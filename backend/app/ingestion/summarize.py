"""``summarize`` stage: a short Qwen summary of every parent chunk (context for retrieval).

The summary is prepended (after the deterministic header) to each child when it
is embedded, so a child that says "như trên" still lands near questions about
its section. It is written only from the parent's own text, at temperature 0
with thinking off, and is never shown as a source.

Units are batches of parents (checkpointing, idempotency by parent hashes and
prompt version). A parent whose identical text was already summarised with the
same prompt version (another generation, a rebuild) reuses that summary. No
model configured → ``skipped``; a model error → ``failed`` for that parent.
Neither blocks the job: retrieval works without summaries, only less well.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..rag.llm import LLMError, SyncLLM, config_from
from ..rag.prompts import SUMMARY_PROMPT_VERSION, Summary, summary_messages
from .worker import JobContext, Unit

log = logging.getLogger('bazi.summarize')
BATCH = 16
MAX_TOKENS = 400


class SummarizeStage:
    name = 'summarize'

    def __init__(self, settings=None, client: SyncLLM | None = None):
        self.settings = settings
        self._client = client

    def _llm(self) -> SyncLLM | None:
        if self._client is None and self.settings is not None:
            config = config_from(self.settings)
            self._client = SyncLLM(config) if config else None
        return self._client

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            rows = conn.execute(text(
                'SELECT ordinal, content_hash FROM chunk_parents WHERE generation_id = :g'
                ' ORDER BY ordinal'), {'g': ctx.generation_id}).all()
        llm = self._llm()
        model = llm.config.model if llm else 'none'
        units = []
        for start in range(0, len(rows), BATCH):
            batch = rows[start:start + BATCH]
            material = '|'.join(f'{o}:{h.strip()}' for o, h in batch) + SUMMARY_PROMPT_VERSION + model
            units.append(Unit(f'parents:{start}-{start + len(batch) - 1}',
                              hashlib.sha256(material.encode()).hexdigest()))
        return units

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        first, last = map(int, unit.key.split(':', 1)[1].split('-'))
        with ctx.engine.connect() as conn:
            parents = conn.execute(text(
                "SELECT id, ordinal, text, content_hash, meta->>'header' AS header"
                ' FROM chunk_parents WHERE generation_id = :g AND ordinal BETWEEN :a AND :b'
                ' ORDER BY ordinal'), {'g': ctx.generation_id, 'a': first, 'b': last}).mappings().all()
            cached = dict(conn.execute(text(
                "SELECT DISTINCT ON (content_hash) content_hash, summary FROM chunk_parents"
                " WHERE content_hash = ANY(:h) AND summary_status = 'done'"
                ' AND summary_prompt_version = :v ORDER BY content_hash, updated_at DESC'),
                {'h': [p['content_hash'] for p in parents], 'v': SUMMARY_PROMPT_VERSION}).all())
        llm = self._llm()
        results = {}
        todo = []
        for parent in parents:
            if parent['content_hash'] in cached:
                results[str(parent['id'])] = ('done', cached[parent['content_hash']])
            elif llm is None:
                results[str(parent['id'])] = ('skipped', None)
            else:
                todo.append(parent)

        def summarise(parent) -> tuple[str, tuple[str, str | None]]:
            try:
                value, _ = llm.structured(summary_messages(parent['header'] or '', parent['text']),
                                          Summary, MAX_TOKENS, temperature=0.0)
                return str(parent['id']), ('done', value.summary.strip())
            except LLMError as exc:
                log.warning('summary failed', extra={'event': 'summary_failed', 'code': exc.code})
                return str(parent['id']), ('failed', None)

        if todo:
            workers = getattr(self.settings, 'rag_summary_concurrency', 4)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results.update(dict(pool.map(summarise, todo)))
        return {'results': results, 'model': llm.config.model if llm else None,
                'computed': len(todo)}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        for parent_id, (status, summary) in result['results'].items():
            conn.execute(text(
                'UPDATE chunk_parents SET summary = :s, summary_status = :st, summary_model = :m,'
                ' summary_prompt_version = :v WHERE id = :id'),
                {'s': summary, 'st': status, 'm': result['model'], 'v': SUMMARY_PROMPT_VERSION,
                 'id': parent_id})
        done = sum(1 for status, _ in result['results'].values() if status == 'done')
        conn.execute(text(
            'UPDATE ingestion_jobs SET counters = counters || jsonb_build_object('
            " 'parents_summarised', coalesce((counters->>'parents_summarised')::int, 0) + :n)"
            ' WHERE id = :j'), {'j': ctx.job_id, 'n': done})
        return {'summarised': done, 'computed': result['computed']}

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, output: dict) -> None:
        """Unit done by an earlier job (same parents, same prompt): copy its summaries over."""
        first, last = map(int, unit.key.split(':', 1)[1].split('-'))
        conn.execute(text(
            "UPDATE chunk_parents p SET summary = d.summary, summary_status = 'done',"
            ' summary_model = d.summary_model, summary_prompt_version = d.summary_prompt_version'
            ' FROM (SELECT DISTINCT ON (content_hash) content_hash, summary, summary_model,'
            "  summary_prompt_version FROM chunk_parents WHERE summary_status = 'done'"
            '  AND summary_prompt_version = :v ORDER BY content_hash, updated_at DESC) d'
            " WHERE p.generation_id = :g AND p.ordinal BETWEEN :a AND :b"
            " AND p.summary_status <> 'done' AND p.content_hash = d.content_hash"),
            {'g': ctx.generation_id, 'a': first, 'b': last, 'v': SUMMARY_PROMPT_VERSION})
