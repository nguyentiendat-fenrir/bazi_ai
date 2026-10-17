"""Objects table + blob store together.

The ``objects`` row is the authority (docs/04): a blob without a ready row is
garbage, a row is only ``ready`` after the blob is stored. Deletion goes
through the database first so FK RESTRICT from book versions, renders,
reports and backups blocks removing anything still referenced.
"""
from __future__ import annotations

from typing import BinaryIO
import uuid

from psycopg import errors as pg_errors
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from .base import ObjectStore, StorageError


class ObjectInUse(StorageError):
    pass


def store_object(conn: Connection, store: ObjectStore, stream: BinaryIO,
                 detected_mime: str) -> dict:
    """Store bytes and return the objects row; identical bytes reuse the existing row."""
    stored = store.put_if_absent(stream)
    row = conn.execute(text(
        'INSERT INTO objects (sha256, storage_backend, object_key, size_bytes, detected_mime, state)'
        " VALUES (:sha, :backend, :key, :size, :mime, 'ready')"
        ' ON CONFLICT (sha256) DO NOTHING RETURNING id, sha256, object_key, size_bytes, state'),
        {'sha': stored.sha256, 'backend': store.backend, 'key': stored.key,
         'size': stored.size_bytes, 'mime': detected_mime}).mappings().first()
    if row is None:
        row = conn.execute(text('SELECT id, sha256, object_key, size_bytes, state FROM objects'
                                ' WHERE sha256 = :sha'), {'sha': stored.sha256}).mappings().one()
        return {**row, 'created': False}
    return {**row, 'created': True}


def delete_object(engine: Engine, store: ObjectStore, object_id: uuid.UUID) -> bool:
    """Delete the row (FK-checked) and, only after commit, the blob.

    Runs its own transaction: removing the blob before the row deletion is
    durable would lose data if the transaction rolled back. A crash between
    commit and blob removal leaves an orphan blob for the sweep, never a row
    pointing at nothing. Referenced objects raise ObjectInUse.
    """
    try:
        with engine.begin() as conn:
            key = conn.execute(text('DELETE FROM objects WHERE id = :id RETURNING object_key'),
                               {'id': object_id}).scalar()
    except IntegrityError as exc:
        if isinstance(exc.orig, pg_errors.ForeignKeyViolation):
            raise ObjectInUse(f'object {object_id} is still referenced') from None
        raise
    if key is None:
        return False
    store.delete(key)
    return True


def orphan_blobs(conn: Connection, store: ObjectStore) -> list[str]:
    """Blob keys with no objects row (interrupted deletes/writes); caller decides removal."""
    known = {r[0] for r in conn.execute(text('SELECT object_key FROM objects'))}
    return [s.key for s in store.list_manifest() if s.key not in known]
