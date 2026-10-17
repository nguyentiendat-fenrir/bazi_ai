"""Local administration CLI (owner database connection, never exposed over HTTP).

    python -m backend.app.cli create-runtime-login   # LOGIN role in bazi_runtime
    python -m backend.app.cli bootstrap-admin --email admin@example.test
    python -m backend.app.cli export-openapi          # contracts/openapi.json snapshot
    python -m backend.app.cli gc --dry-run              # unreferenced objects, orphan blobs
    python -m backend.app.cli backup --dest /backups    # db.dump + objects + manifest.json
    python -m backend.app.cli restore --manifest /backup/<name>/manifest.json --confirm <name>
    python -m backend.app.cli embedding-profile --provider openai_compatible --model bge-m3 \
        --revision <rev> --dimension 1024 --base-url http://embed:8080/v1 --locality local \
        --provision
    python -m backend.app.cli pipeline-profile --name "Sách in"         --embedding-profile <id> --ocr-languages vie+eng

Passwords come from an environment variable or an interactive prompt, never
from argv (shell history, process lists).
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, pool, text

from .auth.passwords import validate_new_password
from .auth.service import create_user
from .core.config import ConfigError, load_settings

BOOTSTRAP_PASSWORD_ENV = 'BAZI_BOOTSTRAP_PASSWORD'


def _password(prompt_env: str) -> str:
    value = os.environ.get(prompt_env)
    if value:
        return value
    first = getpass.getpass('Password: ')
    if first != getpass.getpass('Repeat password: '):
        raise SystemExit('Passwords do not match')
    return first


def bootstrap_admin(email: str) -> int:
    settings = load_settings()
    password = _password(BOOTSTRAP_PASSWORD_ENV)
    try:
        validate_new_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.begin() as conn:
        # One-time: refuse once any admin exists, so this cannot mint extra admins later.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bazi.users.admins'))"))
        if conn.execute(text("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'admin')")).scalar():
            print('An admin already exists; use the admin UI/API to manage users.',
                  file=sys.stderr)
            return 1
        user = create_user(conn, email.strip().lower(), password, 'admin')
    print(f'Created admin {user["email"]} ({user["id"]})')
    return 0


def create_runtime_login() -> int:
    settings = load_settings()
    if not settings.postgres_app_user or not settings.postgres_app_password:
        raise SystemExit('Set POSTGRES_APP_USER and POSTGRES_APP_PASSWORD first')
    if settings.postgres_app_user == settings.postgres_user:
        raise SystemExit('POSTGRES_APP_USER must differ from the owner POSTGRES_USER')
    owner = settings.database_url
    with psycopg.connect(host=owner.host, port=owner.port, dbname=owner.database,
                         user=owner.username, password=owner.password, autocommit=True) as conn:
        role = sql.Identifier(settings.postgres_app_user)
        password = sql.Literal(settings.postgres_app_password.get_secret_value())
        exists = conn.execute('SELECT 1 FROM pg_roles WHERE rolname = %s',
                              (settings.postgres_app_user,)).fetchone()
        verb = sql.SQL('ALTER') if exists else sql.SQL('CREATE')
        conn.execute(sql.SQL('{} ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE'
                             ' PASSWORD {}').format(verb, role, password))
        conn.execute(sql.SQL('GRANT bazi_runtime TO {}').format(role))
        conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}')
                     .format(sql.Identifier(owner.database), role))
    print(f'Runtime login {settings.postgres_app_user} is ready (member of bazi_runtime)')
    return 0


OPENAPI_PATH = Path(__file__).resolve().parents[2] / 'contracts' / 'openapi.json'


def openapi_document() -> dict:
    """The contract from default settings only, so the snapshot never depends on .env."""
    from unittest.mock import patch

    from .main import create_app
    with patch.dict(os.environ, {}, clear=True):
        settings = load_settings(_env_file=None)
    return create_app(settings).openapi()


def export_openapi() -> int:
    OPENAPI_PATH.parent.mkdir(exist_ok=True)
    text_ = json.dumps(openapi_document(), indent=2, ensure_ascii=False, sort_keys=True) + '\n'
    OPENAPI_PATH.write_text(text_, encoding='utf-8', newline='\n')
    print(f'Wrote {OPENAPI_PATH}')
    return 0


def embedding_profile(args) -> int:
    from .retrieval.models import create_ann_index, provision_collection, register_profile
    settings = load_settings()
    config = {k: v for k, v in (('base_url', args.base_url),
                                ('passage_prefix', args.passage_prefix),
                                ('query_prefix', args.query_prefix),
                                ('locality', args.locality),
                                ('max_distance', args.max_distance)) if v}
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.begin() as conn:
        profile = register_profile(conn, args.provider, args.model, args.revision, args.dimension,
                                   config, args.secret_ref)
    print(f'Embedding profile {profile.id} ({profile.profile_hash[:12]})')
    if args.provision or args.ann_index:
        owner = settings.database_url
        with psycopg.connect(host=owner.host, port=owner.port, dbname=owner.database,
                             user=owner.username, password=owner.password, autocommit=True) as conn:
            if args.provision:
                print(f'Collection table {provision_collection(conn, profile, args.distance)}')
            if args.ann_index:
                create_ann_index(conn, profile)
                print('HNSW index ready')
    return 0


def pipeline_profile(args) -> int:
    import uuid

    from .ingestion.docx import renderer_version
    from .ingestion.profiles import ProfileError, create_pipeline_profile
    settings = load_settings()
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    try:
        with engine.begin() as conn:
            # Run it where the worker runs (its image) so the DOCX renderer recorded is real.
            profile_id, created = create_pipeline_profile(
                conn, args.name, uuid.UUID(args.embedding_profile), args.ocr_languages,
                renderer_version())
    except (ProfileError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    print(f'Pipeline profile {profile_id} ({"created" if created else "already existed"})')
    return 0


def collect_garbage(args) -> int:
    from datetime import timedelta

    from .storage import build_store
    from .storage.gc import collect
    settings = load_settings()
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    result = collect(engine, build_store(settings), timedelta(hours=args.grace_hours),
                     args.dry_run)
    print(json.dumps(result))
    return 0


def _owner_database(settings):
    from .ops.backup import Database
    url = settings.database_url
    return Database(url.host or 'localhost', url.port or 5432, url.username, url.password or '',
                    url.database)


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))


def run_backup(args) -> int:
    from .ops.backup import BackupError, create_backup
    from .storage import build_store
    settings = load_settings()
    try:
        manifest = create_backup(_owner_database(settings), build_store(settings),
                                 Path(args.dest), args.name, args.pg_dump, args.pg_restore)
    except BackupError as exc:
        _print({'ok': False, 'code': exc.code, 'message': str(exc), 'details': exc.details})
        return 1
    _print({'ok': True, 'name': manifest['name'], 'path': str(Path(args.dest) / manifest['name']),
            'created_at': manifest['created_at'], 'schema_head': manifest['schema_head'],
            'objects': manifest['objects']['count'],
            'object_bytes': manifest['objects']['total_bytes'],
            'database_bytes': manifest['database']['size_bytes'],
            'duration_seconds': manifest['duration_seconds']})
    return 0


def run_restore(args) -> int:
    from .ops.backup import BackupError, preflight, restore
    from .storage import build_store
    from .storage.local import LocalObjectStore
    if args.command == 'restore-preflight':
        try:
            result = preflight(Path(args.manifest), args.pg_restore)
        except BackupError as exc:
            result = {'ok': False, 'code': exc.code, 'message': str(exc)}
        _print(result)
        return 0 if result['ok'] else 1
    settings = load_settings()
    # Restored blobs were accepted once; today's upload limit does not apply to them.
    store = (LocalObjectStore(settings.storage_root) if settings.storage_backend == 'local'
             else build_store(settings))
    try:
        report = restore(Path(args.manifest), _owner_database(settings), store, args.confirm,
                         args.pg_restore)
    except BackupError as exc:
        _print({'ok': False, 'code': exc.code, 'message': str(exc), 'details': exc.details})
        return 1
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                     encoding='utf-8')
    _print({'ok': True, **report})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m backend.app.cli')
    commands = parser.add_subparsers(dest='command', required=True)
    admin = commands.add_parser('bootstrap-admin', help='create the first admin account')
    admin.add_argument('--email', required=True)
    commands.add_parser('create-runtime-login', help='create/update the API database login')
    commands.add_parser('export-openapi', help='write contracts/openapi.json')
    embed = commands.add_parser('embedding-profile', help='register/provision an embedding profile')
    embed.add_argument('--provider', required=True, choices=['openai_compatible', 'fixture-hashing'])
    embed.add_argument('--model', required=True)
    embed.add_argument('--revision', required=True)
    embed.add_argument('--dimension', required=True, type=int)
    embed.add_argument('--base-url')
    embed.add_argument('--secret-ref')
    embed.add_argument('--passage-prefix')
    embed.add_argument('--query-prefix')
    embed.add_argument('--max-distance', type=float,
                       help='cosine distance beyond which a neighbour is not evidence (T036)')
    embed.add_argument('--locality', choices=['local', 'external'],
                       help='local = self-hosted server; otherwise each version must allow'
                            ' external processing')
    embed.add_argument('--distance', default='cosine', choices=['cosine', 'l2', 'inner_product'])
    embed.add_argument('--provision', action='store_true', help='create the vector table')
    embed.add_argument('--ann-index', action='store_true', help='create the HNSW index')
    pipe = commands.add_parser('pipeline-profile',
                               help='create the profile uploads are processed with')
    pipe.add_argument('--name', required=True)
    pipe.add_argument('--embedding-profile', required=True, help='id of a provisioned profile')
    pipe.add_argument('--ocr-languages', help='Tesseract languages, default vie+eng')
    back = commands.add_parser('backup', help='consistent backup: db.dump, objects, manifest')
    back.add_argument('--dest', required=True, help='directory on encrypted storage')
    back.add_argument('--name', help='default bazi-<UTC timestamp>')
    back.add_argument('--pg-dump', default='pg_dump')
    back.add_argument('--pg-restore', default='pg_restore')
    pre = commands.add_parser('restore-preflight', help='verify a backup without restoring')
    pre.add_argument('--manifest', required=True)
    pre.add_argument('--pg-restore', default='pg_restore')
    rest = commands.add_parser('restore', help='restore into an EMPTY database and store')
    rest.add_argument('--manifest', required=True)
    rest.add_argument('--confirm', required=True, help='the backup name, typed again')
    rest.add_argument('--report', help='also write the restore report to this file')
    rest.add_argument('--pg-restore', default='pg_restore')
    gc = commands.add_parser('gc', help='remove unreferenced objects and orphan blobs')
    gc.add_argument('--grace-hours', type=float, default=24.0)
    gc.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'bootstrap-admin':
            return bootstrap_admin(args.email)
        if args.command == 'export-openapi':
            return export_openapi()
        if args.command == 'embedding-profile':
            return embedding_profile(args)
        if args.command == 'gc':
            return collect_garbage(args)
        if args.command == 'pipeline-profile':
            return pipeline_profile(args)
        if args.command == 'backup':
            return run_backup(args)
        if args.command in ('restore', 'restore-preflight'):
            return run_restore(args)
        return create_runtime_login()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    raise SystemExit(main())
