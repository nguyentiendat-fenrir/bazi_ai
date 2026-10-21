"""Human judging of RAG answers: judge sessions, evaluation runs, score sheets.

Judges have no accounts: they share one password (its Argon2 hash is
``JUDGE_PASSWORD_HASH``) and give a display name. A successful sign-in returns
an HMAC-signed cookie ``{name, exp}`` scoped to ``/api/v1/judge``; that cookie
is accepted by the judge routes only, so a judge can read evaluation runs and
write score sheets but nothing else in the application.

A score sheet is one per (result, judge name): a later save replaces it.
Chunks a judge marks "has a rule worth reviewing" become ``JUDGE_SUGGESTED_RULE``
review items for the experts (reviewer accounts), carrying the chunk, the
question and the judge's note — the judge never touches knowledge itself.
"""
from __future__ import annotations

import base64
import csv
from dataclasses import dataclass
import hashlib
import hmac
import io
import json
import os
import time

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.passwords import verify_password
from ..core.errors import AppError

COOKIE = 'bazi_judge'
COOKIE_PATH = '/api/v1/judge'      # behind settings.public_base_path in the browser
_PROCESS_KEY = os.urandom(32)       # dev without SESSION_SIGNING_KEY: sessions die on restart
SCORE_KEYS = 20


@dataclass(frozen=True)
class Judge:
    name: str
    expires: int


def _key(settings) -> bytes:
    secret = settings.session_signing_key
    return hashlib.sha256(b'judge:' + (secret.get_secret_value().encode() if secret
                                        else _PROCESS_KEY)).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def sign_in(settings, password: str, name: str) -> str:
    stored = settings.judge_password_hash.get_secret_value() if settings.judge_password_hash else None
    if stored is None:
        raise AppError(503, 'JUDGING_DISABLED', 'Judging is not configured on this server')
    if not verify_password(stored, password):
        raise AppError(401, 'AUTH_REQUIRED', 'Wrong judge password')
    payload = json.dumps({'n': name, 'e': int(time.time()) + settings.judge_session_hours * 3600},
                         ensure_ascii=False).encode()
    signature = hmac.new(_key(settings), payload, hashlib.sha256).digest()
    return f'{_b64(payload)}.{_b64(signature)}'


def judge_from(settings, token: str | None) -> Judge | None:
    if not token or '.' not in token:
        return None
    try:
        payload_part, signature_part = token.split('.', 1)
        payload = _unb64(payload_part)
        expected = hmac.new(_key(settings), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature_part)):
            return None
        data = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if int(data.get('e', 0)) < time.time():
        return None
    return Judge(str(data.get('n', ''))[:80], int(data['e']))


# ---- runs ------------------------------------------------------------------------------------

def create_run(conn: Connection, user_id, body: dict) -> dict:
    run_id = conn.execute(text(
        'INSERT INTO eval_runs (label, questions_file, settings, versions, created_by)'
        ' VALUES (:l, :q, CAST(:s AS jsonb), CAST(:v AS jsonb), :u) RETURNING id'),
        {'l': body['label'], 'q': body.get('questions_file'),
         's': json.dumps(body.get('settings') or {}, ensure_ascii=False),
         'v': json.dumps(body.get('versions') or {}, ensure_ascii=False), 'u': user_id}).scalar_one()
    for result in body['results']:
        payload = result['payload']
        conn.execute(text(
            'INSERT INTO eval_results (run_id, ordinal, question_key, question, status, answer,'
            ' latency_ms, payload) VALUES (:r, :o, :k, :q, :s, :a, :ms, CAST(:p AS jsonb))'),
            {'r': run_id, 'o': result['ordinal'], 'k': result['question_key'],
             'q': result['question'], 's': payload.get('status') or 'request_failed',
             'a': payload.get('answer'), 'ms': result.get('latency_ms'),
             'p': json.dumps(payload, ensure_ascii=False)})
    return {'id': str(run_id), 'results': len(body['results'])}


def list_runs(conn: Connection, judge_name: str) -> list[dict]:
    rows = conn.execute(text(
        'SELECT r.id, r.label, r.created_at, r.settings, r.versions,'
        ' (SELECT count(*) FROM eval_results x WHERE x.run_id = r.id) AS results,'
        ' (SELECT count(*) FROM judge_scores s JOIN eval_results x ON x.id = s.result_id'
        '  WHERE x.run_id = r.id AND s.judge_name = :j) AS scored_by_me,'
        ' (SELECT count(DISTINCT s.judge_name) FROM judge_scores s JOIN eval_results x'
        '  ON x.id = s.result_id WHERE x.run_id = r.id) AS judges'
        ' FROM eval_runs r ORDER BY r.created_at DESC LIMIT 100'), {'j': judge_name}).mappings()
    return [{**dict(r), 'id': str(r['id'])} for r in rows]


def list_results(conn: Connection, run_id, judge_name: str) -> list[dict]:
    rows = conn.execute(text(
        'SELECT x.id, x.ordinal, x.question_key, x.question, x.status, x.latency_ms,'
        ' EXISTS (SELECT 1 FROM judge_scores s WHERE s.result_id = x.id AND s.judge_name = :j)'
        ' AS scored_by_me, (SELECT count(*) FROM judge_scores s WHERE s.result_id = x.id) AS scores'
        ' FROM eval_results x WHERE x.run_id = :r ORDER BY x.ordinal'),
        {'r': run_id, 'j': judge_name}).mappings()
    return [{**dict(r), 'id': str(r['id'])} for r in rows]


