"""Durable work state in PostgreSQL: stage leases with fencing tokens (ADR-06).

A worker claims a unit of work (one stage for one page/chunk/batch) and gets a
fencing token. Every write that publishes the unit's result runs in the same
transaction as ``complete`` and fails when the token is no longer current, so
a worker whose lease expired (paused, partitioned, killed) can never publish.
The broker only says "look at job X"; it holds no state that matters.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import random
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

LEASE = timedelta(seconds=180)  # docs/05 starting value; long units heartbeat
MAX_ATTEMPTS = 5
TERMINAL = ('succeeded', 'partial', 'failed', 'cancelled')


class LeaseLost(Exception):
    """The fencing token is stale: another worker owns (or finished) this unit."""


class UnitBusy(Exception):
    """Another worker holds a live lease on this unit."""


class AttemptsExhausted(Exception):
    """The unit failed MAX_ATTEMPTS times; it needs review or a new pipeline version."""


@dataclass(frozen=True)
class Lease:
    stage_id: uuid.UUID
    token: int
    attempt: int


@dataclass(frozen=True)
class Claim:
    lease: Lease | None          # None when the unit already succeeded
    output_ref: dict | None      # reusable output of a succeeded unit


def idempotency_key(book_version_id, source_sha256: str, stage: str, unit_key: str,
                    pipeline_config_hash: str, input_hash: str) -> str:
    """docs/05: one valid result per input hash and pipeline version."""
    material = json.dumps([str(book_version_id), source_sha256, stage, unit_key,
                           pipeline_config_hash, input_hash], separators=(',', ':'))
    return hashlib.sha256(material.encode()).hexdigest()


def claim(conn: Connection, job_id: uuid.UUID, stage: str, unit_key: str, input_hash: str,
          key: str, worker_id: str, lease: timedelta = LEASE) -> Claim:
    conn.execute(text(
        'INSERT INTO job_stages (job_id, stage, unit_key, input_hash, idempotency_key)'
        ' VALUES (:job, :stage, :unit, :input, :key) ON CONFLICT (idempotency_key) DO NOTHING'),
        {'job': job_id, 'stage': stage, 'unit': unit_key, 'input': input_hash, 'key': key})
    row = conn.execute(text(
        'SELECT id, state, attempt, fencing_token, output_ref, lease_until > now() AS live'
        ' FROM job_stages WHERE idempotency_key = :key FOR UPDATE'), {'key': key}).mappings().one()
    if row['state'] == 'succeeded':
        return Claim(None, row['output_ref'])  # reuse: a retry job never redoes finished units
    if row['state'] == 'running' and row['live']:
        raise UnitBusy(f'{stage}:{unit_key} is leased by another worker')
    if row['attempt'] >= MAX_ATTEMPTS:
        raise AttemptsExhausted(f'{stage}:{unit_key} exhausted {MAX_ATTEMPTS} attempts')
    updated = conn.execute(text(
        "UPDATE job_stages SET state = 'running', attempt = attempt + 1,"
        ' fencing_token = fencing_token + 1, lease_until = now() + :lease, worker_id = :worker'
        ' WHERE id = :id RETURNING fencing_token, attempt'),
        {'id': row['id'], 'lease': lease, 'worker': worker_id}).mappings().one()
    return Claim(Lease(row['id'], updated['fencing_token'], updated['attempt']), None)


def _guarded(conn: Connection, lease: Lease, assignment: str, params: dict) -> None:
    done = conn.execute(text(
        f"UPDATE job_stages SET {assignment} WHERE id = :id AND fencing_token = :token"
        " AND state = 'running'"), {'id': lease.stage_id, 'token': lease.token, **params}).rowcount
    if done != 1:
        raise LeaseLost(f'stage {lease.stage_id} token {lease.token} is no longer current')


def heartbeat(conn: Connection, lease: Lease, extend: timedelta = LEASE,
              checkpoint: dict | None = None) -> None:
    params = {'lease': extend}
    assignment = 'lease_until = now() + :lease'
    if checkpoint is not None:
        assignment += ', checkpoint = CAST(:checkpoint AS jsonb)'
        params['checkpoint'] = json.dumps(checkpoint)
    _guarded(conn, lease, assignment, params)


def complete(conn: Connection, lease: Lease, output_ref: dict) -> None:
    """Call in the same transaction as the writes that publish the unit's output."""
    _guarded(conn, lease, "state = 'succeeded', output_ref = CAST(:out AS jsonb),"
                          ' lease_until = NULL', {'out': json.dumps(output_ref)})


