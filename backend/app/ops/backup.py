"""Backups of the knowledge store and restores onto new volumes (docs/12 · T052.1/T053.1).

A backup is a directory ``<name>/`` holding ``db.dump`` (pg_dump custom format),
``objects/..`` (every stored blob under its content address) and ``manifest.json``.
Everything is written under ``.<name>.partial`` and renamed into place only after it was
verified, so a directory with a manifest is always complete. It is consistent without a
write freeze:

* pg_dump reads the snapshot exported by the transaction that lists objects and counts
  rows, so the dump and the manifest describe the same instant;
* blobs are immutable and content-addressed, and an ``objects`` row is committed only
  after its bytes are stored, so every row in that snapshot has its blob;
* garbage collection takes the same maintenance lock, so nothing is deleted meanwhile.

Nothing secret is copied: passwords and keys stay in .env, which a restore needs again.
This layer does not encrypt; keep backups on encrypted storage (docs/12).

A restore never touches a live system: it refuses a database that already has tables,
copies the blobs first (idempotent), restores the dump in one transaction, then compares
every table count, the schema head, the active release and each blob with the manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Iterator
import uuid

import psycopg
from psycopg import sql

from ..storage.base import CHUNK, ObjectStore, validate_key
from .archive import ArchiveError, BackupKey
from ..storage.gc import MAINTENANCE_LOCK
from ..storage.local import LocalObjectStore

FORMAT = 'bazi-backup-1'
TOOL_TIMEOUT = 6 * 3600
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')


class BackupError(Exception):
    def __init__(self, code: str, message: str, details: list | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or []


@dataclass(frozen=True)
class Database:
    """Owner connection; tools get it through PG* variables, never argv."""
    host: str
    port: int
    user: str
    password: str
    dbname: str

    @classmethod
    def from_conninfo(cls, conninfo: str) -> 'Database':
        info = psycopg.conninfo.conninfo_to_dict(conninfo)
        return cls(info.get('host', 'localhost'), int(info.get('port', 5432)), info['user'],
                   info.get('password', ''), info['dbname'])

    def conninfo(self) -> str:
        return psycopg.conninfo.make_conninfo(host=self.host, port=self.port, user=self.user,
                                              password=self.password, dbname=self.dbname)

    def env(self) -> dict:
        return {**os.environ, 'PGHOST': self.host, 'PGPORT': str(self.port), 'PGUSER': self.user,
                'PGPASSWORD': self.password, 'PGDATABASE': self.dbname}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _tool(binary: str, args: list[str], env: dict | None = None,
          timeout: int = TOOL_TIMEOUT) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run([binary, *args], env=env, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise BackupError('TOOL_MISSING', f'{binary} not found; run this in the app image'
                          ' (PostgreSQL 17 client tools)') from None
    except subprocess.TimeoutExpired:
        raise BackupError('TOOL_TIMEOUT', f'{binary} did not finish in {timeout}s') from None
    if result.returncode != 0:
        message = result.stderr.decode('utf-8', 'replace').strip()[-500:]
        raise BackupError('TOOL_FAILED', f'{Path(binary).name}: {message}')
    return result


def tool_major(binary: str) -> int:
    out = _tool(binary, ['--version'], timeout=60).stdout.decode()
    found = re.search(r'\b(\d+)(?:\.\d+)?', out)
    if not found:
        raise BackupError('TOOL_FAILED', f'cannot read the version of {binary}: {out[:80]}')
    return int(found.group(1))


def _tables(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")]


def _facts(conn) -> dict:
    """Schema head, row counts, objects and the active release, all in one snapshot."""
    counts = {t: conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t)))
              .fetchone()[0] for t in _tables(conn)}
    objects = [{'key': key, 'sha256': sha.strip(), 'size_bytes': size} for key, sha, size in
               conn.execute("SELECT object_key, sha256, size_bytes FROM objects"
                            " WHERE state = 'ready' ORDER BY object_key")]
    active = conn.execute("SELECT release_id, visibility_epoch FROM active_corpus"
                          " WHERE slot = 'default'").fetchone()
    return {
        'schema_head': conn.execute('SELECT version_num FROM alembic_version').fetchone()[0],
        'server_version': conn.execute('SHOW server_version').fetchone()[0],
        'server_major': int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000,
        'counts': counts, 'objects': objects,
        'active_corpus': {'release_id': str(active[0]), 'visibility_epoch': active[1]}
        if active else None,
    }


def _key_for(manifest: dict, secret: str | None) -> BackupKey | None:
    encryption = manifest.get('encryption')
    if not isinstance(encryption, dict):          # older or clear backups: a note string
        return None
    try:
        return BackupKey.for_manifest(secret, encryption)
    except ArchiveError as exc:
        raise BackupError(exc.code, str(exc)) from None


def _plain_chunks(path: Path, key: BackupKey | None, name: str, digest) -> Iterator[bytes]:
    """The file's plaintext in chunks, hashed on the way; decrypted when ``key`` is set.
    Nothing decrypted is written to disk (containers here have read-only roots)."""
    if key is None:
        with open(path, 'rb') as handle:
            while chunk := handle.read(CHUNK):
                digest.update(chunk)
                yield chunk
        return
    with open(path, 'rb') as handle:
        for chunk in key.decrypt(handle, name):
            digest.update(chunk)
            yield chunk


def _tool_fed(binary: str, args: list[str], chunks: Iterator[bytes], env: dict | None = None,
              timeout: int = TOOL_TIMEOUT) -> None:
    """Run a tool reading its archive from stdin. Every chunk is still consumed (so the
    caller's checksum and the decryption check cover the whole file) even if the tool
    stops reading early, as ``pg_restore --list`` does after the table of contents."""
    try:
        process = subprocess.Popen([binary, *args], stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError:
        raise BackupError('TOOL_MISSING', f'{binary} not found; run this in the app image'
                          ' (PostgreSQL 17 client tools)') from None
    errors: list[bytes] = []
    drain = threading.Thread(target=lambda: errors.append(process.stderr.read()), daemon=True)
    drain.start()
    open_pipe = True
    try:
        for chunk in chunks:
            if open_pipe:
                try:
                    process.stdin.write(chunk)
                except (BrokenPipeError, OSError):
                    open_pipe = False
        if open_pipe:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        raise BackupError('TOOL_TIMEOUT', f'{binary} did not finish in {timeout}s') from None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        drain.join(timeout=10)
        for pipe in (process.stdin, process.stderr):
            try:
                pipe.close()
            except (BrokenPipeError, OSError):
                pass
    if process.returncode != 0:
        message = b''.join(errors).decode('utf-8', 'replace').strip()[-500:]
        raise BackupError('TOOL_FAILED', f'{Path(binary).name}: {message}')


def _copy_blob(store: ObjectStore, item: dict, root: Path, key: BackupKey | None = None) -> None:
    target = root / validate_key(item['key'])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    digest, size = hashlib.sha256(), 0
    with open(temporary, 'wb') as out:
        for chunk in store.get_stream(item['key']):
            digest.update(chunk)
            size += len(chunk)
            out.write(chunk)
        out.flush()
        os.fsync(out.fileno())
    if digest.hexdigest() != item['sha256'] or size != item['size_bytes']:
        temporary.unlink()
        raise BackupError('OBJECT_CORRUPT', f"stored bytes of {item['key']} do not match the"
                          ' database record')
    if key is not None:
        key.encrypt_file(temporary, target, item['key'])
        temporary.unlink()
    else:
        os.replace(temporary, target)


def create_backup(db: Database, store: ObjectStore, dest: Path, name: str | None = None,
                  pg_dump: str = 'pg_dump', pg_restore: str = 'pg_restore',
                  lock_timeout_s: int = 300, encryption_secret: str | None = None) -> dict:
    """Write a verified backup directory under ``dest``; returns its manifest. With a
    secret every file is encrypted (archive.py) and the manifest says how, never the key."""
    started = time.monotonic()
    try:
        key = BackupKey.new(encryption_secret) if encryption_secret else None
    except ArchiveError as exc:
        raise BackupError(exc.code, str(exc)) from None
    name = name or datetime.now(timezone.utc).strftime('bazi-%Y%m%dT%H%M%SZ')
    if not NAME.match(name):
        raise BackupError('VALIDATION_ERROR', 'backup name: letters, digits, . _ - (max 100)')
    dest = Path(dest)
    final, staging = dest / name, dest / f'.{name}.partial'
    if final.exists():
        raise BackupError('BACKUP_EXISTS', f'{final} already exists')
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with psycopg.connect(db.conninfo(), autocommit=True) as lock:
            # Waits for a running GC to finish; GC skips while this is held.
            lock.execute(sql.SQL('SET lock_timeout = {}').format(sql.Literal(f'{lock_timeout_s}s')))
            lock.execute('SELECT pg_advisory_lock(hashtext(%s))', (MAINTENANCE_LOCK,))
            try:
                with psycopg.connect(db.conninfo()) as snap:
                    snap.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                    snapshot = snap.execute('SELECT pg_export_snapshot()').fetchone()[0]
                    facts = _facts(snap)
                    if tool_major(pg_dump) < facts['server_major']:
                        raise BackupError('TOOL_TOO_OLD', f'pg_dump older than server'
                                          f" {facts['server_version']}")
                    _tool(pg_dump, ['--format=custom', f'--snapshot={snapshot}',
                                    f"--file={staging / 'db.dump'}", '--no-password'],
                          env=db.env())
                    snap.rollback()
                for item in facts['objects']:
                    _copy_blob(store, item, staging, key)
            finally:
                lock.execute('SELECT pg_advisory_unlock(hashtext(%s))', (MAINTENANCE_LOCK,))
        dump = staging / 'db.dump'
        _tool(pg_restore, ['--list', str(dump)], timeout=600)     # the archive is readable
        database = {'file': 'db.dump', 'sha256': _sha256_file(dump),
                    'size_bytes': dump.stat().st_size}
        if key is not None:
            sealed = staging / 'db.dump.enc'
            key.encrypt_file(dump, sealed, 'db.dump')
            dump.unlink()
            database.update(file='db.dump.enc', stored_sha256=_sha256_file(sealed))
        manifest = {
            'format': FORMAT, 'name': name,
            'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'schema_head': facts['schema_head'], 'server_version': facts['server_version'],
            'database': database,
            'objects': {'count': len(facts['objects']),
                        'total_bytes': sum(o['size_bytes'] for o in facts['objects']),
                        'items': facts['objects']},
            'counts': facts['counts'], 'active_corpus': facts['active_corpus'],
            'secrets': 'not included: a restore needs the same .env (keys, passwords)',
            'encryption': key.describe() if key else
            'none: BACKUP_ENCRYPTION_KEY was not set; keep this backup on encrypted storage',
            'duration_seconds': round(time.monotonic() - started, 1),
        }
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False),
                                               encoding='utf-8')
        os.replace(staging, final)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


# ---- catalogue, retention and record ---------------------------------------------------

def list_backups(dest: Path) -> list[dict]:
    """Complete backups under ``dest`` (a readable manifest), newest first."""
    found = []
    for folder in Path(dest).iterdir() if Path(dest).is_dir() else []:
        if folder.name.startswith('.') or not (folder / 'manifest.json').is_file():
            continue
        try:
            manifest, _ = load_manifest(folder / 'manifest.json')
        except BackupError:
            continue
        found.append({'name': manifest['name'], 'path': str(folder),
                      'created_at': datetime.fromisoformat(manifest['created_at']),
                      'encrypted': isinstance(manifest.get('encryption'), dict)})
    return sorted(found, key=lambda b: b['created_at'], reverse=True)


def prune(dest: Path, keep_daily: int = 7, keep_weekly: int = 4, dry_run: bool = False) -> dict:
    """Keep the newest backup of each of the last ``keep_daily`` days and of the last
    ``keep_weekly`` ISO weeks (docs/12: 7 daily + 4 weekly); the newest always stays."""
    backups = list_backups(dest)
    keep = {b['name'] for b in backups[:1]}
    for size, bucket in ((keep_daily, lambda d: d.date()),
                         (keep_weekly, lambda d: tuple(d.isocalendar())[:2])):
        seen: list = []
        for b in backups:
            period = bucket(b['created_at'])
            if period not in seen and len(seen) < size:
                seen.append(period)
                keep.add(b['name'])
    removed = [b for b in backups if b['name'] not in keep]
    if not dry_run:
        for b in removed:
            shutil.rmtree(b['path'])
    return {'dry_run': dry_run, 'kept': sorted(keep),
            'removed': [b['name'] for b in removed]}


def record_backup(db: Database, store: ObjectStore, manifest: dict, location: str) -> str | None:
    """Note a verified backup in its own database (for the overdue alert and the list).
    The restored copy of this database will not contain the row; the manifest on disk is
    what a restore reads."""
    import io
    body = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode('utf-8')
    with psycopg.connect(db.conninfo()) as conn:
        actor = conn.execute("SELECT id FROM users WHERE role = 'admin' AND enabled"
                             ' ORDER BY created_at LIMIT 1').fetchone()
        if actor is None:
            return None
        stored = store.put_if_absent(io.BytesIO(body))
        conn.execute("INSERT INTO objects (sha256, storage_backend, object_key, size_bytes,"
                     " detected_mime, state) VALUES (%s, %s, %s, %s, 'application/json', 'ready')"
                     ' ON CONFLICT DO NOTHING',
                     (stored.sha256, store.backend, stored.key, stored.size_bytes))
        object_id = conn.execute('SELECT id FROM objects WHERE sha256 = %s',
                                 (stored.sha256,)).fetchone()[0]
        job = conn.execute(
            "INSERT INTO operation_jobs (kind, requested_by, state, target_manifest,"
            " idempotency_key) VALUES ('backup', %s, 'succeeded', %s, %s) RETURNING id",
            (actor[0], json.dumps({'name': manifest['name'], 'created_at': manifest['created_at']}),
             hashlib.sha256(f"backup:{manifest['name']}".encode()).hexdigest())).fetchone()[0]
        encryption = manifest.get('encryption')
        ref = (f"BACKUP_ENCRYPTION_KEY:{encryption['key_id'][:16]}"
               if isinstance(encryption, dict) else 'none')
        backup_id = conn.execute(
            'INSERT INTO backups (operation_job_id, manifest_object_id, archive_location,'
            " db_schema_version, checksum, encryption_key_ref, state, verified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'verified', now()) RETURNING id",
            (job, object_id, location, manifest['schema_head'], stored.sha256, ref)).fetchone()[0]
    return str(backup_id)


# ---- restore ------------------------------------------------------------------------

def load_manifest(path: Path) -> tuple[dict, Path]:
    path = Path(path)
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise BackupError('MANIFEST_UNREADABLE', f'cannot read {path.name}: {exc}') from None
    if manifest.get('format') != FORMAT:
        raise BackupError('MANIFEST_UNSUPPORTED', f"unknown backup format {manifest.get('format')}")
    return manifest, path.parent


def known_heads() -> set[str]:
    """Every migration revision this code knows (a newer backup cannot be restored)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    return {r.revision for r in ScriptDirectory.from_config(config).walk_revisions()}


def preflight(manifest_path: Path, pg_restore: str = 'pg_restore',
              secret: str | None = None) -> dict:
    """Read-only checks before anything is restored; ``ok`` only if all pass. An encrypted
    backup is decrypted in full (to a temporary copy) as part of the check."""
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = '') -> None:
        checks.append({'name': name, 'ok': ok, 'detail': detail})

    manifest, root = load_manifest(manifest_path)
    try:
        key = _key_for(manifest, secret)
        if key is not None:
            check('encryption', True, f"key {key.key_id[:8]}… matches")
    except BackupError as exc:
        check('encryption', False, str(exc))
        return {'ok': False, 'backup': manifest['name'], 'created_at': manifest['created_at'],
                'checks': checks}
    meta = manifest['database']
    dump = root / meta['file']
    if not dump.is_file():
        check('database_dump', False, f"{meta['file']} is missing")
    elif key is not None and _sha256_file(dump) != meta['stored_sha256']:
        check('database_dump', False, 'encrypted dump checksum differs from the manifest')
    else:
        digest = hashlib.sha256()
        listed = None
        try:
            # One pass: decrypt, hash and let pg_restore read the table of contents.
            _tool_fed(pg_restore, ['--list'], _plain_chunks(dump, key, 'db.dump', digest),
                      timeout=600)
        except ArchiveError as exc:
            check('database_dump', False, str(exc))
        except BackupError as exc:
            listed = str(exc)
        else:
            listed = ''
        if listed is not None:
            same = digest.hexdigest() == meta['sha256']
            check('database_dump', same, '' if same else 'checksum differs from the manifest')
            if same:
                check('database_archive', not listed, listed)
    bad = []
    for item in manifest['objects']['items']:
        path = root / validate_key(item['key'])
        if not path.is_file():
            bad.append(item['key'])
            continue
        try:
            digest = (key.plaintext_sha256(path, item['key']) if key is not None
                      else _sha256_file(path))
        except ArchiveError:
            digest = None
        if digest != item['sha256'] or (key is None and path.stat().st_size != item['size_bytes']):
            bad.append(item['key'])
    check('objects', not bad, f'{len(bad)} missing or corrupt, e.g. {bad[0]}' if bad
          else f"{manifest['objects']['count']} verified")
    known = manifest['schema_head'] in known_heads()
    check('schema', known, '' if known else 'the backup is newer than this application')
    return {'ok': all(c['ok'] for c in checks), 'backup': manifest['name'],
            'created_at': manifest['created_at'], 'checks': checks}


