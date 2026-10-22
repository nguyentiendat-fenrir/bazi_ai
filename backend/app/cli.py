"""Local administration CLI (owner database connection, never exposed over HTTP).

    python -m backend.app.cli create-runtime-login   # LOGIN role in bazi_runtime
    python -m backend.app.cli bootstrap-admin --email admin@example.test
    python -m backend.app.cli export-openapi          # contracts/openapi.json snapshot
    python -m backend.app.cli gc --dry-run              # unreferenced objects, orphan blobs
    python -m backend.app.cli backup --dest /backups    # db.dump + objects + manifest.json
    python -m backend.app.cli restore --manifest /backup/<name>/manifest.json --confirm <name>
    python -m backend.app.cli deletion-ledger --out /backups/ledger.json   # erasures since
    python -m backend.app.cli evaluate --dataset gold --version 1 --as reviewer@example.test \
        --split test --baseline latest     # exit 1 on a regression (or a failed gate with --gates)
    python -m backend.app.cli embedding-profile --provider openai_compatible --model bge-m3 \
        --revision <rev> --dimension 1024 --base-url http://embed:8080/v1 --locality local \
        --provision
    python -m backend.app.cli load-glossary --as reviewer@example.test --publish   # term list
    python -m backend.app.cli curate --as reviewer@example.test --dry-run           # definitions
    python -m backend.app.cli pipeline-profile --name "Sách in"         --embedding-profile <id> --ocr-languages vie+eng

RAG pilot (backend/app/rag/admin.py):

    python -m backend.app.cli fetch-models                 # pinned models into the model cache
    python -m backend.app.cli rag-setup                    # embedding + pipeline profiles
    python -m backend.app.cli ingest-folder /inputs/books --admin admin@example.test
    python -m backend.app.cli judge-password               # hash for JUDGE_PASSWORD_HASH

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
JUDGE_PASSWORD_ENV = 'BAZI_JUDGE_PASSWORD'


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


def contract_app():
    """The app built from default settings only, so the contract never depends on .env."""
    from unittest.mock import patch

    from .main import create_app
    with patch.dict(os.environ, {}, clear=True):
        settings = load_settings(_env_file=None)
    return create_app(settings)


def openapi_document() -> dict:
    return contract_app().openapi()


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
    from .ops.backup import BackupError, create_backup, prune, record_backup
    from .storage import build_store
    settings = load_settings()
    try:
        secret = (settings.backup_encryption_key.get_secret_value()
                  if settings.backup_encryption_key else None)
        store = build_store(settings)
        manifest = create_backup(_owner_database(settings), store, Path(args.dest), args.name,
                                 args.pg_dump, args.pg_restore, encryption_secret=secret)
        recorded = record_backup(_owner_database(settings), store, manifest,
                                 str(Path(args.dest) / manifest['name']))
        pruned = (prune(Path(args.dest), args.keep_daily, args.keep_weekly)
                  if args.prune else None)
    except BackupError as exc:
        _print({'ok': False, 'code': exc.code, 'message': str(exc), 'details': exc.details})
        return 1
    _print({'ok': True, 'name': manifest['name'], 'path': str(Path(args.dest) / manifest['name']),
            'created_at': manifest['created_at'], 'schema_head': manifest['schema_head'],
            'objects': manifest['objects']['count'],
            'object_bytes': manifest['objects']['total_bytes'],
            'database_bytes': manifest['database']['size_bytes'],
            'encrypted': isinstance(manifest.get('encryption'), dict),
            'recorded': recorded, 'pruned': pruned,
            'duration_seconds': manifest['duration_seconds']})
    return 0


def run_evaluate(args) -> int:
    """A retrieval regression check for CI or a release: run, compare, set the exit code."""
    import uuid

    from sqlalchemy import create_engine, pool, text

    from .auth.service import Principal
    from .core.errors import AppError
    from .retrieval import evaluate
    settings = load_settings()
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.begin() as conn:
        user = conn.execute(text(
            "SELECT id, email, role FROM users WHERE email = :e AND enabled"
            " AND role IN ('reviewer', 'admin')"), {'e': args.as_user}).mappings().first()
        if user is None:
            _print({'ok': False, 'code': 'USER_NOT_FOUND',
                    'message': 'evaluate as an enabled reviewer or admin (--as)'})
            return 2
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {'u': str(user['id'])})
        principal = Principal(user['id'], user['email'], user['role'], uuid.UUID(int=0), '')
        dataset = conn.execute(text('SELECT id FROM evaluation_datasets WHERE name = :n'
                                    ' AND version = :v'),
                               {'n': args.dataset, 'v': args.version}).scalar()
        if dataset is None:
            _print({'ok': False, 'code': 'DATASET_NOT_FOUND', 'message': 'no such dataset'})
            return 2
        baseline = None
        if args.baseline == 'latest':
            baseline = conn.execute(text(
                "SELECT id FROM evaluation_runs WHERE dataset_id = :d AND status = 'completed'"
                " AND config_snapshot->>'strategy' = :st"
                " AND config_snapshot->>'split' IS NOT DISTINCT FROM :sp"
                ' ORDER BY created_at DESC, id DESC LIMIT 1'),
                {'d': dataset, 'st': args.strategy, 'sp': args.split}).scalar()
        elif args.baseline:
            baseline = uuid.UUID(args.baseline)
        try:
            result = evaluate.run(conn, principal, dataset, args.top_k,
                                  args.strategy == 'hybrid_rerank', args.split, settings.app_env,
                                  (None, None), args.strategy, baseline, args.tolerance)
        except AppError as exc:
            _print({'ok': False, 'code': exc.code, 'message': str(exc)})
            return 2
    failed_gates = [g['metric'] for g in result['gates'] if g['passed'] is False]
    regressed = [c['metric'] for c in result['comparison'] or [] if c['regressed']]
    ok = not regressed and not (args.gates and failed_gates)
    _print({'ok': ok, 'run_id': result['id'], 'strategy': result['config']['strategy'],
            'baseline_run_id': result['config']['baseline_run_id'],
            'metrics': result['metrics'], 'failed_gates': failed_gates, 'regressed': regressed})
    return 0 if ok else 1


def load_glossary(args) -> int:
    """Load the reviewed term list as approved concepts/aliases, optionally publish it."""
    import uuid

    from .auth.service import Principal
    from .core.errors import AppError
    from .knowledge import glossary, ontology_release
    settings = load_settings()
    data = glossary.read(Path(args.file)) if args.file else glossary.read()
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.begin() as conn:
        user = conn.execute(text(
            "SELECT id, email, role FROM users WHERE email = :e AND enabled"
            " AND role IN ('reviewer', 'admin')"), {'e': args.as_user}).mappings().first()
        if user is None:
            _print({'ok': False, 'code': 'USER_NOT_FOUND',
                    'message': 'load as an enabled reviewer or admin (--as)'})
            return 2
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {'u': str(user['id'])})
        principal = Principal(user['id'], user['email'], user['role'], uuid.UUID(int=0), '')
        try:
            report = glossary.load(conn, principal, data).as_dict()
            if args.publish:
                try:
                    report['ontology_release'] = ontology_release.publish(
                        conn, user['id'], None, None)['release']['version']
                except AppError as exc:
                    if exc.code != 'NO_CHANGE':
                        raise
                    report['ontology_release'] = 'unchanged'
        except AppError as exc:
            _print({'ok': False, 'code': exc.code, 'message': str(exc)})
            return 2
    _print({'ok': not report['missing_schools'], **report})
    return 0 if not report['missing_schools'] else 1


def run_restore(args) -> int:
    from .ops.backup import BackupError, preflight, restore
    from .storage import build_store
    from .storage.local import LocalObjectStore
    if args.command == 'restore-preflight':
        try:
            settings = load_settings()
            secret = (settings.backup_encryption_key.get_secret_value()
                      if settings.backup_encryption_key else None)
            result = preflight(Path(args.manifest), args.pg_restore, secret)
        except BackupError as exc:
            result = {'ok': False, 'code': exc.code, 'message': str(exc)}
        _print(result)
        return 0 if result['ok'] else 1
    settings = load_settings()
    # Restored blobs were accepted once; today's upload limit does not apply to them.
    store = (LocalObjectStore(settings.storage_root) if settings.storage_backend == 'local'
             else build_store(settings))
    try:
        ledger = (json.loads(Path(args.deletion_ledger).read_text('utf-8'))
                  if args.deletion_ledger else None)
        secret = (settings.backup_encryption_key.get_secret_value()
                  if settings.backup_encryption_key else None)
        report = restore(Path(args.manifest), _owner_database(settings), store, args.confirm,
                         args.pg_restore, ledger, secret)
    except BackupError as exc:
        _print({'ok': False, 'code': exc.code, 'message': str(exc), 'details': exc.details})
        return 1
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                     encoding='utf-8')
    _print({'ok': True, **report})
    return 0


def curate(args) -> int:
    """Definition curation by the outside model (knowledge/curation.py); people approve in the UI."""
    import uuid

    from .auth.service import Principal
    from .core.db import make_engine
    from .knowledge import curation
    from .rag.llm import LLMError
    settings = load_settings()
    engine = make_engine(settings.runtime_database_url)
    with engine.begin() as conn:
        user = conn.execute(text(
            "SELECT id, email, role FROM users WHERE email = :e AND enabled"
            " AND role IN ('reviewer', 'admin')"), {'e': args.as_user}).mappings().first()
    if user is None:
        _print({'ok': False, 'code': 'USER_NOT_FOUND',
                'message': 'run as an enabled reviewer or admin (--as)'})
        return 2
    principal = Principal(user['id'], user['email'], user['role'], uuid.UUID(int=0), '')
    try:
        report = curation.run(engine, principal, settings, tuple(args.steps.split(',')),
                              args.school, args.book, args.units, args.max_calls, args.name,
                              args.refresh, args.dry_run)
    except LLMError as exc:
        _print({'ok': False, 'code': exc.code, 'message': str(exc)})
        return 2
    _print({'ok': not report.get('errors'), **report})
    return 0


def rag_command(args) -> int:
    from .rag import admin
    if args.command == 'fetch-models':
        _print(admin.fetch_models(ocr_only=args.ocr_only))
    elif args.command == 'rag-setup':
        _print(admin.rag_setup())
    elif args.command == 'ingest-folder':
        _print(admin.ingest_folder(Path(args.root), args.admin, args.pipeline_profile, args.only,
                                   not args.no_auto_publish))
    else:
        password = _password(JUDGE_PASSWORD_ENV)
        print(admin.judge_password_hash(password))
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
    back.add_argument('--prune', action='store_true', help='then apply the retention policy')
    back.add_argument('--keep-daily', type=int, default=7)
    back.add_argument('--keep-weekly', type=int, default=4)
    pre = commands.add_parser('restore-preflight', help='verify a backup without restoring')
    pre.add_argument('--manifest', required=True)
    pre.add_argument('--pg-restore', default='pg_restore')
    rest = commands.add_parser('restore', help='restore into an EMPTY database and store')
    rest.add_argument('--manifest', required=True)
    rest.add_argument('--confirm', required=True, help='the backup name, typed again')
    rest.add_argument('--report', help='also write the restore report to this file')
    rest.add_argument('--pg-restore', default='pg_restore')
    rest.add_argument('--deletion-ledger', help='ledger exported from the live system; erasures'
                      ' made after the backup are applied again')
    led = commands.add_parser('deletion-ledger', help='export erasures for a later restore')
    led.add_argument('--out', required=True)
    ev = commands.add_parser('evaluate', help='retrieval run with gates and regression check')
    ev.add_argument('--dataset', required=True)
    ev.add_argument('--version', required=True)
    ev.add_argument('--as', dest='as_user', required=True, help='a reviewer or admin email')
    ev.add_argument('--split', choices=('dev', 'test', 'holdout'))
    ev.add_argument('--strategy', default='hybrid_rerank',
                    choices=('lexical', 'vector', 'hybrid', 'hybrid_rerank'))
    ev.add_argument('--top-k', type=int, default=20)
    ev.add_argument('--baseline', help="'latest' (same strategy and split) or a run id")
    ev.add_argument('--tolerance', type=float, default=0.02)
    ev.add_argument('--gates', action='store_true', help='also fail when a release gate fails')
    glo = commands.add_parser('load-glossary', help='load the reviewed term list (concepts, aliases)')
    glo.add_argument('--as', dest='as_user', required=True, help='the reviewer or admin who reviewed it')
    glo.add_argument('--file', help='default: backend/app/knowledge/data/glossary_v1.json')
    glo.add_argument('--publish', action='store_true',
                     help='then publish an ontology release (repins the corpus)')
    cur = commands.add_parser('curate', help='draft and check definitions with the curator model')
    cur.add_argument('--as', dest='as_user', required=True, help='a reviewer or admin email')
    cur.add_argument('--steps', default='discover,compose,review',
                     help='comma list of discover, compose, review')
    cur.add_argument('--school', choices=('tu_binh', 'manh_phai'))
    cur.add_argument('--book', help='only books whose title contains this')
    cur.add_argument('--units', type=int, help='read at most this many sections')
    cur.add_argument('--name', action='append', help='compose only this concept name (repeatable)')
    cur.add_argument('--max-calls', type=int, default=200, help='model calls this run may make')
    cur.add_argument('--refresh', action='store_true', help='compose again even when unchanged')
    cur.add_argument('--dry-run', action='store_true', help='count sections and tokens, call nothing')
    fetch = commands.add_parser('fetch-models', help='download the pinned RAG/OCR models (network)')
    fetch.add_argument('--ocr-only', action='store_true',
                       help='only SenOCR-Vi and its layout model (remote OCR server)')
    commands.add_parser('rag-setup', help='RAG pilot embedding profile, collection, pipeline')
    ingest = commands.add_parser('ingest-folder', help='upload every PDF/DOCX of a folder tree')
    ingest.add_argument('root', help='folder whose sub-folders name the school')
    ingest.add_argument('--admin', required=True, help='admin email that approves the schools')
    ingest.add_argument('--pipeline-profile', help='default: latest "RAG pilot" profile')
    ingest.add_argument('--only', nargs='*', help='file name fragments to include')
    ingest.add_argument('--no-auto-publish', action='store_true')
    commands.add_parser('judge-password', help='print the Argon2 hash of a judge password'
                        f' (read from {JUDGE_PASSWORD_ENV} or a prompt)')
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
        if args.command in ('fetch-models', 'rag-setup', 'ingest-folder', 'judge-password'):
            return rag_command(args)
        if args.command == 'pipeline-profile':
            return pipeline_profile(args)
        if args.command == 'backup':
            return run_backup(args)
        if args.command in ('restore', 'restore-preflight'):
            return run_restore(args)
        if args.command == 'evaluate':
            return run_evaluate(args)
        if args.command == 'load-glossary':
            return load_glossary(args)
        if args.command == 'curate':
            return curate(args)
        if args.command == 'deletion-ledger':
            from .ops.backup import export_ledger
            ledger = export_ledger(_owner_database(load_settings()))
            Path(args.out).write_text(json.dumps(ledger, indent=1), encoding='utf-8')
            _print({'ok': True, 'entries': len(ledger['entries']), 'path': args.out})
            return 0
        return create_runtime_login()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == '__main__':
    raise SystemExit(main())
