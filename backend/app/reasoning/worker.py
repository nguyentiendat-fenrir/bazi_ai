"""Reasoning worker: takes queued chat runs one at a time (docs/09, docs/03 worker ``ai``).

    python -m backend.app.reasoning.worker

The queue is the ``chat_runs`` table; a definer function hands out the next queued run
(id and owner only) so the worker then works as that owner under row-level security.
Runs a dead worker left running are failed after RUN_CAP, never resumed silently.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .orchestrator import process

log = logging.getLogger('bazi.reasoning.worker')
RUN_CAP = '10 minutes'
HOUSEKEEPING_SECONDS = 60


def claim(engine: Engine):
    with engine.begin() as conn:
        return conn.execute(text('SELECT run_id, owner_id FROM bazi_claim_chat_run()')).first()


def work_once(engine: Engine, app_env: str = 'dev', transport=None) -> str | None:
    """Process the next queued run; None when the queue is empty."""
    claimed = claim(engine)
    if claimed is None:
        return None
    return process(engine, claimed.run_id, claimed.owner_id, app_env, transport)


def housekeeping(engine: Engine) -> dict:
    with engine.begin() as conn:
        failed = conn.execute(text('SELECT bazi_fail_stale_chat_runs(CAST(:cap AS interval))'),
                              {'cap': RUN_CAP}).scalar_one()
        expired = conn.execute(text('SELECT bazi_expire_run_events()')).scalar_one()
    return {'stale_runs_failed': failed, 'events_expired': expired}


def run_forever(engine: Engine, app_env: str, interval: float = 1.0) -> None:
    last_housekeeping = 0.0
    while True:
        try:
            if time.monotonic() - last_housekeeping > HOUSEKEEPING_SECONDS:
                housekeeping(engine)
                last_housekeeping = time.monotonic()
            if work_once(engine, app_env) is None:
                time.sleep(interval)
        except Exception:  # noqa: BLE001 - keep serving; the next pass retries
            log.exception('reasoning worker pass failed', extra={'event': 'reasoning_error'})
            time.sleep(interval)


if __name__ == '__main__':
    from ..core.config import load_settings
    from ..core.db import make_engine
    from ..core.logging import configure_logging

    settings = load_settings()
    configure_logging(settings.log_level, settings.secret_values())
    run_forever(make_engine(settings.runtime_database_url), settings.app_env)