def _restore_blobs(manifest: dict, root: Path, store: ObjectStore,
                   key: BackupKey | None = None) -> int:
    copied = 0
    for item in manifest['objects']['items']:
        source = root / validate_key(item['key'])
        handle = key.reader(source, item['key']) if key is not None else open(source, 'rb')
        with handle:
            stored = store.put_if_absent(handle, expected_sha256=item['sha256'],
                                         namespace=item['key'].split('/', 1)[0])
        if stored.key != item['key']:
            raise BackupError('OBJECT_CORRUPT', f"{item['key']} restored under {stored.key}")
        copied += stored.created
    return copied


LEDGER_FORMAT = 'bazi-deletion-ledger-1'


def export_ledger(db: Database) -> dict:
    """Erasures recorded by the live system, for a restore of an older backup (docs/12)."""
    with psycopg.connect(db.conninfo()) as conn:
        rows = conn.execute('SELECT subject_id, account_deleted, created_at FROM deletion_ledger'
                            ' ORDER BY created_at, id').fetchall()
    return {'format': LEDGER_FORMAT, 'exported_at': datetime.now(timezone.utc).isoformat(),
            'entries': [{'subject_id': str(s), 'account_deleted': a, 'erased_at': t.isoformat()}
                        for s, a, t in rows]}


