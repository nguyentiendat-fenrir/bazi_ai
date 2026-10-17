"""Batch uploads: one file per request, results recorded per file (docs/10, docs/05).

Accepting a file is a single transaction: store bytes (content-addressed),
dedupe, create the version, and — when the batch names a pipeline profile —
a building generation, a queued ingestion job and its outbox event. Identical
bytes uploaded concurrently serialise on the objects.sha256 unique index, so
the second upload sees the first one's committed version and reports a
duplicate instead of creating another object, version or job.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import BinaryIO
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..auth.service import Principal
from ..core.db import transaction
from ..core.errors import AppError
from ..storage.base import ObjectStore, StorageError
from ..storage.service import store_object
from .catalog import create_book
from .formats import DOCX, FormatRejected, sniff, validate_docx
from .text import display_name, title_from_filename

RIGHTS = ('unknown', 'private_reference', 'licensed', 'public_domain', 'restricted')


@dataclass(frozen=True)
class UploadForm:
    batch_id: uuid.UUID
    edition_label: str
    rights_status: str
    external_processing_allowed: bool
    book_id: uuid.UUID | None
    title: str | None
    language: str


class UploadRejected(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def create_batch(conn: Connection, principal: Principal, name: str,
                 pipeline_profile_id: uuid.UUID | None, auto_publish: bool) -> dict:
    if pipeline_profile_id and not conn.execute(text(
            'SELECT 1 FROM pipeline_profiles WHERE id = :id'), {'id': pipeline_profile_id}).first():
        raise AppError(422, 'VALIDATION_ERROR', 'Unknown pipeline profile',
                       field_errors=[{'path': 'body.pipeline_profile_id', 'message': 'not found'}])
    config = {'pipeline_profile_id': str(pipeline_profile_id) if pipeline_profile_id else None,
              'auto_publish': auto_publish}
    return dict(conn.execute(text(
        'INSERT INTO ingestion_batches (created_by, name, config)'
        ' VALUES (:user, :name, CAST(:config AS jsonb)) RETURNING id, name, state, config,'
        ' created_at'), {'user': principal.user_id, 'name': name,
                         'config': json.dumps(config)}).mappings().one())


def batch_for_upload(conn: Connection, batch_id: uuid.UUID) -> dict:
    batch = conn.execute(text('SELECT id, state, config FROM ingestion_batches WHERE id = :id'
                              ' FOR SHARE'), {'id': batch_id}).mappings().first()
    if batch is None:
        raise UploadRejected(404, 'NOT_FOUND', 'Batch not found')
    if batch['state'] not in ('open', 'running'):
        raise UploadRejected(409, 'CONFLICT', f'Batch is {batch["state"]}')
    return dict(batch)


def _queue_job(conn: Connection, principal: Principal, batch: dict,
               version_id: uuid.UUID) -> uuid.UUID | None:
    profile = (batch['config'] or {}).get('pipeline_profile_id')
    if not profile:
        return None  # processed later via POST /book-versions/{id}/process
    generation = conn.execute(text(
        'INSERT INTO generations (book_version_id, pipeline_profile_id) VALUES (:v, :p)'
        ' RETURNING id'), {'v': version_id, 'p': profile}).scalar_one()
    job = conn.execute(text(
        'INSERT INTO ingestion_jobs (batch_id, book_version_id, generation_id, pipeline_profile_id,'
        ' requested_by) VALUES (:b, :v, :g, :p, :u) RETURNING id'),
        {'b': batch['id'], 'v': version_id, 'g': generation, 'p': profile,
         'u': principal.user_id}).scalar_one()
    # Same transaction as the job: the dispatcher can never miss or invent it.
    conn.execute(text("INSERT INTO outbox_events (topic, payload) VALUES ('ingestion.job.queued',"
                      ' CAST(:payload AS jsonb))'), {'payload': json.dumps({'job_id': str(job)})})
    return job


def accept_upload(conn: Connection, store: ObjectStore, principal: Principal, form: UploadForm,
                  stream: BinaryIO, filename: str | None) -> dict:
    name = display_name(filename)
    batch = batch_for_upload(conn, form.batch_id)
    try:
        mime = sniff(stream.read(8), name)
        stream.seek(0)
        if mime == DOCX:
            validate_docx(stream)
    except FormatRejected as exc:
        raise UploadRejected(415, exc.code, str(exc)) from None
    try:
        obj = store_object(conn, store, stream, mime)
    except StorageError as exc:
        raise UploadRejected(413, 'FILE_TOO_LARGE', str(exc)) from None
    result = {'display_name': name, 'sha256': obj['sha256'].strip(),
              'size_bytes': obj['size_bytes'], 'object_id': obj['id']}

    existing = conn.execute(text('SELECT id, book_id FROM book_versions WHERE object_id = :o'
                                 ' ORDER BY created_at LIMIT 1'), {'o': obj['id']}).mappings().first()
    if existing:
        record_item(conn, form.batch_id, name, 'duplicate', obj=obj,
                    duplicate_of=existing['id'])
        return {**result, 'outcome': 'duplicate', 'duplicate_of': str(existing['id']),
                'book_id': str(existing['book_id'])}

    if form.book_id:
        if conn.execute(text('SELECT 1 FROM books WHERE id = :b AND deleted_at IS NULL FOR UPDATE'),
                        {'b': form.book_id}).first() is None:
            raise UploadRejected(404, 'NOT_FOUND', 'Book not found')
        book_id = form.book_id
    else:
        book_id = create_book(conn, principal, form.title or title_from_filename(name),
                              form.language, None, [])
        conn.execute(text('SELECT 1 FROM books WHERE id = :b FOR UPDATE'), {'b': book_id})
    version_no = conn.execute(text('SELECT coalesce(max(version_no), 0) + 1 FROM book_versions'
                                   ' WHERE book_id = :b'), {'b': book_id}).scalar_one()
    version_id = conn.execute(text(
        'INSERT INTO book_versions (book_id, object_id, edition_label, version_no, rights_status,'
        ' external_processing_allowed, uploaded_by) VALUES (:b, :o, :e, :n, :r, :x, :u)'
        ' RETURNING id'),
        {'b': book_id, 'o': obj['id'], 'e': form.edition_label, 'n': version_no,
         'r': form.rights_status, 'x': form.external_processing_allowed,
         'u': principal.user_id}).scalar_one()
    job_id = _queue_job(conn, principal, batch, version_id)
    record_item(conn, form.batch_id, name, 'accepted', obj=obj, version_id=version_id,
                job_id=job_id)
    conn.execute(text("UPDATE ingestion_batches SET state = 'running'"
                      " WHERE id = :b AND state = 'open' AND :queued"),
                 {'b': form.batch_id, 'queued': job_id is not None})
    return {**result, 'outcome': 'accepted', 'book_id': str(book_id),
            'version_id': str(version_id), 'job_id': str(job_id) if job_id else None}


def record_item(conn: Connection, batch_id: uuid.UUID, name: str, outcome: str, obj=None,
                version_id=None, duplicate_of=None, job_id=None, error_code=None) -> None:
    conn.execute(text(
        'INSERT INTO ingestion_batch_items (batch_id, display_name, outcome, error_code, sha256,'
        ' size_bytes, object_id, book_version_id, duplicate_of_version_id, job_id)'
        ' VALUES (:b, :n, :o, :e, :sha, :size, :obj, :v, :d, :j)'),
        {'b': batch_id, 'n': name, 'o': outcome, 'e': error_code,
         'sha': obj['sha256'] if obj else None, 'size': obj['size_bytes'] if obj else None,
         'obj': obj['id'] if obj else None, 'v': version_id, 'd': duplicate_of, 'j': job_id})


def record_rejection(engine: Engine, principal: Principal, batch_id: uuid.UUID,
                     filename: str | None, code: str) -> None:
    """Separate transaction: the upload's own transaction rolled back."""
    with transaction(engine, principal.user_id) as conn:
        if conn.execute(text('SELECT 1 FROM ingestion_batches WHERE id = :b'),
                        {'b': batch_id}).first():
            record_item(conn, batch_id, display_name(filename), 'rejected', error_code=code)


