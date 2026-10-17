"""Job runner: stages × units, each unit leased, computed, then published atomically.

Stage handlers split work in two:

* ``compute(ctx, unit)`` does the expensive part (parse, OCR, embed) without
  touching the database; it may only write content-addressed blobs, which are
  harmless if the worker dies (identical bytes, or an orphan for the sweep).
* ``persist(conn, ctx, unit, result)`` writes rows in the same transaction as
  ``queue.complete``; a stale fencing token rolls the whole unit back.

A killed worker therefore leaves either nothing or a fully published unit, and
a rerun skips succeeded units by their idempotency key.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable, Protocol
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..storage.base import ObjectStore
from . import queue

log = logging.getLogger('bazi.worker')
Fault = Callable[[str], None]


class RetryableError(Exception):
    """Transient failure (network, 429/5xx, timeout): retry the unit later."""

    def __init__(self, code: str, message: str = ''):
        super().__init__(message or code)
        self.code = code


class UnitFailed(Exception):
    """Permanent failure for this unit (corrupt input, password, invalid format)."""

    def __init__(self, code: str, message: str = ''):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class Unit:
    key: str            # e.g. "page:12", "doc", "chunk-batch:3"
    input_hash: str     # hash of everything the result depends on


@dataclass
class JobContext:
    job_id: uuid.UUID
    book_version_id: uuid.UUID
    generation_id: uuid.UUID
    pipeline_profile_id: uuid.UUID
    pipeline_config_hash: str
    pipeline_config: dict
    source_sha256: str
    source_key: str
    source_mime: str
    engine: Engine
    store: ObjectStore
    worker_id: str
    state: dict = field(default_factory=dict)  # per-run scratch shared between stages


class StageHandler(Protocol):
    name: str

    def units(self, ctx: JobContext) -> list[Unit]: ...

    def compute(self, ctx: JobContext, unit: Unit) -> Any: ...

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: Any) -> dict: ...

    # Optional: ``attach(conn, ctx, unit, output_ref)`` links an output computed by an
    # earlier job (same idempotency key) to this job's generation. Must be idempotent.


def load_context(conn: Connection, job_id: uuid.UUID, engine: Engine, store: ObjectStore,
                 worker_id: str) -> JobContext:
    row = conn.execute(text(
        'SELECT j.id, j.book_version_id, j.generation_id, j.pipeline_profile_id,'
        ' p.config_hash, p.config, o.sha256, o.object_key, o.detected_mime'
        ' FROM ingestion_jobs j JOIN pipeline_profiles p ON p.id = j.pipeline_profile_id'
        ' JOIN book_versions v ON v.id = j.book_version_id JOIN objects o ON o.id = v.object_id'
        ' WHERE j.id = :id'), {'id': job_id}).mappings().one()
    return JobContext(row['id'], row['book_version_id'], row['generation_id'],
                      row['pipeline_profile_id'], row['config_hash'].strip(), row['config'] or {},
                      row['sha256'].strip(), row['object_key'], row['detected_mime'], engine,
                      store, worker_id)


def _due(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def run_job(engine: Engine, store: ObjectStore, job_id: uuid.UUID,
            handlers: list[StageHandler], worker_id: str,
            fault: Fault | None = None) -> str:
    """Run (or resume) a job; returns the job state reached by this worker."""
    def hit(point: str) -> None:
        if fault:
            fault(point)

    with engine.begin() as conn:
        if queue.start_job(conn, job_id) is None:
            return conn.execute(text('SELECT state FROM ingestion_jobs WHERE id = :id'),
                                {'id': job_id}).scalar() or 'missing'
        ctx = load_context(conn, job_id, engine, store, worker_id)
    if not handlers:
        with engine.begin() as conn:
            queue.set_job_state(conn, job_id, 'failed',
                                {'code': 'PIPELINE_NOT_CONFIGURED', 'retryable': False,
                                 'message': 'No stage handlers for this pipeline profile'})
        return 'failed'

    for handler in handlers:
        units = handler.units(ctx)
        for unit in units:
            with engine.begin() as conn:
                if queue.cancel_requested(conn, job_id):
                    queue.set_job_state(conn, job_id, 'cancelled')
                    return 'cancelled'
                key = queue.idempotency_key(ctx.book_version_id, ctx.source_sha256, handler.name,
                                            unit.key, ctx.pipeline_config_hash, unit.input_hash)
                try:
                    claimed = queue.claim(conn, job_id, handler.name, unit.key, unit.input_hash,
                                          key, worker_id)
                except queue.UnitBusy:
                    return 'running'  # a live worker owns this unit; it will finish the job
                except queue.AttemptsExhausted:
                    queue.set_job_state(conn, job_id, 'failed', {
                        'code': 'ATTEMPTS_EXHAUSTED', 'retryable': False,
                        'message': f'{handler.name} {unit.key} failed {queue.MAX_ATTEMPTS} times'})
                    return 'failed'
            if claimed.lease is None:
                # Computed before (retry job or another generation of the same version):
                # reuse the output, but still link it to this generation.
                attach = getattr(handler, 'attach', None)
                if attach is not None:
                    with engine.begin() as conn:
                        attach(conn, ctx, unit, claimed.output_ref)
                continue
            lease = claimed.lease
            try:
                result = handler.compute(ctx, unit)
            except RetryableError as exc:
                with engine.begin() as conn:
                    queue.fail(conn, lease, exc.code, retryable=True)
                    queue.set_job_state(conn, job_id, 'retry_wait', {
                        'code': exc.code, 'retryable': True, 'message': str(exc)[:500],
                        'retry_at': _due(queue.retry_delay(lease.attempt))})
                return 'retry_wait'
            except UnitFailed as exc:
                with engine.begin() as conn:
                    queue.fail(conn, lease, exc.code, retryable=False)
                    queue.set_job_state(conn, job_id, 'failed', {
                        'code': exc.code, 'retryable': False, 'message': str(exc)[:500]})
                return 'failed'
            hit('after_compute_before_commit')
            try:
                with engine.begin() as conn:
                    output_ref = handler.persist(conn, ctx, unit, result)
                    hit('after_persist_before_complete')
                    queue.complete(conn, lease, output_ref)
            except queue.LeaseLost:
                log.warning('lease lost; result discarded',
                            extra={'event': 'lease_lost', 'error_code': 'LEASE_LOST'})
                return 'running'
            hit('after_commit_before_next')

    with engine.begin() as conn:
        queue.set_job_state(conn, job_id, 'succeeded')
    return 'succeeded'
