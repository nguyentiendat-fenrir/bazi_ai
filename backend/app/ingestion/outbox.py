"""Transactional outbox → broker, and consumer-side dedupe (docs/03 · Transaction và event).

Events are written in the business transaction. The dispatcher sends them and
then marks them published; a crash between send and mark resends, so every
consumer dedupes through ``processed_events``. Delivery is at-least-once,
never assumed exactly-once.
"""
from __future__ import annotations

import logging
from typing import Callable, Protocol
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

log = logging.getLogger('bazi.outbox')


class Broker(Protocol):
    def send(self, topic: str, payload: dict, event_id: uuid.UUID) -> None: ...


def emit(conn: Connection, topic: str, payload: dict) -> None:
    import json
    conn.execute(text('INSERT INTO outbox_events (topic, payload) VALUES (:t, CAST(:p AS jsonb))'),
                 {'t': topic, 'p': json.dumps(payload)})


def dispatch(engine: Engine, broker: Broker, limit: int = 100,
             fault: Callable[[str], None] | None = None) -> int:
    """Send unpublished events; returns how many were marked published."""
    sent = 0
    with engine.begin() as conn:
        # SKIP LOCKED lets several dispatchers share the table without double work.
        rows = conn.execute(text(
            'SELECT id, event_id, topic, payload FROM outbox_events WHERE published_at IS NULL'
            ' ORDER BY created_at LIMIT :limit FOR UPDATE SKIP LOCKED'),
            {'limit': limit}).mappings().all()
        for row in rows:
            try:
                broker.send(row['topic'], row['payload'], row['event_id'])
            except Exception as exc:  # noqa: BLE001 - broker down: keep for the next pass
                log.warning('outbox send failed', extra={'event': 'outbox_send_failed',
                                                         'error_code': type(exc).__name__})
                conn.execute(text('UPDATE outbox_events SET attempts = attempts + 1 WHERE id = :id'),
                             {'id': row['id']})
                continue
            if fault:
                fault('after_send_before_mark')
            conn.execute(text('UPDATE outbox_events SET published_at = now(), attempts = attempts + 1'
                              ' WHERE id = :id'), {'id': row['id']})
            sent += 1
    return sent


def first_delivery(conn: Connection, consumer: str, event_id: uuid.UUID) -> bool:
    """True exactly once per (consumer, event); later redeliveries return False."""
    return conn.execute(text(
        'INSERT INTO processed_events (consumer, event_id) VALUES (:c, :e)'
        ' ON CONFLICT (consumer, event_id) DO NOTHING RETURNING id'),
        {'c': consumer, 'e': event_id}).first() is not None
