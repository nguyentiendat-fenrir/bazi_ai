"""Retrieval evaluation: datasets of questions, runs and metrics (docs/07 · Benchmark, docs/13).

An item asks a question (``input.query`` plus optional filters) and names the
relevant pages (``expected.relevant``: version, physical pages, grade 1–2) or
``expected.no_answer``. A run searches every item as the requesting principal
on the active release and stores per-item results and the means: recall@k
(share of relevant pages found in the top k), hit@k, nDCG@10 with graded gains
(each relevant page counted once), MRR@10, page@1, school leakage (hits outside
the schools an item filters on), no-answer accuracy, precision and recall, and latency.
A strategy picks the channels (lexical, vector, hybrid, hybrid with rerank) so they
can be compared on one release. Each run is checked against the release gates of
docs/07 and, when given a baseline run, against it for regressions (T050).
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
# strategy → (channels, rerank); hybrid is what /search runs.
STRATEGIES = {'lexical': (('lexical', 'section'), False), 'vector': (('vector',), False),
              'hybrid': (None, False), 'hybrid_rerank': (None, True)}
# Release gates (docs/07 · Benchmark): targets, not yet measured on an approved gold set.
GATES = (('recall@20', '>=', 0.90), ('ndcg@10', '>=', 0.75), ('school_leakage', '<=', 0.0))
# Higher is better for these; a drop beyond the tolerance against the baseline regresses.
COMPARED = ('recall@20', 'recall@10', 'hit@10', 'ndcg@10', 'mrr@10', 'page@1',
            'no_answer_correct', 'no_answer_precision', 'no_answer_recall')


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


def _leakage(item: dict, result: dict, school_keys: dict) -> dict:
    """Share of hits outside the schools the item filters on (0 when it does not filter)."""
    allowed = {school_keys.get(str(s)) for s in item['input'].get('school_ids') or []}
    if not allowed or not result['hits']:
        return {}
    outside = [h for h in result['hits'] if h.get('school_key') not in allowed]
    return {'school_leakage': len(outside) / len(result['hits'])}


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
    top = result['hits'][:1]
    scores['page@1'] = float(bool(top) and any((top[0]['book_version_id'], p) in relevant
                                               for p in top[0]['pages']))
    return scores


def gates(metrics: dict) -> list[dict]:
    checks = []
    for metric, op, target in GATES:
        value = metrics.get(metric)
        passed = None if value is None else (value >= target if op == '>=' else value <= target)
        checks.append({'metric': metric, 'op': op, 'target': target, 'value': value,
                       'passed': passed})
    return checks


def compare(metrics: dict, baseline: dict, tolerance: float) -> list[dict]:
    rows = []
    for metric in COMPARED + ('school_leakage',):
        if metric not in metrics or metric not in baseline:
            continue
        delta = round(metrics[metric] - baseline[metric], 4)
        worse = -delta if metric != 'school_leakage' else delta
        rows.append({'metric': metric, 'baseline': baseline[metric], 'value': metrics[metric],
                     'delta': delta, 'regressed': worse > tolerance})
    return rows


def run(conn: Connection, principal: Principal, dataset_id, top_k: int, rerank: bool,
        split: str | None, app_env: str, transports: tuple = (None, None),
        strategy: str | None = None, baseline_run_id=None, tolerance: float = 0.02) -> dict:
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
    if baseline_run_id is not None and conn.execute(text(
            'SELECT 1 FROM evaluation_runs WHERE id = :b AND dataset_id = :d'),
            {'b': baseline_run_id, 'd': dataset_id}).first() is None:
        raise AppError(422, 'VALIDATION_ERROR', 'the baseline must be a run of the same dataset',
                       field_errors=[{'path': 'body.baseline_run_id', 'message': 'unknown run'}])
    channels = None
    if strategy is not None:
        channels, rerank = STRATEGIES[strategy]
    active = conn.execute(text("SELECT release_id FROM active_corpus WHERE slot = 'default'")).scalar()
    config = {'top_k': top_k, 'rerank': rerank, 'split': split, 'release_id': str(active) if active
              else None, 'dataset_state': dataset['state'],
              'strategy': strategy or ('hybrid_rerank' if rerank else 'hybrid'),
              'baseline_run_id': str(baseline_run_id) if baseline_run_id else None,
              'tolerance': tolerance}
    school_keys = {str(i): k for i, k in conn.execute(text('SELECT id, key FROM schools'))}
    run_id = conn.execute(text(
        "INSERT INTO evaluation_runs (dataset_id, requested_by, config_snapshot, status)"
        " VALUES (:d, :u, CAST(:c AS jsonb), 'running') RETURNING id"),
        {'d': dataset_id, 'u': principal.user_id, 'c': json.dumps(config)}).scalar_one()
    per_item, latencies, answered = [], [], []
    for item in items:
        query = item['input']
        spec = Spec(query['query'], max(top_k, 20), query.get('school_ids', []),
                    query.get('book_ids', []), query.get('book_version_ids', []),
                    query.get('topic_ids', []), None, rerank, False, channels)
        started = time.perf_counter()
        result = search(conn, principal, spec, app_env, *transports)
        elapsed = int((time.perf_counter() - started) * 1000)
        latencies.append(elapsed)
        scores = {**_scores(item, result), **_leakage(item, result, school_keys)}
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
        answered.append((result['status'] == 'ok',
                         item['kind'] == 'no_answer' or bool(item['expected'].get('no_answer'))))
    metrics = {'items': len(items), 'latency_ms': {
        'p50': statistics.median(latencies),
        'p95': sorted(latencies)[max(0, math.ceil(0.95 * len(latencies)) - 1)]}}
    for name in sorted({k for s in per_item for k in s}):
        values = [s[name] for s in per_item if name in s]
        metrics[name] = round(sum(values) / len(values), 4)
    # No-answer as a classifier: predicted when search found nothing usable.
    predicted = [expected for ok, expected in answered if not ok]
    expected_no = sum(1 for _, expected in answered if expected)
    if predicted:
        metrics['no_answer_precision'] = round(sum(predicted) / len(predicted), 4)
    if expected_no:
        metrics['no_answer_recall'] = round(sum(predicted) / expected_no, 4)
    conn.execute(text("UPDATE evaluation_runs SET status = 'completed', metrics = CAST(:m AS jsonb)"
                      ' WHERE id = :r'), {'r': run_id, 'm': json.dumps(metrics)})
    return get_run(conn, run_id)


def _summary(conn: Connection, row) -> dict:
    metrics, config = row['metrics'] or {}, row['config_snapshot'] or {}
    comparison = None
    if config.get('baseline_run_id'):
        base = conn.execute(text('SELECT metrics FROM evaluation_runs WHERE id = :b'),
                            {'b': config['baseline_run_id']}).scalar()
        comparison = compare(metrics, base or {}, config.get('tolerance', 0.02))
    return {'id': str(row['id']), 'dataset_id': str(row['dataset_id']), 'config': config,
            'status': row['status'], 'metrics': metrics, 'created_at': row['created_at'],
            'gates': gates(metrics), 'comparison': comparison,
            'regressed': bool(comparison and any(c['regressed'] for c in comparison))}


def list_runs(conn: Connection, dataset_id=None, limit: int = 50) -> list[dict]:
    rows = conn.execute(text(
        'SELECT id, dataset_id, config_snapshot, status, metrics, created_at FROM evaluation_runs'
        ' WHERE CAST(:d AS uuid) IS NULL OR dataset_id = :d ORDER BY created_at DESC, id DESC'
        ' LIMIT :n'), {'d': str(dataset_id) if dataset_id else None, 'n': limit}).mappings().all()
    return [_summary(conn, r) for r in rows]


def get_run(conn: Connection, run_id) -> dict:
    row = conn.execute(text('SELECT id, dataset_id, config_snapshot, status, metrics, created_at'
                            ' FROM evaluation_runs WHERE id = :r'), {'r': run_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Evaluation run not found')
    results = conn.execute(text(
        'SELECT i.key, r.status, r.scores, r.actual, r.duration_ms FROM evaluation_results r'
        ' JOIN evaluation_items i ON i.id = r.item_id WHERE r.run_id = :r ORDER BY i.key'),
        {'r': run_id}).mappings().all()
    return {**_summary(conn, row),
            'results': [{'key': r['key'], 'status': r['status'], 'scores': r['scores'],
                         'actual': r['actual'], 'duration_ms': r['duration_ms']} for r in results]}