def fail(conn: Connection, lease: Lease, code: str, retryable: bool) -> None:
    _guarded(conn, lease, "state = 'failed', lease_until = NULL,"
                          " checkpoint = checkpoint || CAST(:err AS jsonb)",
             {'err': json.dumps({'last_error': code, 'retryable': retryable})})


def retry_delay(attempt: int) -> float:
    """Exponential backoff with full jitter, 2–120 s (docs/05)."""
    return random.uniform(2, min(120, 2 * 2 ** attempt))


# ---- job state ------------------------------------------------------------------

def start_job(conn: Connection, job_id: uuid.UUID) -> str | None:
    """Move a queued job to running; return the state, or None if there is nothing to do."""
    job = conn.execute(text('SELECT state FROM ingestion_jobs WHERE id = :id FOR UPDATE'),
                       {'id': job_id}).scalar()
    if job is None or job in TERMINAL:
        return None
    if job == 'cancel_requested':
        set_job_state(conn, job_id, 'cancelled')
        return None
    if job in ('retry_wait', 'waiting_review'):
        return None  # the watchdog re-queues these when they are due
    if job == 'queued':
        set_job_state(conn, job_id, 'running')
    return 'running'


def set_job_state(conn: Connection, job_id: uuid.UUID, state: str, error: dict | None = None,
                  counters: dict | None = None) -> None:
    conn.execute(text(
        'UPDATE ingestion_jobs SET state = :state,'
        ' error = CASE WHEN CAST(:error AS jsonb) IS NULL THEN error ELSE CAST(:error AS jsonb) END,'
        ' counters = counters || CAST(:counters AS jsonb) WHERE id = :id'),
        {'id': job_id, 'state': state, 'error': json.dumps(error) if error else None,
         'counters': json.dumps(counters or {})})


def cancel_requested(conn: Connection, job_id: uuid.UUID) -> bool:
    return bool(conn.execute(text('SELECT cancel_requested OR state = \'cancel_requested\''
                                  ' FROM ingestion_jobs WHERE id = :id'), {'id': job_id}).scalar())


def request_cancel(conn: Connection, job_id: uuid.UUID) -> str:
    state = conn.execute(text('SELECT state FROM ingestion_jobs WHERE id = :id FOR UPDATE'),
                         {'id': job_id}).scalar()
    if state is None or state in TERMINAL or state == 'cancel_requested':
        return state
    conn.execute(text("UPDATE ingestion_jobs SET cancel_requested = true,"
                      " state = 'cancel_requested' WHERE id = :id"), {'id': job_id})
    if state in ('queued', 'retry_wait', 'waiting_review'):
        set_job_state(conn, job_id, 'cancelled')  # nobody is running it: finish now
        return 'cancelled'
    return 'cancel_requested'  # a running worker stops cooperatively between units


# ---- operation jobs (deletion/backup/restore/reindex/reevaluate) share the lease model ----

def claim_operation(conn: Connection, operation_id: uuid.UUID,
                    lease: timedelta = LEASE) -> Lease | None:
    row = conn.execute(text('SELECT state, fencing_token, lease_until > now() AS live'
                            ' FROM operation_jobs WHERE id = :id FOR UPDATE'),
                       {'id': operation_id}).mappings().first()
    if row is None or row['state'] in ('succeeded', 'failed', 'cancelled'):
        return None
    if row['state'] == 'running' and row['live']:
        raise UnitBusy(f'operation {operation_id} is leased')
    token = conn.execute(text(
        "UPDATE operation_jobs SET state = 'running', fencing_token = fencing_token + 1,"
        ' lease_until = now() + :lease WHERE id = :id RETURNING fencing_token'),
        {'id': operation_id, 'lease': lease}).scalar_one()
    return Lease(operation_id, token, 0)


def finish_operation(conn: Connection, lease: Lease, state: str, progress: dict) -> None:
    done = conn.execute(text(
        'UPDATE operation_jobs SET state = :state, lease_until = NULL,'
        ' progress = CAST(:progress AS jsonb) WHERE id = :id AND fencing_token = :token'
        " AND state = 'running'"),
        {'id': lease.stage_id, 'token': lease.token, 'state': state,
         'progress': json.dumps(progress)}).rowcount
    if done != 1:
        raise LeaseLost(f'operation {lease.stage_id} token {lease.token} is no longer current')
