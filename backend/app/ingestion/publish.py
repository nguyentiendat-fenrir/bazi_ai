"""``publish`` stage: seal the built generation, then publish it if the batch asked to.

Sealing hashes the generation's membership (pages → revisions, section tree,
chunk order) into ``manifest_hash`` and moves it ``building → ready``; from then
on its membership is frozen and it can join a corpus release. A batch with
``auto_publish`` publishes the sealed generation when every gate passes without
a human acknowledgement (no partial coverage); otherwise the generation waits
for a reviewer and the job counters say why (``auto_publish``: the gate code).
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from ..documents import releases
from .worker import JobContext, Unit

MANIFEST_VERSION = 'generation-manifest-1'


def manifest_hash(conn: Connection, generation_id) -> str:
    """Content identity of a generation: chunk ids imply text and spans (immutable rows)."""
    pages = conn.execute(text(
        'SELECT page_id::text, page_revision_id::text FROM generation_pages'
        ' WHERE generation_id = :g ORDER BY page_id'), {'g': generation_id}).all()
    sections = conn.execute(text('SELECT path, title FROM sections WHERE generation_id = :g'
                                 ' ORDER BY path'), {'g': generation_id}).all()
    chunks = conn.execute(text(
        'SELECT gc.ordinal, gc.chunk_id::text, s.path FROM generation_chunks gc'
        ' JOIN sections s ON s.id = gc.section_id WHERE gc.generation_id = :g'
        ' ORDER BY gc.ordinal'), {'g': generation_id}).all()
    material = json.dumps({'version': MANIFEST_VERSION, 'pages': [list(r) for r in pages],
                           'sections': [list(r) for r in sections],
                           'chunks': [list(r) for r in chunks]},
                          ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(material.encode('utf-8')).hexdigest()


class PublishStage:
    name = 'publish'

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            state = conn.execute(text('SELECT state FROM generations WHERE id = :g'),
                                 {'g': ctx.generation_id}).scalar_one()
            if state != 'building' or not conn.execute(text(
                    'SELECT 1 FROM generation_pages WHERE generation_id = :g LIMIT 1'),
                    {'g': ctx.generation_id}).first():
                return []
            return [Unit('generation', manifest_hash(conn, ctx.generation_id))]

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        return {'manifest_hash': unit.input_hash}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        self.attach(conn, ctx, unit, result)
        return result

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, output: dict) -> None:
        pages = releases.coverage(conn, ctx.generation_id)
        sealed = conn.execute(text(
            "UPDATE generations SET state = 'ready', manifest_hash = :h,"
            " coverage = coverage || CAST(:c AS jsonb) WHERE id = :g AND state = 'building'"
            ' RETURNING id'),
            {'g': ctx.generation_id, 'h': output['manifest_hash'],
             'c': json.dumps({'accepted': pages['accepted'],
                              'review_required': pages['review_required'],
                              'excluded': pages['excluded'], 'failed': pages['missing'],
                              'excluded_ranges': pages['excluded_ranges']})}).first()
        if sealed is None:
            return
        job = conn.execute(text(
            'SELECT j.requested_by, b.config FROM ingestion_jobs j'
            ' LEFT JOIN ingestion_batches b ON b.id = j.batch_id WHERE j.id = :j'),
            {'j': ctx.job_id}).mappings().one()
        if not (job['config'] or {}).get('auto_publish'):
            return
        outcome = 'published'
        try:
            with conn.begin_nested():
                releases.publish(conn, job['requested_by'], ctx.generation_id)
        except AppError as exc:
            outcome = exc.code           # e.g. PARTIAL_NOT_ACKNOWLEDGED: a reviewer decides
        conn.execute(text('UPDATE ingestion_jobs SET counters = counters || CAST(:c AS jsonb)'
                          ' WHERE id = :j'),
                     {'j': ctx.job_id, 'c': json.dumps({'auto_publish': outcome})})
