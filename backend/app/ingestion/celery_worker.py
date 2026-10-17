"""Celery worker entry point; importing it loads settings and fails loudly if invalid.

    celery -A backend.app.ingestion.celery_worker:celery worker -Q ingestion -c 1
"""
from __future__ import annotations

import socket
import uuid

from ..core.config import load_settings
from ..core.db import make_engine
from ..core.logging import configure_logging
from ..storage import build_store
from .celery_app import CONSUMER, JOB_TASK, make_celery
from .outbox import first_delivery
from .pipeline import handlers_for
from .worker import run_job

settings = load_settings()
configure_logging(settings.log_level, settings.secret_values())
celery = make_celery(settings)
engine = make_engine(settings.runtime_database_url)
store = build_store(settings)
WORKER_ID = f'{socket.gethostname()}:{uuid.uuid4().hex[:8]}'


@celery.task(name=JOB_TASK)
def run_job_task(job_id: str, event_id: str) -> str:
    with engine.begin() as conn:
        if not first_delivery(conn, CONSUMER, uuid.UUID(event_id)):
            return 'duplicate-delivery'  # redelivered signal; the job runner is idempotent anyway
    return run_job(engine, store, uuid.UUID(job_id), handlers_for(settings), WORKER_ID)
