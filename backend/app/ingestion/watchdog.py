"""Watchdog/reconciler: rebuilds the runnable set from PostgreSQL every minute.

It never trusts the broker. Expired leases go back to pending, due retries
become queued, and any queued/running job without a live lease or an
unpublished signal gets a fresh outbox event — so losing Redis (restart,
flush) only delays work, it never loses it.

Run as a process:  python -m backend.app.ingestion.watchdog
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import time

from sqlalchemy import text
from sqlalchemy.engine import Engine

from . import outbox
from .outbox import Broker

log = logging.getLogger('bazi.watchdog')
QUEUED_TOPIC = 'ingestion.job.queued'
STALE_AFTER = '60 seconds'


@dataclass
class SweepResult:
    expired_leases: int = 0
    retries_due: int = 0
    resignalled: int = 0
    cancelled: int = 0


def sweep(engine: Engine, stale_after: str = STALE_AFTER) -> SweepResult:
    result = SweepResult()
    with engine.begin() as conn:
        result.expired_leases = conn.execute(text(
            "UPDATE job_stages SET state = 'pending', lease_until = NULL, worker_id = NULL"
            " WHERE state = 'running' AND lease_until < now()")).rowcount
        result.expired_leases += conn.execute(text(
            "UPDATE operation_jobs SET state = 'retry_wait', lease_until = NULL"
            " WHERE state = 'running' AND lease_until < now()")).rowcount

        due = conn.execute(text(
            "SELECT id FROM ingestion_jobs WHERE state = 'retry_wait'"
            " AND coalesce((error->>'retry_at')::timestamptz, now()) <= now() FOR UPDATE"
            ' SKIP LOCKED')).scalars().all()
        for job_id in due:
            conn.execute(text("UPDATE ingestion_jobs SET state = 'queued' WHERE id = :id"),
                         {'id': job_id})
        result.retries_due = len(due)

        # Cancel requests nobody is working on (no live lease) finish here.
        result.cancelled = conn.execute(text(
            "UPDATE ingestion_jobs j SET state = 'cancelled' WHERE j.state = 'cancel_requested'"
            ' AND NOT EXISTS (SELECT 1 FROM job_stages s WHERE s.job_id = j.id'
            " AND s.state = 'running' AND s.lease_until > now())")).rowcount

        # Runnable but silent: no live lease, no pending signal, untouched for a while.
        silent = conn.execute(text(
            "SELECT j.id FROM ingestion_jobs j WHERE j.state IN ('queued', 'running')"
            ' AND (j.updated_at < now() - CAST(:stale AS interval) OR j.id = ANY(:due))'
            ' AND NOT EXISTS (SELECT 1 FROM job_stages s WHERE s.job_id = j.id'
            "   AND s.state = 'running' AND s.lease_until > now())"
            ' AND NOT EXISTS (SELECT 1 FROM outbox_events o WHERE o.published_at IS NULL'
            "   AND o.topic = :topic AND o.payload->>'job_id' = j.id::text)"
            ' FOR UPDATE OF j SKIP LOCKED'),
            {'stale': stale_after, 'due': due, 'topic': QUEUED_TOPIC}).scalars().all()
        for job_id in silent:
            outbox.emit(conn, QUEUED_TOPIC, {'job_id': str(job_id)})
            # Touch so the next sweep waits another interval before re-signalling.
            conn.execute(text('UPDATE ingestion_jobs SET updated_at = now() WHERE id = :id'),
                         {'id': job_id})
        result.resignalled = len(silent)
    return result


def run_forever(engine: Engine, broker: Broker, interval: float = 60.0) -> None:
    while True:
        try:
            swept = sweep(engine)
            sent = outbox.dispatch(engine, broker)
            if any(vars(swept).values()) or sent:
                log.info('watchdog pass', extra={'event': 'watchdog_pass'})
        except Exception:  # noqa: BLE001 - keep the loop alive; the next pass retries
            log.exception('watchdog pass failed', extra={'event': 'watchdog_error'})
        time.sleep(interval)


if __name__ == '__main__':
    from ..core.config import load_settings
    from ..core.db import make_engine
    from ..core.logging import configure_logging
    from .celery_app import CeleryBroker

    settings = load_settings()
    configure_logging(settings.log_level, settings.secret_values())
    run_forever(make_engine(settings.runtime_database_url), CeleryBroker(settings))
