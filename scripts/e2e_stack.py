#!/usr/bin/env python3
"""Throwaway backend for frontend E2E (docs/13 · Frontend E2E): real API, real PostgreSQL.

    BAZI_TEST_DATABASE_URL="host=127.0.0.1 port=55432 dbname=postgres user=... password=..." \
        python scripts/e2e_stack.py --port 8765 --origin http://127.0.0.1:3100

Creates database ``bazi_e2e_<hex>`` on the *test* server (never the dev database), a
runtime login, three users (admin/reviewer/reader) with a fixed test password, a fixture
embedding + pipeline profile and synthetic PDFs, then serves the API with uvicorn while a
background thread runs queued ingestion jobs (no Redis/Celery; OCR disabled so scans
always become review items). Leftovers of killed runs are dropped at the next start.
Connection details for the tests go to ``.cache/e2e/stack.json``; no secret is printed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from tests.integration.db import ADMIN_URL, alembic, database_url, engine_for, sha  # noqa: E402

PREFIX = 'bazi_e2e_'
PASSWORD = 'e2e correct horse battery staple'
STATE_DIR = ROOT / '.cache' / 'e2e'
BLACK = (0, 0, 0)
log = logging.getLogger('bazi.e2e')


def drop_leftovers() -> None:
    """Databases and roles of earlier runs that were killed before cleaning up."""
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        for (name,) in admin.execute('SELECT datname FROM pg_database WHERE datname LIKE %s',
                                     (PREFIX + '%',)).fetchall():
            admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)')
                          .format(sql.Identifier(name)))
        for (role,) in admin.execute('SELECT rolname FROM pg_roles WHERE rolname LIKE %s',
                                     (PREFIX + 'rt_%',)).fetchall():
            admin.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))


def create_stack_database() -> tuple[str, str, str]:
    """(database, runtime role, runtime conninfo) for a migrated, empty database."""
    name = f'{PREFIX}{uuid.uuid4().hex[:10]}'
    role, password = f'{PREFIX}rt_{uuid.uuid4().hex[:8]}', uuid.uuid4().hex
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    alembic(name, 'upgrade', 'head')
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}')
                      .format(sql.Identifier(role), sql.Literal(password)))
        admin.execute(sql.SQL('GRANT bazi_runtime TO {}').format(sql.Identifier(role)))
    info = psycopg.conninfo.conninfo_to_dict(ADMIN_URL)
    info.update(dbname=name, user=role, password=password)
    return name, role, psycopg.conninfo.make_conninfo(**info)


def drop_stack_database(name: str, role: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))


def seed(name: str) -> dict:
    """Users and a provisioned fixture pipeline; returns what the tests need to know."""
    from backend.app.auth.service import create_user
    from backend.app.retrieval.models import provision_collection, register_profile

    owner = engine_for(database_url(name))
    users = {}
    with owner.begin() as conn:
        for role in ('admin', 'reviewer', 'reader'):
            user = create_user(conn, f'{role}@e2e.test', PASSWORD, role)
            users[role] = {'id': str(user['id']), 'email': user['email']}
        profile = register_profile(conn, 'fixture-hashing', 'e2e-hash', 'r1', 32,
                                   {'locality': 'local'})
    with psycopg.connect(database_url(name), autocommit=True) as conn:
        provision_collection(conn, profile)
        pipeline = conn.execute(
            "INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
            " normalizer_version, embedding_profile_id, config_hash) VALUES"
            " ('E2E fixture', 'e2e', '1', '1', %s, %s) RETURNING id",
            (profile.id, sha(uuid.uuid4().hex))).fetchone()[0]
    owner.dispose()
    return {'users': users, 'password': PASSWORD, 'pipeline_profile_id': str(pipeline),
            'embedding_profile_id': str(profile.id)}


def fixtures(target: Path) -> dict:
    """Synthetic books (no real book content): one clean, one with a scanned page."""
    from tests.fixtures.pdf_factory import PdfBuilder

    target.mkdir(parents=True, exist_ok=True)
    titles = ['THỂ DỤNG', 'CÁCH CỤC', 'ĐẠI VẬN']

    def book(file: str, tag: str, pages: int, scan: bool) -> str:
        builder = PdfBuilder()
        for n in range(pages):
            builder.page(lines=[(f'CHƯƠNG {n + 1}: {titles[n % len(titles)]}', 72, 720, 18, BLACK),
                                (f'Sách {tag} trang {n + 1}: thực thần sinh tài, thương quan kiến quan.',
                                 72, 680, 11, BLACK),
                                (f'Giáp Tý, Bính Dần, Mậu Thìn là ví dụ {tag} {n + 1}.', 72, 600, 11,
                                 BLACK)])
        if scan:
            builder.page(image=(0, 0, 612, 792))
        return str(builder.save(target / file))

    corrupt = target / 'hong.pdf'                    # PDF magic, unreadable body
    corrupt.write_bytes(b'%PDF-1.7' + bytes([10]) + b'garbage ' * 64)
    not_pdf = target / 'khong-phai-pdf.pdf'          # wrong bytes behind a .pdf name
    not_pdf.write_bytes('Đây chỉ là văn bản, không phải PDF.'.encode('utf-8'))
    # Distinct bytes per file: the same file twice is a duplicate by design.
    return {'clean_a': book('sach-mau-a.pdf', 'mẫu A', 3, False),
            'clean_b': book('sach-mau-b.pdf', 'mẫu B', 3, False),
            'clean_c': book('sach-mau-c.pdf', 'mẫu C', 2, False),
            'scan': book('sach-co-trang-quet.pdf', 'có trang quét', 2, True),
            'corrupt': str(corrupt), 'not_pdf': str(not_pdf)}


class InlineBroker:
    """Outbox → in-process queue; the worker thread below plays the Celery worker."""

    def __init__(self):
        self.jobs: queue.Queue[str] = queue.Queue()

    def send(self, topic: str, payload: dict, event_id) -> None:
        if payload.get('job_id'):
            self.jobs.put(payload['job_id'])


def run_worker(engine, store, broker: InlineBroker, stop: threading.Event) -> None:
    from backend.app.ingestion import outbox, watchdog
    from backend.app.ingestion.ocr import OcrUnavailable
    from backend.app.ingestion.ocr_stage import OcrStage
    from backend.app.ingestion.pipeline import handlers_for
    from backend.app.ingestion.worker import run_job
    from backend.app.reasoning.worker import work_once as answer_once

    def no_ocr():
        raise OcrUnavailable('OCR is disabled in the E2E stack')

    handlers = [OcrStage(engine_factory=no_ocr) if h.name == 'ocr' else h
                for h in handlers_for(None)]
    last_sweep = 0.0
    while not stop.is_set():
        try:
            if time.monotonic() - last_sweep > 5:
                watchdog.sweep(engine)
                last_sweep = time.monotonic()
            outbox.dispatch(engine, broker)
            try:
                job = broker.jobs.get(timeout=0.3)
            except queue.Empty:
                answer_once(engine)              # chat runs when no ingestion job waits
                continue
            run_job(engine, store, uuid.UUID(job), handlers, 'e2e-worker')
        except Exception:  # noqa: BLE001 - keep serving; the test shows the failure
            log.exception('e2e worker pass failed')
            time.sleep(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--origin', action='append', default=[],
                        help='frontend origin allowed for unsafe requests (repeatable)')
    parser.add_argument('--cleanup', action='store_true', help='drop leftovers and exit')
    args = parser.parse_args(argv)
    if not ADMIN_URL:
        print('Set BAZI_TEST_DATABASE_URL (test PostgreSQL server) first.', file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.WARNING)
    drop_leftovers()
    if args.cleanup:
        return 0

    from unittest.mock import patch

    import uvicorn

    from backend.app.core.config import load_settings
    from backend.app.main import create_app
    from backend.app.storage.local import LocalObjectStore

    shutil.rmtree(STATE_DIR, ignore_errors=True)
    name, role, runtime = create_stack_database()
    stop = threading.Event()
    try:
        state = seed(name)
        state['fixtures'] = fixtures(STATE_DIR / 'fixtures')
        state['api'] = f'http://127.0.0.1:{args.port}'
        origins = args.origin or ['http://127.0.0.1:3100']
        with patch.dict(os.environ, {'ALLOWED_ORIGINS': json.dumps(origins),
                                     'LOG_LEVEL': 'WARNING',
                                     'FIELD_ENCRYPTION_KEY': uuid.uuid4().hex * 2},
                        clear=True):
            settings = load_settings(_env_file=None)
        engine = engine_for(runtime)
        store = LocalObjectStore(STATE_DIR / 'objects')
        app = create_app(settings, engine=engine, store=store)
        broker = InlineBroker()
        threading.Thread(target=run_worker, args=(engine, store, broker, stop),
                         daemon=True).start()
        (STATE_DIR / 'stack.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
        print(f'E2E stack: database {name}, API {state["api"]}', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
    finally:
        stop.set()
        drop_stack_database(name, role)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
