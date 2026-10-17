"""Optimistic concurrency (If-Match/ETag) and Idempotency-Key handling (docs/10).

Idempotency rows live in the same transaction as the mutation they protect:
a concurrent request with the same key blocks on the unique index until the
first commits, then replays its stored response. Same key with a different
payload is a client bug and gets 409.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .errors import AppError

IDEMPOTENCY_HEADER = 'Idempotency-Key'
IDEMPOTENCY_TTL_HOURS = 24
_KEY = re.compile(r'^[\x21-\x7e]{1,128}$')  # visible ASCII, max 128 (docs/10)


def etag(revision: int | str) -> str:
    return f'"{revision}"'


def require_if_match(request: Request, current: int | str) -> None:
    """412 when the client edited a stale revision, 428 when it did not say which."""
    presented = request.headers.get('If-Match')
    if presented is None:
        raise AppError(428, 'PRECONDITION_REQUIRED', 'If-Match header with the revision is required')
    if presented.strip() not in (etag(current), str(current)):
        raise AppError(412, 'REVISION_MISMATCH', 'The resource changed; reload and retry',
                       headers={'ETag': etag(current)})


def request_hash(payload) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                           default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class Replay:
    status_code: int
    body: dict


@dataclass
class IdempotencySlot:
    conn: Connection
    owner_id: uuid.UUID
    route: str
    key: str
    replay: Replay | None = None

    def complete(self, status_code: int, body: dict) -> None:
        self.conn.execute(text(
            "UPDATE idempotency_keys SET status = 'completed', response_code = :code,"
            ' response = CAST(:body AS jsonb) WHERE owner_id = :owner AND route = :route'
            ' AND key = :key'),
            {'code': status_code, 'body': json.dumps(body, default=str), 'owner': self.owner_id,
             'route': self.route, 'key': self.key})


def claim_idempotency(conn: Connection, request: Request, owner_id: uuid.UUID, route: str,
                      payload) -> IdempotencySlot:
    key = request.headers.get(IDEMPOTENCY_HEADER)
    if key is None or not _KEY.fullmatch(key):
        raise AppError(422, 'VALIDATION_ERROR', 'Idempotency-Key header (1-128 visible ASCII)'
                       ' is required', field_errors=[{'path': 'header.Idempotency-Key',
                                                      'message': 'required'}])
    digest = request_hash(payload)
    params = {'owner': owner_id, 'route': route, 'key': key, 'hash': digest,
              'ttl': f'{IDEMPOTENCY_TTL_HOURS} hours'}
    # Expired keys are forgotten so the key can be reused after the retention window.
    conn.execute(text('DELETE FROM idempotency_keys WHERE owner_id = :owner AND route = :route'
                      ' AND key = :key AND expires_at < now()'), params)
    inserted = conn.execute(text(
        'INSERT INTO idempotency_keys (owner_id, route, key, request_hash, status, expires_at)'
        " VALUES (:owner, :route, :key, :hash, 'in_progress', now() + CAST(:ttl AS interval))"
        ' ON CONFLICT (owner_id, route, key) DO NOTHING RETURNING id'), params).first()
    slot = IdempotencySlot(conn, owner_id, route, key)
    if inserted:
        return slot
    row = conn.execute(text(
        'SELECT request_hash, status, response_code, response FROM idempotency_keys'
        ' WHERE owner_id = :owner AND route = :route AND key = :key FOR UPDATE'),
        params).mappings().one()
    if row['request_hash'] != digest:
        raise AppError(409, 'IDEMPOTENCY_MISMATCH',
                       'Idempotency-Key was already used with a different request')
    if row['status'] != 'completed':
        raise AppError(409, 'IDEMPOTENCY_IN_PROGRESS', 'The original request is still running')
    slot.replay = Replay(row['response_code'], row['response'])
    return slot
