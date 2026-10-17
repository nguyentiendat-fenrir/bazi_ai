"""Durable, ordered job events (docs/10 ``GET /jobs/{id}/events``).

Events are written in the same transaction as the state change they describe,
so a reader never sees "stage done" for work that rolled back. ``seq`` is
allocated under the job row lock: one gap-free order per job.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection


def log(conn: Connection, job_id: uuid.UUID, level: str, code: str,
        payload: dict | None = None) -> None:
    conn.execute(text('SELECT 1 FROM ingestion_jobs WHERE id = :j FOR UPDATE'), {'j': job_id})
    conn.execute(text(
        'INSERT INTO job_events (job_id, seq, level, code, payload)'
        ' SELECT :j, coalesce(max(seq), 0) + 1, :level, :code, CAST(:payload AS jsonb)'
        ' FROM job_events WHERE job_id = :j'),
        {'j': job_id, 'level': level, 'code': code, 'payload': json.dumps(payload or {})})


def read(conn: Connection, job_id: uuid.UUID, after_seq: int = 0, limit: int = 100) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        'SELECT seq, level, code, payload, created_at FROM job_events'
        ' WHERE job_id = :j AND seq > :after ORDER BY seq LIMIT :limit'),
        {'j': job_id, 'after': after_seq, 'limit': limit}).mappings()]
