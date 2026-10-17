"""Celery wiring: Redis carries signals only; PostgreSQL holds the state (ADR-06).

acks_late + prefetch 1 suit long jobs, and a lost worker's message is
redelivered — but correctness comes from leases/idempotency in the database,
not from these settings.

Worker entry point: backend/app/ingestion/celery_worker.py
"""
from __future__ import annotations

import uuid

from celery import Celery

from ..core.config import Settings

JOB_TASK = 'bazi.ingestion.run_job'
CONSUMER = 'ingestion-worker'


def make_celery(settings: Settings) -> Celery:
    app = Celery('bazi', broker=settings.redis_url)
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_default_queue='ingestion',
        task_serializer='json',
        accept_content=['json'],
        # Longer than any stage runtime cap; long jobs are split into units instead.
        broker_transport_options={'visibility_timeout': 6 * 3600},
    )
    return app


class CeleryBroker:
    def __init__(self, settings: Settings, app: Celery | None = None):
        self.app = app or make_celery(settings)

    def send(self, topic: str, payload: dict, event_id: uuid.UUID) -> None:
        if topic == 'ingestion.job.queued':
            self.app.send_task(JOB_TASK, kwargs={'job_id': payload['job_id'],
                                                 'event_id': str(event_id)})
