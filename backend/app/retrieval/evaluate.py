"""Retrieval evaluation: datasets of questions, runs and metrics (docs/07 · Benchmark, docs/13).

An item asks a question (``input.query`` plus optional filters) and names the
relevant pages (``expected.relevant``: version, physical pages, grade 1–2) or
``expected.no_answer``. A run searches every item as the requesting principal
on the active release and stores per-item results and the means: recall@k
(share of relevant pages found in the top k), hit@k, nDCG@10 with graded gains
(each relevant page counted once), MRR@10, no-answer accuracy and latency.
Numbers mean something only on a dataset an expert approved — every item
signed (``reviewer_id``) — and are reported with the split they ran on.
"""
from __future__ import annotations

import json
import math
import statistics
import time
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from .search import Spec, search

KINDS = ('retrieval', 'no_answer')
CUTOFFS = (5, 10, 20)
MAX_ITEMS = 500


def _dataset_dto(row, items: int) -> dict:
    return {'id': str(row['id']), 'name': row['name'], 'version': row['version'],
            'state': row['state'], 'rights': row['rights'], 'split_manifest': row['split_manifest'],
            'items': items, 'created_at': row['created_at']}


def create_dataset(conn: Connection, name: str, version: str, rights: dict, items: list[dict]) -> dict:
    keys = [i['key'] for i in items]
    if len(set(keys)) != len(keys):
        raise AppError(422, 'VALIDATION_ERROR', 'item keys must be unique')
    for item in items:
        if item['kind'] not in KINDS:
            raise AppError(422, 'VALIDATION_ERROR', f"item {item['key']}: kind {item['kind']}"
                           ' is not evaluated yet')
        expected = item['expected']
        if item['kind'] == 'retrieval' and not expected.get('relevant'):
            raise AppError(422, 'VALIDATION_ERROR', f"item {item['key']}: no relevant pages")
    dataset = conn.execute(text(
        'INSERT INTO evaluation_datasets (name, version, rights, split_manifest) VALUES'
        ' (:n, :v, CAST(:r AS jsonb), CAST(:s AS jsonb)) ON CONFLICT (name, version) DO NOTHING'
        ' RETURNING id, name, version, state, rights, split_manifest, created_at'),
        {'n': name, 'v': version, 'r': json.dumps(rights),
         's': json.dumps({split: sum(1 for i in items if i['split'] == split)
                          for split in ('dev', 'test', 'holdout')})}).mappings().first()
    if dataset is None:
        raise AppError(409, 'CONFLICT', f'dataset {name} {version} exists; publish a new version')
    for item in items:
        conn.execute(text(
            'INSERT INTO evaluation_items (dataset_id, key, kind, input, expected, source_manifest,'
            ' split) VALUES (:d, :k, :kind, CAST(:i AS jsonb), CAST(:e AS jsonb), CAST(:m AS jsonb),'
            ' :s)'),
            {'d': dataset['id'], 'k': item['key'], 'kind': item['kind'],
             'i': json.dumps(item['input'], ensure_ascii=False),
             'e': json.dumps(item['expected'], ensure_ascii=False),
             'm': json.dumps(item.get('source_manifest') or {}, ensure_ascii=False),
             's': item['split']})
    return _dataset_dto(dataset, len(items))


def list_datasets(conn: Connection) -> list[dict]:
    return [_dataset_dto(r, r['items']) for r in conn.execute(text(
        'SELECT d.*, (SELECT count(*) FROM evaluation_items i WHERE i.dataset_id = d.id) AS items'
        " FROM evaluation_datasets d WHERE d.name <> 'rule-fixtures' ORDER BY d.created_at DESC")
    ).mappings()]


def list_items(conn: Connection, dataset_id, limit: int, offset: int) -> list[dict]:
    return [{'id': str(r['id']), 'key': r['key'], 'kind': r['kind'], 'input': r['input'],
             'expected': r['expected'], 'split': r['split'],
             'reviewer_id': str(r['reviewer_id']) if r['reviewer_id'] else None}
            for r in conn.execute(text(
                'SELECT id, key, kind, input, expected, split, reviewer_id FROM evaluation_items'
                ' WHERE dataset_id = :d ORDER BY key LIMIT :l OFFSET :o'),
                {'d': dataset_id, 'l': limit, 'o': offset}).mappings()]


def approve_dataset(conn: Connection, principal: Principal, dataset_id) -> dict:
    """The expert sign-off: every item gets the reviewer, then the dataset is approved."""
    row = conn.execute(text('SELECT id, state FROM evaluation_datasets WHERE id = :d FOR UPDATE'),
                       {'d': dataset_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Dataset not found')
    if row['state'] != 'draft':
        raise AppError(409, 'CONFLICT', f"dataset is {row['state']}")
    conn.execute(text('UPDATE evaluation_items SET reviewer_id = :u WHERE dataset_id = :d'
                      ' AND reviewer_id IS NULL'), {'u': principal.user_id, 'd': dataset_id})
    conn.execute(text("UPDATE evaluation_datasets SET state = 'approved' WHERE id = :d"),
                 {'d': dataset_id})
    return next(d for d in list_datasets(conn) if d['id'] == str(dataset_id))


def _scores(item: dict, result: dict) -> dict:
    expected = item['expected']
    if item['kind'] == 'no_answer' or expected.get('no_answer'):
        return {'no_answer_correct': float(result['status'] != 'ok')}
    relevant = {}
    for entry in expected['relevant']:
        for page in entry['pages']:
            key = (str(entry['book_version_id']), int(page))
            relevant[key] = max(relevant.get(key, 0), int(entry.get('grade', 1)))
    found_order = []                          # relevant pages in the order hits reach them
    gains, first = [], None
    for rank, hit in enumerate(result['hits'], start=1):
        new = [(hit['book_version_id'], p) for p in hit['pages']
               if (hit['book_version_id'], p) in relevant
               and (hit['book_version_id'], p) not in found_order]
        found_order += new
        gains.append(max((relevant[k] for k in new), default=0))
        if new and first is None:
            first = rank
    scores = {}
    for k in CUTOFFS:
        reached = set()
        for hit in result['hits'][:k]:
            reached |= {(hit['book_version_id'], p) for p in hit['pages']} & set(relevant)
        scores[f'recall@{k}'] = len(reached) / len(relevant)
        scores[f'hit@{k}'] = float(bool(reached))
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains[:10]))
    ideal = sum(g / math.log2(i + 2) for i, g in enumerate(sorted(relevant.values(),
                                                                  reverse=True)[:10]))
    scores['ndcg@10'] = dcg / ideal if ideal else 0.0
    scores['mrr@10'] = 1 / first if first and first <= 10 else 0.0
    return scores


