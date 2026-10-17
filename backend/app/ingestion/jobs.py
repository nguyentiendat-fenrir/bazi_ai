"""Ingestion jobs as an API: list, detail, events, retry, cancel, reprocess (docs/05, 10).

A retry is a new child job (``parent_job_id``) on the same generation: units
that succeeded are reused through their idempotency keys, and failed units of
the version get fresh attempts. A reprocess is a new generation of the version;
extraction links each page's newest correction when it descends from the
extracted text (T017), so human fixes survive a full rebuild.
"""
from __future__ import annotations

import base64
from datetime import datetime
import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from ..documents.corrections import ACTIVE_JOB, lock_version
from . import events, queue

RETRYABLE = ('failed', 'partial', 'cancelled')
ERROR_STATES = ('retry_wait', 'failed', 'partial')

JOB_SELECT = (
    'SELECT j.id, j.state, j.counters, j.error, j.generation_id, j.book_version_id, j.batch_id,'
    ' j.parent_job_id, j.pipeline_profile_id, j.created_at, j.updated_at,'
    " (SELECT e.payload->>'stage' FROM job_events e WHERE e.job_id = j.id"
    "  AND e.code = 'STAGE_STARTED' ORDER BY e.seq DESC LIMIT 1) AS stage,"
    " (SELECT (e.payload->>'attempt')::int FROM job_events e WHERE e.job_id = j.id"
    "  AND e.code = 'UNIT_RETRY' ORDER BY e.seq DESC LIMIT 1) AS attempt,"
    ' v.book_id, b.title AS book_title, v.edition_label'
    ' FROM ingestion_jobs j JOIN book_versions v ON v.id = j.book_version_id'
    ' JOIN books b ON b.id = v.book_id')


def job_dto(row) -> dict:
    # A job that recovered keeps its last error row; only show it while it applies.
    error = row['error'] if row['state'] in ERROR_STATES else None
    return {
        'id': str(row['id']), 'state': row['state'], 'stage': row['stage'],
        'counters': row['counters'] or {}, 'attempt': row['attempt'],
        'retry_at': (error or {}).get('retry_at') if row['state'] == 'retry_wait' else None,
        'error': {'code': error.get('code'), 'message': error.get('message'),
                  'retryable': bool(error.get('retryable'))} if error else None,
        'generation_id': str(row['generation_id']), 'book_version_id': str(row['book_version_id']),
        'book_id': str(row['book_id']), 'book_title': row['book_title'],
        'edition_label': row['edition_label'],
        'batch_id': str(row['batch_id']) if row['batch_id'] else None,
        'parent_job_id': str(row['parent_job_id']) if row['parent_job_id'] else None,
        'pipeline_profile_id': str(row['pipeline_profile_id']),
        'created_at': row['created_at'], 'updated_at': row['updated_at']}


def _cursor(created_at: datetime, job_id) -> str:
    return base64.urlsafe_b64encode(f'{created_at.isoformat()}|{job_id}'.encode()).decode()


def list_jobs(conn: Connection, state: str | None, batch_id, book_version_id, limit: int,
              cursor: str | None) -> tuple[list[dict], str | None]:
    clauses, params = [], {'limit': limit + 1}
    for column, value in (('state', state), ('batch_id', batch_id),
                          ('book_version_id', book_version_id)):
        if value is not None:
            clauses.append(f'j.{column} = :{column}')
            params[column] = value
    if cursor:
        try:
            stamp, job = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
            params.update(at=datetime.fromisoformat(stamp), after=uuid.UUID(job))
        except (ValueError, UnicodeDecodeError):
            raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None
        clauses.append('(j.created_at, j.id) < (:at, :after)')
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    rows = conn.execute(text(f'{JOB_SELECT}{where} ORDER BY j.created_at DESC, j.id DESC'
                             ' LIMIT :limit'), params).mappings().all()
    page, more = rows[:limit], len(rows) > limit
    return [job_dto(r) for r in page], (_cursor(page[-1]['created_at'], page[-1]['id'])
                                         if more else None)