def batch_view(conn: Connection, batch_id: uuid.UUID) -> dict:
    batch = conn.execute(text('SELECT id, name, state, config, created_by, created_at'
                              ' FROM ingestion_batches WHERE id = :id'),
                         {'id': batch_id}).mappings().first()
    if batch is None:
        raise AppError(404, 'NOT_FOUND', 'Batch not found')
    items = conn.execute(text(
        'SELECT id, display_name, outcome, error_code, sha256, size_bytes, book_version_id,'
        ' duplicate_of_version_id, job_id, created_at FROM ingestion_batch_items'
        ' WHERE batch_id = :b ORDER BY created_at, id'), {'b': batch_id}).mappings().all()
    counters = {k: 0 for k in ('accepted', 'duplicate', 'rejected')}
    for item in items:
        counters[item['outcome']] += 1

    def s(value):
        return str(value) if value is not None else None
    return {'id': str(batch['id']), 'name': batch['name'], 'state': batch['state'],
            'pipeline_profile_id': (batch['config'] or {}).get('pipeline_profile_id'),
            'auto_publish': bool((batch['config'] or {}).get('auto_publish')),
            'counters': counters,
            'items': [{'id': s(i['id']), 'display_name': i['display_name'],
                       'outcome': i['outcome'], 'error_code': i['error_code'],
                       'sha256': i['sha256'].strip() if i['sha256'] else None,
                       'size_bytes': i['size_bytes'], 'version_id': s(i['book_version_id']),
                       'duplicate_of': s(i['duplicate_of_version_id']), 'job_id': s(i['job_id'])}
                      for i in items]}