def reapply_ledger(db: Database, ledger: dict, since: datetime) -> int:
    """Erase again everyone erased after ``since`` (the backup time); one transaction."""
    if ledger.get('format') != LEDGER_FORMAT:
        raise BackupError('LEDGER_INVALID', f'the deletion ledger must be {LEDGER_FORMAT}')
    entries = [e for e in ledger['entries'] if datetime.fromisoformat(e['erased_at']) > since]
    with psycopg.connect(db.conninfo()) as conn:
        if conn.execute("SELECT to_regproc('bazi_erase_owner')").fetchone()[0] is None:
            raise BackupError('LEDGER_NEEDS_UPGRADE', 'this backup predates erasure support;'
                              ' run alembic upgrade head, then restore again with the ledger')
        for entry in entries:
            if conn.execute('SELECT 1 FROM users WHERE id = %s', (entry['subject_id'],)).fetchone():
                conn.execute('SELECT bazi_erase_owner(%s, %s, NULL)',
                             (entry['subject_id'], entry['account_deleted']))
    return len(entries)


def post_restore_checks(db: Database, store: ObjectStore) -> dict:
    """Runbook step 4 (docs/12) on the restored system, with evidence for the report:
    cited spans still match their page text, chart facts match their hash, the active
    release is ready, book sources hash to their records, and what the watchdog will
    resume. Raises VERIFY_FAILED on the first three kinds of mismatch."""
    with psycopg.connect(db.conninfo()) as conn:
        spans, bad_spans = conn.execute(
            'SELECT count(*), count(*) FILTER (WHERE e.quote_hash <> bazi_sha256_text(substr('
            'r.normalized_text, e.start_offset + 1, e.end_offset - e.start_offset)))'
            ' FROM evidence_spans e JOIN page_revisions r ON r.id = e.page_revision_id').fetchone()
        charts, bad_charts = conn.execute(
            'SELECT count(*), count(*) FILTER (WHERE facts_hash <> bazi_sha256_text(facts::text))'
            ' FROM bazi_charts').fetchone()
        release = conn.execute(
            "SELECT r.state FROM active_corpus a JOIN corpus_releases r ON r.id = a.release_id"
            " WHERE a.slot = 'default'").fetchone()
        sources = conn.execute(
            'SELECT o.object_key, o.sha256 FROM book_versions v JOIN objects o ON o.id = v.object_id'
        ).fetchall()
        unfinished = conn.execute(
            "SELECT count(*) FROM ingestion_jobs WHERE state IN ('queued', 'running', 'retry_wait')"
        ).fetchone()[0]
    bad_sources = []
    for key, expected in sources:
        digest = hashlib.sha256()
        for chunk in store.get_stream(key):
            digest.update(chunk)
        if digest.hexdigest() != expected.strip():
            bad_sources.append(key)
    problems = []
    if bad_spans:
        problems.append(f'{bad_spans} cited spans differ from their page text')
    if bad_charts:
        problems.append(f'{bad_charts} charts differ from their facts hash')
    if release is not None and release[0] != 'active':
        problems.append(f'the active pointer names a {release[0]} release')
    if bad_sources:
        problems.append(f'{len(bad_sources)} book sources do not hash to their record')
    if problems:
        raise BackupError('VERIFY_FAILED', 'the restored system failed its checks', problems)
    return {'evidence_spans_verified': spans, 'charts_verified': charts,
            'book_sources_verified': len(sources),
            'active_release': release[0] if release else None,
            'unfinished_jobs_to_resume': unfinished}