def job_view(conn: Connection, job_id) -> dict:
    row = conn.execute(text(f'{JOB_SELECT} WHERE j.id = :j'), {'j': job_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Job not found')
    stages: dict[str, dict] = {}
    for code, payload in conn.execute(text(
            "SELECT code, payload FROM job_events WHERE job_id = :j"
            " AND code IN ('STAGE_STARTED', 'STAGE_DONE') ORDER BY seq"), {'j': job_id}):
        entry = stages.setdefault(payload['stage'], {'stage': payload['stage'], 'units': 0,
                                                     'computed': 0, 'reused': 0, 'done': False})
        if code == 'STAGE_STARTED':
            entry['units'] = payload['units']
        else:
            entry.update(computed=payload['computed'], reused=payload['reused'], done=True)
    children = conn.execute(text('SELECT id FROM ingestion_jobs WHERE parent_job_id = :j'
                                 ' ORDER BY created_at'), {'j': job_id}).scalars().all()
    return {**job_dto(row), 'stages': list(stages.values()),
            'retried_by': [str(c) for c in children]}


def _active(conn: Connection, version_id, profile_id) -> bool:
    return conn.execute(text('SELECT 1 FROM ingestion_jobs WHERE book_version_id = :v AND'
                             ' pipeline_profile_id = :p AND state = ANY(:active)'),
                        {'v': version_id, 'p': profile_id, 'active': ACTIVE_JOB}).first() is not None


def _queue(conn: Connection, actor_id, version_id, generation_id, profile_id, batch_id=None,
           parent_job_id=None):
    job = conn.execute(text(
        'INSERT INTO ingestion_jobs (batch_id, book_version_id, generation_id, pipeline_profile_id,'
        ' parent_job_id, requested_by) VALUES (:b, :v, :g, :p, :parent, :u) RETURNING id'),
        {'b': batch_id, 'v': version_id, 'g': generation_id, 'p': profile_id,
         'parent': parent_job_id, 'u': actor_id}).scalar_one()
    conn.execute(text("INSERT INTO outbox_events (topic, payload) VALUES ('ingestion.job.queued',"
                      ' CAST(:p AS jsonb))'), {'p': json.dumps({'job_id': str(job)})})
    return job


def retry_job(conn: Connection, actor_id, job_id) -> dict:
    job = conn.execute(text('SELECT id, state, book_version_id, generation_id, pipeline_profile_id,'
                            ' batch_id FROM ingestion_jobs WHERE id = :j FOR UPDATE'),
                       {'j': job_id}).mappings().first()
    if job is None:
        raise AppError(404, 'NOT_FOUND', 'Job not found')
    if job['state'] not in RETRYABLE:
        raise AppError(409, 'JOB_NOT_RETRYABLE', f"A {job['state']} job cannot be retried")
    generation = conn.execute(text(
        'SELECT g.state, v.status FROM generations g JOIN book_versions v'
        ' ON v.id = g.book_version_id WHERE g.id = :g'), {'g': job['generation_id']}).one()
    if generation[1] != 'active':
        raise AppError(409, 'VERSION_WITHDRAWN', 'This book version is withdrawn')
    if generation[0] != 'building':
        raise AppError(409, 'GENERATION_CLOSED', f'The generation is {generation[0]}; reprocess'
                       ' the version instead')
    lock_version(conn, job['book_version_id'])
    if _active(conn, job['book_version_id'], job['pipeline_profile_id']):
        raise AppError(409, 'JOB_ACTIVE', 'Another job of this version is active')
    # Units that failed for this version get fresh attempts; succeeded ones are reused.
    reset = conn.execute(text(
        "UPDATE job_stages SET state = 'pending', attempt = 0, lease_until = NULL,"
        " worker_id = NULL WHERE state = 'failed' AND job_id IN (SELECT id FROM ingestion_jobs"
        ' WHERE book_version_id = :v)'), {'v': job['book_version_id']}).rowcount
    child = _queue(conn, actor_id, job['book_version_id'], job['generation_id'],
                   job['pipeline_profile_id'], job['batch_id'], job_id)
    events.log(conn, job_id, 'info', 'RETRIED', {'job_id': str(child), 'reset_units': reset})
    events.log(conn, child, 'info', 'JOB_QUEUED', {'parent_job_id': str(job_id),
                                                   'reset_units': reset})
    return job_view(conn, child)


def cancel_job(conn: Connection, job_id) -> dict:
    state = queue.request_cancel(conn, job_id)
    if state is None:
        raise AppError(404, 'NOT_FOUND', 'Job not found')
    if state in ('cancel_requested', 'cancelled'):
        events.log(conn, job_id, 'warning',
                   'CANCEL_REQUESTED' if state == 'cancel_requested' else 'JOB_CANCELLED',
                   {'by': 'api'})
    return job_view(conn, job_id)


def process_version(conn: Connection, actor_id, version_id, pipeline_profile_id=None) -> dict:
    """Rebuild a version from its source as a new generation (scope: full)."""
    version = conn.execute(text('SELECT status FROM book_versions WHERE id = :v FOR UPDATE'),
                           {'v': version_id}).scalar()
    if version is None:
        raise AppError(404, 'NOT_FOUND', 'Version not found')
    if version != 'active':
        raise AppError(409, 'VERSION_WITHDRAWN', 'This book version is withdrawn')
    profile = pipeline_profile_id or conn.execute(text(
        'SELECT pipeline_profile_id FROM generations WHERE book_version_id = :v'
        ' ORDER BY created_at DESC LIMIT 1'), {'v': version_id}).scalar()
    if profile is None:
        raise AppError(422, 'VALIDATION_ERROR', 'pipeline_profile_id is required for a version'
                       ' that was never processed',
                       field_errors=[{'path': 'body.pipeline_profile_id', 'message': 'required'}])
    if not conn.execute(text('SELECT 1 FROM pipeline_profiles WHERE id = :p'),
                        {'p': profile}).first():
        raise AppError(404, 'NOT_FOUND', 'Pipeline profile not found')
    lock_version(conn, version_id)
    if _active(conn, version_id, profile):
        raise AppError(409, 'JOB_ACTIVE', 'A job of this version is active')
    generation = conn.execute(text(
        'INSERT INTO generations (book_version_id, pipeline_profile_id) VALUES (:v, :p)'
        ' RETURNING id'), {'v': version_id, 'p': profile}).scalar_one()
    job = _queue(conn, actor_id, version_id, generation, profile)
    events.log(conn, job, 'info', 'JOB_QUEUED', {'reason': 'process'})
    return job_view(conn, job)
