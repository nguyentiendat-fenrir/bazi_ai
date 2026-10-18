#!/usr/bin/env python3
"""Synthetic capacity benchmark (docs/13 · PERF01–PERF03; T051) on a throwaway database.

    BAZI_TEST_DATABASE_URL="host=127.0.0.1 port=55432 dbname=postgres user=... password=..." \
        python scripts/bench.py --docs 10 --pages 3 --concurrency 1 10 --repeats 3

PERF01 startup: app factory, first live/ready. PERF02 ingest: N distinct synthetic PDFs
uploaded through the API, processed by one in-process worker (no OCR, fixture embedding),
then published; per-document latency, pages/s, database and object-store growth.
PERF03 query: concurrent /search clients against the published corpus after a warmup,
repeated; p50/p95 latency and throughput per level.

Numbers are synthetic and machine-specific: the report records the machine, the models
(fixture) and that no OCR or real model ran. They are not a user SLA. The database is
created on the *test* server and dropped at the end; nothing touches the dev database.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import time
import uuid
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('e2e_stack', ROOT / 'scripts' / 'e2e_stack.py')
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)

OUT_DIR = ROOT / '.artifacts' / 'bench'
WORK_DIR = ROOT / '.cache' / 'bench'


def pct(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(share * len(ordered)) - 1)], 1)


def folder_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file()) if path.exists() else 0


def machine() -> dict:
    info = {'platform': platform.platform(), 'python': platform.python_version(),
            'cpus': os.cpu_count()}
    try:
        import psutil  # optional
        info['ram_bytes'] = psutil.virtual_memory().total
    except ImportError:
        info['ram_bytes'] = None
    return info


def synthetic_pdfs(target: Path, docs: int, pages: int) -> list[Path]:
    from tests.fixtures.pdf_factory import PdfBuilder
    target.mkdir(parents=True, exist_ok=True)
    topics = ['THỰC THẦN', 'THƯƠNG QUAN', 'CHÍNH TÀI', 'THẤT SÁT', 'ẤN TINH', 'TỶ KIẾP']
    made = []
    for d in range(docs):
        builder = PdfBuilder()
        for p in range(pages):
            topic = topics[(d + p) % len(topics)]
            builder.page(lines=[(f'CHƯƠNG {p + 1}: {topic} {d}', 72, 720, 18, stack.BLACK),
                                (f'Tài liệu tổng hợp {d} trang {p + 1}: {topic.lower()} gặp tài'
                                 f' tinh thì luận theo cách cục, ví dụ số {d * 1000 + p}.',
                                 72, 680, 11, stack.BLACK),
                                ('Giáp Tý, Bính Dần, Mậu Thìn, Canh Ngọ là bốn trụ minh họa.',
                                 72, 640, 11, stack.BLACK)])
        made.append(builder.save(target / f'bench-{d:04d}.pdf'))
    return made


def client_for(app, email: str):
    from fastapi.testclient import TestClient
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        client = TestClient(app, client=('127.0.0.1', 40100))
    login = client.post('/api/v1/auth/login', json={'email': email, 'password': stack.PASSWORD})
    client.headers['X-CSRF-Token'] = login.json()['data']['csrf_token']
    return client


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--docs', type=int, default=10)
    parser.add_argument('--pages', type=int, default=3)
    parser.add_argument('--concurrency', type=int, nargs='+', default=[1, 10])
    parser.add_argument('--queries', type=int, default=30, help='queries per level and repeat')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args(argv)
    if not stack.ADMIN_URL:
        print('Set BAZI_TEST_DATABASE_URL (test PostgreSQL server) first.', file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.WARNING)

    from unittest.mock import patch

    import psycopg
    from sqlalchemy import text

    from backend.app.core.config import load_settings
    from backend.app.ingestion import outbox
    from backend.app.ingestion.ocr import OcrUnavailable
    from backend.app.ingestion.ocr_stage import OcrStage
    from backend.app.ingestion.pipeline import handlers_for
    from backend.app.ingestion.worker import run_job
    from backend.app.main import create_app
    from backend.app.storage.local import LocalObjectStore

    shutil.rmtree(WORK_DIR, ignore_errors=True)
    report: dict = {'started_at': datetime.now(timezone.utc).isoformat(), 'machine': machine(),
                    'conditions': {'ocr': False, 'embedding': 'fixture-hashing (32 dim, CPU)',
                                   'llm': None, 'worker': 'one in-process thread',
                                   'transport': 'in-process ASGI client (no network)',
                                   'documents': 'synthetic PDFs, not books'},
                    'args': vars(args)}
    name, role, runtime = stack.create_stack_database()
    try:
        state = stack.seed(name)
        with patch.dict(os.environ, {'LOG_LEVEL': 'WARNING',
                                     'FIELD_ENCRYPTION_KEY': uuid.uuid4().hex * 2}, clear=True):
            settings = load_settings(_env_file=None)
        engine = stack.engine_for(runtime)
        store = LocalObjectStore(WORK_DIR / 'objects')

        # PERF01 — startup
        started = time.perf_counter()
        app = create_app(settings, engine=engine, store=store)
        built = time.perf_counter()
        admin = client_for(app, state['users']['admin']['email'])
        live = admin.get('/api/v1/health/live')
        first_live = time.perf_counter()
        ready = admin.get('/api/v1/health/ready')
        report['perf01_startup'] = {
            'create_app_ms': round((built - started) * 1000, 1),
            'first_live_ms': round((first_live - built) * 1000, 1),
            'ready_ms': round((time.perf_counter() - first_live) * 1000, 1),
            'live_status': live.status_code, 'ready_status': ready.status_code}

        # PERF02 — ingest
        reviewer = client_for(app, state['users']['reviewer']['email'])
        files = synthetic_pdfs(WORK_DIR / 'pdfs', args.docs, args.pages)

        def db_bytes() -> int:
            with psycopg.connect(stack.database_url(name)) as conn:
                return conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]

        before = {'db': db_bytes(), 'objects': folder_bytes(WORK_DIR / 'objects')}
        batch = reviewer.post('/api/v1/ingestion-batches', json={
            'name': 'bench', 'pipeline_profile_id': state['pipeline_profile_id'],
            'auto_publish': False}).json()['data']
        handlers = [OcrStage(engine_factory=lambda: (_ for _ in ()).throw(
            OcrUnavailable('benchmark without OCR'))) if h.name == 'ocr' else h
            for h in handlers_for(None)]
        broker = stack.InlineBroker()
        per_doc, jobs = [], []
        ingest_started = time.perf_counter()
        for path in files:
            t0 = time.perf_counter()
            with path.open('rb') as handle:
                uploaded = reviewer.post('/api/v1/uploads', headers={
                    'Idempotency-Key': uuid.uuid4().hex}, data={
                    'batch_id': batch['id'], 'rights_status': 'private_reference',
                    'title': path.stem, 'edition_label': 'bench', 'language': 'vi',
                    'external_processing_allowed': 'false'},
                    files={'file': (path.name, handle, 'application/pdf')})
            if uploaded.status_code != 201:
                raise SystemExit(f'upload failed: {uploaded.status_code} {uploaded.text}')
            outbox.dispatch(engine, broker)
            while not broker.jobs.empty():
                job = broker.jobs.get()
                run_job(engine, store, uuid.UUID(job), handlers, 'bench-worker')
            jobs.append(uploaded.json()['data']['job_id'])
            per_doc.append((time.perf_counter() - t0) * 1000)
        ingest_seconds = time.perf_counter() - ingest_started
        states = [reviewer.get(f'/api/v1/jobs/{j}').json()['data']['state'] for j in jobs]
        published = 0
        for job in jobs:
            generation = reviewer.get(f'/api/v1/jobs/{job}').json()['data']['generation_id']
            done = reviewer.post(f'/api/v1/generations/{generation}/publish', json={
                'activate': True}, headers={'Idempotency-Key': uuid.uuid4().hex})
            published += done.status_code == 201
        after = {'db': db_bytes(), 'objects': folder_bytes(WORK_DIR / 'objects')}
        pages = args.docs * args.pages
        report['perf02_ingest'] = {
            'documents': args.docs, 'pages': pages,
            'job_states': {s: states.count(s) for s in set(states)}, 'published': published,
            'seconds': round(ingest_seconds, 2), 'pages_per_second': round(pages / ingest_seconds, 2),
            'per_document_ms': {'p50': pct(per_doc, 0.5), 'p95': pct(per_doc, 0.95)},
            'growth_bytes': {'database': after['db'] - before['db'],
                             'objects': after['objects'] - before['objects']},
            'per_page_bytes': {'database': round((after['db'] - before['db']) / pages),
                               'objects': round((after['objects'] - before['objects']) / pages)}}

        # PERF03 — concurrent queries
        queries = ['thực thần sinh tài', 'thuong quan', 'chính tài cách cục', 'thất sát',
                   'ấn tinh', 'giáp tý bính dần']
        readers = [client_for(app, state['users']['reader']['email'])
                   for _ in range(max(args.concurrency))]

        def one(i: int) -> float:
            t0 = time.perf_counter()
            response = readers[i % len(readers)].post('/api/v1/search', json={
                'query': queries[i % len(queries)], 'rerank': False})
            if response.status_code != 200:
                raise RuntimeError(response.text)
            return (time.perf_counter() - t0) * 1000

        for i in range(len(queries)):                         # warmup
            one(i)
        levels = []
        for level in args.concurrency:
            runs = []
            for _ in range(args.repeats):
                t0 = time.perf_counter()
                with ThreadPoolExecutor(max_workers=level) as pool:
                    latencies = list(pool.map(one, range(args.queries)))
                wall = time.perf_counter() - t0
                runs.append({'p50_ms': pct(latencies, 0.5), 'p95_ms': pct(latencies, 0.95),
                             'throughput_qps': round(args.queries / wall, 1)})
            levels.append({'concurrency': level, 'repeats': runs,
                           'median_p95_ms': statistics.median(r['p95_ms'] for r in runs)})
        report['perf03_query'] = {'queries_per_repeat': args.queries, 'levels': levels}
        with engine.connect() as conn:
            report['corpus'] = {'chunks': conn.execute(text(
                'SELECT count(*) FROM generation_chunks')).scalar_one()}
        engine.dispose()
    finally:
        stack.drop_stack_database(name, role)
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"bench-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=1, ensure_ascii=False))
    print(f'report: {out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