def restore(manifest_path: Path, db: Database, store: ObjectStore, confirm: str,
            pg_restore: str = 'pg_restore', ledger: dict | None = None,
            secret: str | None = None) -> dict:
    """Restore into an empty database and object store; returns a report (RTO/RPO). With the
    live system's deletion ledger, erasures made after the backup are applied again."""
    started = time.monotonic()
    manifest, root = load_manifest(manifest_path)
    if confirm != manifest['name']:
        raise BackupError('CONFIRMATION_MISMATCH', f"type the backup name {manifest['name']!r}"
                          ' to confirm')
    checked = preflight(manifest_path, pg_restore, secret)
    if not checked['ok']:
        raise BackupError('PREFLIGHT_FAILED', 'preflight failed; nothing was restored',
                          [c for c in checked['checks'] if not c['ok']])
    with psycopg.connect(db.conninfo(), autocommit=True) as conn:
        if _tables(conn):
            raise BackupError('TARGET_NOT_EMPTY', f'database {db.dbname} already has tables;'
                              ' restore only into new volumes')
        # Roles are cluster-wide and not in a database dump; grants in the dump need it.
        conn.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname ="
                     " 'bazi_runtime') THEN CREATE ROLE bazi_runtime NOLOGIN NOSUPERUSER"
                     ' NOBYPASSRLS NOCREATEDB NOCREATEROLE; END IF; END $$')
    if isinstance(store, LocalObjectStore):
        store.root.mkdir(parents=True, exist_ok=True)
        need = manifest['objects']['total_bytes'] * 1.05
        if shutil.disk_usage(store.root).free < need:
            raise BackupError('DISK_FULL', f'the object store needs {int(need)} free bytes')
    key = _key_for(manifest, secret)
    blobs = _restore_blobs(manifest, root, store, key)
    _tool_fed(pg_restore, ['--dbname', db.dbname, '--exit-on-error', '--single-transaction',
                           '--no-password'],
              _plain_chunks(root / manifest['database']['file'], key, 'db.dump',
                            hashlib.sha256()), env=db.env())
    problems = []
    with psycopg.connect(db.conninfo()) as conn:
        facts = _facts(conn)
    if facts['schema_head'] != manifest['schema_head']:
        problems.append('schema head differs')
    if facts['counts'] != manifest['counts']:
        differ = sorted(t for t in set(facts['counts']) | set(manifest['counts'])
                        if facts['counts'].get(t) != manifest['counts'].get(t))
        problems.append(f'row counts differ: {", ".join(differ[:10])}')
    if facts['active_corpus'] != manifest['active_corpus']:
        problems.append('active release differs')
    missing = [o['key'] for o in facts['objects']
               if (stat := store.stat(o['key'])) is None or stat.size_bytes != o['size_bytes']]
    if missing:
        problems.append(f'{len(missing)} objects missing in the store, e.g. {missing[0]}')
    if problems:
        raise BackupError('VERIFY_FAILED', 'restored data does not match the backup', problems)
    created = datetime.fromisoformat(manifest['created_at'])
    erasures = reapply_ledger(db, ledger, created) if ledger is not None else None
    verified = post_restore_checks(db, store)
    return {
        'backup': manifest['name'], 'restored_at': datetime.now(timezone.utc).isoformat(
            timespec='seconds'),
        'duration_seconds': round(time.monotonic() - started, 1),          # measured RTO part
        'backup_age_hours': round((datetime.now(timezone.utc) - created).total_seconds() / 3600, 2),
        'tables': len(facts['counts']), 'rows': sum(facts['counts'].values()),
        'objects': len(facts['objects']), 'objects_written': blobs,
        'erasures_reapplied': erasures, 'checks': verified,
        'schema_head': facts['schema_head'], 'active_corpus': facts['active_corpus'],
        'next_steps': ['create-runtime-login for the API login role',
                       'alembic upgrade head if this application is newer than the backup',
                       'start the app on a separate port, check sources/search, then switch'],
        'report_id': uuid.uuid4().hex,
    }