def get_result(conn: Connection, result_id, judge_name: str) -> dict:
    row = conn.execute(text(
        'SELECT x.id, x.run_id, x.ordinal, x.question_key, x.question, x.status, x.latency_ms,'
        ' x.payload FROM eval_results x WHERE x.id = :id'), {'id': result_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Result not found')
    mine = conn.execute(text(
        'SELECT scores, chunk_labels, notes, updated_at FROM judge_scores'
        ' WHERE result_id = :id AND judge_name = :j'), {'id': result_id, 'j': judge_name}
    ).mappings().first()
    return {**dict(row), 'id': str(row['id']), 'run_id': str(row['run_id']),
            'my_score': dict(mine) if mine else None}


def _check_scores(scores: dict) -> None:
    if len(scores) > SCORE_KEYS:
        raise AppError(422, 'VALIDATION_ERROR', 'too many score fields')
    for key, value in scores.items():
        if not isinstance(key, str) or len(key) > 40:
            raise AppError(422, 'VALIDATION_ERROR', 'invalid score field name')
        if value is not None and not isinstance(value, bool) and not (
                isinstance(value, int) and 1 <= value <= 5):
            raise AppError(422, 'VALIDATION_ERROR', f'{key}: use 1–5, true/false or null')


def save_score(conn: Connection, result_id, judge_name: str, body: dict) -> dict:
    _check_scores(body.get('scores') or {})
    result = conn.execute(text('SELECT question, payload FROM eval_results WHERE id = :id'),
                          {'id': result_id}).mappings().first()
    if result is None:
        raise AppError(404, 'NOT_FOUND', 'Result not found')
    labels = body.get('chunk_labels') or {}
    known = {c['chunk_id'] for c in result['payload'].get('children', [])}
    if set(labels) - known:
        raise AppError(422, 'VALIDATION_ERROR', 'chunk_labels name chunks not in this result')
    for label in labels.values():
        if label.get('relevance') not in (None, 'relevant', 'partial', 'irrelevant'):
            raise AppError(422, 'VALIDATION_ERROR', 'relevance is relevant, partial or irrelevant')
    conn.execute(text(
        'INSERT INTO judge_scores (result_id, judge_name, scores, chunk_labels, notes)'
        ' VALUES (:r, :j, CAST(:s AS jsonb), CAST(:c AS jsonb), :n)'
        ' ON CONFLICT (result_id, judge_name) DO UPDATE SET scores = EXCLUDED.scores,'
        ' chunk_labels = EXCLUDED.chunk_labels, notes = EXCLUDED.notes'),
        {'r': result_id, 'j': judge_name, 's': json.dumps(body.get('scores') or {}),
         'c': json.dumps(labels, ensure_ascii=False), 'n': body.get('notes') or ''})
    suggested = [cid for cid, label in labels.items() if label.get('suggest_rule')]
    created = _suggest_rules(conn, result_id, result['question'], judge_name, suggested)
    return {'saved': True, 'rule_suggestions': created}


def _suggest_rules(conn: Connection, result_id, question: str, judge_name: str,
                   chunk_ids: list[str]) -> int:
    created = 0
    for chunk_id in chunk_ids:
        source = conn.execute(text(
            'SELECT gc.generation_id, sp.page_revision_id FROM generation_chunks gc'
            ' JOIN chunk_spans sp ON sp.chunk_id = gc.chunk_id AND sp.ordinal = 0'
            ' WHERE gc.chunk_id = :c ORDER BY gc.generation_id DESC LIMIT 1'),
            {'c': chunk_id}).first()
        if source is None:
            continue
        exists = conn.execute(text(
            "SELECT 1 FROM review_items WHERE reason_code = 'JUDGE_SUGGESTED_RULE'"
            " AND resolution->>'chunk_id' = :c AND state IN ('open', 'in_progress')"),
            {'c': chunk_id}).first()
        if exists:
            continue
        conn.execute(text(
            'INSERT INTO review_items (generation_id, page_revision_id, reason_code, severity,'
            " resolution) VALUES (:g, :p, 'JUDGE_SUGGESTED_RULE', 'info', CAST(:d AS jsonb))"),
            {'g': source[0], 'p': source[1], 'd': json.dumps({
                'chunk_id': chunk_id, 'eval_result_id': str(result_id), 'question': question[:500],
                'suggested_by': judge_name}, ensure_ascii=False)})
        created += 1
    return created


def scores_csv(conn: Connection, run_id) -> str:
    rows = conn.execute(text(
        'SELECT x.ordinal, x.question_key, x.question, x.status, s.judge_name, s.scores,'
        ' s.chunk_labels, s.notes, s.updated_at FROM eval_results x'
        ' JOIN judge_scores s ON s.result_id = x.id WHERE x.run_id = :r'
        ' ORDER BY x.ordinal, s.judge_name'), {'r': run_id}).mappings().all()
    keys = sorted({k for r in rows for k in (r['scores'] or {})})
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['ordinal', 'question_key', 'question', 'status', 'judge', *keys,
                     'chunks_relevant', 'chunks_partial', 'chunks_irrelevant', 'notes', 'updated_at'])
    for r in rows:
        labels = [v.get('relevance') for v in (r['chunk_labels'] or {}).values()]
        writer.writerow([r['ordinal'], r['question_key'], r['question'], r['status'],
                         r['judge_name'], *[(r['scores'] or {}).get(k) for k in keys],
                         labels.count('relevant'), labels.count('partial'),
                         labels.count('irrelevant'), r['notes'], r['updated_at'].isoformat()])
    return out.getvalue()
