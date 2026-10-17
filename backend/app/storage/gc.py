"""Garbage collection of unreferenced objects and orphan blobs (docs/05, docs/12).

Only bytes nothing points at are removed, and only after a grace period, so an
upload or a render that is still committing is never collected:

* an ``objects`` row no table references (book versions, rendered pages,
  reports, backups, batch items) and older than the grace period is deleted
  with its blob — the delete is FK-checked, so a reference added meanwhile wins;
* a blob without an ``objects`` row (interrupted write or delete) older than the
  grace period is removed.

Withdrawn versions keep their source object: withdrawal revokes visibility,
deleting content is a separate, audited operation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .base import ObjectStore
from .service import ObjectInUse, delete_object

GRACE = timedelta(hours=24)
REFERENCES = (('book_versions', 'object_id'), ('page_revisions', 'rendered_object_id'),
              ('evaluation_runs', 'report_object_id'), ('backups', 'manifest_object_id'),
              ('ingestion_batch_items', 'object_id'))


def collect(engine: Engine, store: ObjectStore, grace: timedelta = GRACE,
            dry_run: bool = False) -> dict:
    unused = ' AND '.join(f'NOT EXISTS (SELECT 1 FROM {table} t WHERE t.{column} = o.id)'
                          for table, column in REFERENCES)
    with engine.connect() as conn:
        candidates = conn.execute(text(
            f'SELECT id FROM objects o WHERE o.created_at < now() - :grace AND {unused}'),
            {'grace': grace}).scalars().all()
        known = set(conn.execute(text('SELECT object_key FROM objects')).scalars())
    cutoff = datetime.now(timezone.utc) - grace
    orphans = [s.key for s in store.list_manifest()
               if s.key not in known and s.modified is not None and s.modified < cutoff]
    removed_objects = removed_blobs = 0
    if not dry_run:
        for object_id in candidates:
            try:
                removed_objects += delete_object(engine, store, object_id)
            except ObjectInUse:
                continue                      # referenced since we looked: keep it
        for key in orphans:
            with engine.connect() as conn:    # a row may have been committed since
                if conn.execute(text('SELECT 1 FROM objects WHERE object_key = :k'),
                                {'k': key}).first():
                    continue
            store.delete(key)
            removed_blobs += 1
    return {'dry_run': dry_run, 'unreferenced_objects': len(candidates),
            'orphan_blobs': len(orphans), 'removed_objects': removed_objects,
            'removed_blobs': removed_blobs}