def run(conn: Connection, principal: Principal, dataset_id, top_k: int, rerank: bool,
        split: str | None, app_env: str, transports: tuple = (None, None)) -> dict:
    dataset = conn.execute(text('SELECT id, state FROM evaluation_datasets WHERE id = :d'),
                           {'d': dataset_id}).mappings().first()
    if dataset is None:
        raise AppError(404, 'NOT_FOUND', 'Dataset not found')
    items = [dict(r) for r in conn.execute(text(
        'SELECT id, key, kind, input, expected, split FROM evaluation_items WHERE dataset_id = :d'
        ' AND (CAST(:s AS text) IS NULL OR split = :s) ORDER BY key'),
        {'d': dataset_id, 's': split}).mappings()]
    if not items or len(items) > MAX_ITEMS:
        raise AppError(422, 'VALIDATION_ERROR', f'a run evaluates 1-{MAX_ITEMS} items')
    active = conn.execute(text("SELECT release_id FROM active_corpus WHERE slot = 'default'")).scalar()
    config = {'top_k': top_k, 'rerank': rerank, 'split': split, 'release_id': str(active) if active
              else None, 'dataset_state': dataset['state']}
    run_id = conn.execute(text(
        "INSERT INTO evaluation_runs (dataset_id, requested_by, config_snapshot, status)"
        " VALUES (:d, :u, CAST(:c AS jsonb), 'running') RETURNING id"),
        {'d': dataset_id, 'u': principal.user_id, 'c': json.dumps(config)}).scalar_one()
    per_item, latencies = [], []
    for item in items:
        query = item['input']
        spec = Spec(query['query'], max(top_k, 20), query.get('school_ids', []),
                    query.get('book_ids', []), query.get('book_version_ids', []),
                    query.get('topic_ids', []), None, rerank, False)
        started = time.perf_counter()
        result = search(conn, principal, spec, app_env, *transports)
        elapsed = int((time.perf_counter() - started) * 1000)
        latencies.append(elapsed)
        scores = _scores(item, result)
        passed = scores.get('hit@20', scores.get('no_answer_correct', 0.0)) > 0
        actual = {'status': result['status'], 'hits': [
            {'book_version_id': h['book_version_id'], 'pages': h['pages'], 'chunk_id': h['chunk_id']}
            for h in result['hits'][:20]]}
        conn.execute(text(
            'INSERT INTO evaluation_results (run_id, item_id, actual, scores, status, duration_ms)'
            ' VALUES (:r, :i, CAST(:a AS jsonb), CAST(:s AS jsonb), :st, :ms)'),
            {'r': run_id, 'i': item['id'], 'a': json.dumps(actual), 's': json.dumps(scores),
             'st': 'passed' if passed else 'failed', 'ms': elapsed})
        per_item.append(scores)
    metrics = {'items': len(items), 'latency_ms': {
        'p50': statistics.median(latencies),
        'p95': sorted(latencies)[max(0, math.ceil(0.95 * len(latencies)) - 1)]}}
    for name in sorted({k for s in per_item for k in s}):
        values = [s[name] for s in per_item if name in s]
        metrics[name] = round(sum(values) / len(values), 4)
    conn.execute(text("UPDATE evaluation_runs SET status = 'completed', metrics = CAST(:m AS jsonb)"
                      ' WHERE id = :r'), {'r': run_id, 'm': json.dumps(metrics)})
    return get_run(conn, run_id)


def get_run(conn: Connection, run_id) -> dict:
    row = conn.execute(text('SELECT id, dataset_id, config_snapshot, status, metrics, created_at'
                            ' FROM evaluation_runs WHERE id = :r'), {'r': run_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Evaluation run not found')
    results = conn.execute(text(
        'SELECT i.key, r.status, r.scores, r.actual, r.duration_ms FROM evaluation_results r'
        ' JOIN evaluation_items i ON i.id = r.item_id WHERE r.run_id = :r ORDER BY i.key'),
        {'r': run_id}).mappings().all()
    return {'id': str(row['id']), 'dataset_id': str(row['dataset_id']),
            'config': row['config_snapshot'], 'status': row['status'], 'metrics': row['metrics'],
            'created_at': row['created_at'],
            'results': [{'key': r['key'], 'status': r['status'], 'scores': r['scores'],
                         'actual': r['actual'], 'duration_ms': r['duration_ms']} for r in results]}
