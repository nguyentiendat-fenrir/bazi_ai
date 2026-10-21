"""The RAG pipeline (service layer): retrieve children, read parents, answer from them only.

1. Query: NFC; BM25 also matches the accent-folded form.
2. Dense: Jina ``query`` embedding (CPU, in a thread) → pgvector cosine inside the
   principal's scope (active release, visibility, filters) → top N children.
3. Sparse: in-process BM25 over the release's children, restricted to the same scope.
4. Fusion: per-query min-max normalisation, ``0.8·dense + 0.2·sparse`` (settings).
5. Dedupe: the same passage in another edition folds into the best one (``also_in``).
6. Rerank: jina-reranker on the top ``rag_rerank_depth`` (header + start of the
   child); on timeout or error the fused order stands (``reranker_unavailable``).
7. Child → parent: parents of the best children, in rank order, packed into the
   context budget; each gets a handle ``P1…``; approved expert rules whose
   evidence lies in the parent are listed with it.
8. Generate: Qwen answers from the parents only, as JSON validated by Pydantic.
9. Validate: every ``[P#]`` must be a handle that was sent; others are removed
   and listed; no valid citation → ``insufficient_evidence``.

Nothing here touches HTTP: the router maps the result, a CLI or worker could call
it too. Blocking work (DB, CPU models) runs in threads; only the LLM call is async.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import functools
import logging
import re
import threading
import time

import anyio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..auth.service import Principal
from ..core.db import transaction
from ..documents.text import nfc
from ..retrieval.search import Spec
from . import prompts
from .bm25 import BM25Index
from .fusion import Candidate, collapse, fuse
from .llm import AsyncLLM, LLMError
from .repository import RagRepository
from .schemas import AskIn, AskOut, ChildOut, ParentOut, ReviewedRule, Scores

log = logging.getLogger('bazi.rag')
HANDLE = re.compile(r'\[(P\d+)\]')
SHOWN_CHILDREN = 20          # children listed for judges (reranked first, then fused order)
PARENT_OVERHEAD = 60         # header + markers per parent in the prompt, in tokens
INSUFFICIENT = ('Không tìm thấy đủ căn cứ trong các đoạn sách được truy xuất để trả lời câu hỏi'
                ' này.')


class SparseCache:
    """The BM25 index of the active release, rebuilt (once, under a lock) when it changes."""

    def __init__(self):
        self.index = BM25Index()
        self._lock = threading.Lock()

    def get(self, release_id, load) -> BM25Index:
        if self.index.release_id == str(release_id):
            return self.index
        with self._lock:
            if self.index.release_id != str(release_id):
                started = time.perf_counter()
                self.index = BM25Index.build(release_id, load())
                log.info('bm25 index built', extra={
                    'event': 'bm25_built', 'docs': len(self.index),
                    'seconds': round(time.perf_counter() - started, 1)})
        return self.index


@dataclass
class Retrieval:
    status: str = 'ok'
    candidates: list[Candidate] = field(default_factory=list)
    children: dict[str, dict] = field(default_factory=dict)
    release_id: str | None = None
    degraded: list[str] = field(default_factory=list)


class RagService:
    def __init__(self, engine: Engine, settings, llm: AsyncLLM | None, sparse: SparseCache,
                 embedder=None, reranker=None, cpu: asyncio.Semaphore | None = None):
        self.engine, self.settings, self.llm, self.sparse = engine, settings, llm, sparse
        self.embedder, self.reranker = embedder, reranker
        self.cpu = cpu or asyncio.Semaphore(1)

    # ---- public ------------------------------------------------------------------------------
    async def ask(self, principal: Principal, body: AskIn) -> AskOut:
        timings: dict[str, int] = {}
        question = ' '.join(nfc(body.question).split())
        thinking = self.settings.rag_thinking if body.thinking is None else body.thinking
        out = AskOut(status='ok', question=question, settings=self._settings(thinking, body),
                     versions=self._versions())

        clock = time.perf_counter()
        vector, problem = await self._embed(question)
        timings['embed'] = _ms(clock)
        if problem:
            out.degraded.append(problem)

        clock = time.perf_counter()
        found = await anyio.to_thread.run_sync(functools.partial(
            self._retrieve, principal, body, question, vector))
        timings['retrieve'] = _ms(clock)
        out.degraded += found.degraded
        if found.status != 'ok':
            out.status = found.status
            out.timings_ms = timings
            return out

        clock = time.perf_counter()
        ranked = await self._rerank(question, found, body.rerank, out.degraded)
        timings['rerank'] = _ms(clock)

        clock = time.perf_counter()
        parents = await anyio.to_thread.run_sync(functools.partial(
            self._parents, principal, ranked, found.children))
        timings['parents'] = _ms(clock)
        out.parents = parents
        out.children = self._children_out(ranked, found.children, parents)

        clock = time.perf_counter()
        await self._generate(out, question, thinking)
        timings['generate'] = _ms(clock)
        out.timings_ms = {**timings, 'total': sum(timings.values())}
        return out

    # ---- steps ---------------------------------------------------------------------------------
    async def _embed(self, question: str) -> tuple[list[float] | None, str | None]:
        if self.embedder is None:
            return None, 'dense_unavailable'
        try:
            async with self.cpu:
                vectors = await anyio.to_thread.run_sync(self.embedder.encode, [question], 'query')
            return vectors[0], None
        except Exception:  # noqa: BLE001 - a broken embedder degrades to sparse-only
            log.exception('query embedding failed', extra={'event': 'embed_failed'})
            return None, 'dense_unavailable'

    def _retrieve(self, principal: Principal, body: AskIn, question: str,
                  vector: list[float] | None) -> Retrieval:
        settings = self.settings
        with transaction(self.engine, principal.user_id) as conn:
            repo = RagRepository(conn)
            active = repo.active()
            if active is None:
                return Retrieval(status='empty_corpus')
            school_ids = []
            if body.school_keys:
                school_ids = [str(r[0]) for r in conn.execute(text(
                    'SELECT id FROM schools WHERE key = ANY(:k)'), {'k': body.school_keys})]
            spec = Spec(query=question, school_ids=school_ids, book_ids=list(body.book_ids))
            cte, params = repo.scope(principal, spec, active['release_id'])
            allowed = repo.scope_ids(cte, params)
            if not allowed:
                return Retrieval(status='no_match' if spec.filtered else 'empty_corpus')
            found = Retrieval(release_id=str(active['release_id']))
            dense = []
            if vector is not None and active['physical_table']:
                dense = repo.dense(cte, params, active['physical_table'], vector,
                                   settings.rag_dense_candidates)
            elif vector is not None:
                found.degraded.append('dense_unavailable')
            index = self.sparse.get(active['release_id'],
                                    lambda: repo.bm25_documents(active['release_id']))
            sparse = index.search(question, settings.rag_sparse_candidates, allowed)
            candidates = fuse(dense, sparse, settings.rag_dense_weight, settings.rag_sparse_weight)
            if not candidates:
                return Retrieval(status='no_match', release_id=found.release_id)
            found.children = repo.children(cte, params, [c.chunk_id for c in candidates])
            candidates = [c for c in candidates if c.chunk_id in found.children]
            simhashes = {cid: (row['meta'] or {}).get('simhash')
                         for cid, row in found.children.items()}
            books = {cid: row['book_title'] for cid, row in found.children.items()}
            found.candidates = collapse(candidates, simhashes, books, settings.rag_dedupe_bits)
            return found

    async def _rerank(self, question: str, found: Retrieval, enabled: bool,
                      degraded: list[str]) -> list[Candidate]:
        depth = min(self.settings.rag_rerank_depth, len(found.candidates))
        if not enabled or depth == 0:
            return found.candidates
        if self.reranker is None:
            degraded.append('reranker_unavailable')
            return found.candidates
        head = found.candidates[:depth]
        chars = self.settings.rag_rerank_chars
        documents = []
        for candidate in head:
            row = found.children[candidate.chunk_id]
            header = (row['meta'] or {}).get('header', '')
            documents.append(f"{header}\n{row['text'][:chars]}")
        try:
            async with self.cpu:
                scores = await asyncio.wait_for(anyio.to_thread.run_sync(
                    self.reranker.rerank, question, documents, abandon_on_cancel=True),
                    timeout=self.settings.rag_rerank_timeout)
        except Exception:  # noqa: BLE001 - timeout or model error: keep the fused order
            log.warning('rerank failed', extra={'event': 'rerank_failed'})
            degraded.append('reranker_unavailable')
            return found.candidates
        for candidate, score in zip(head, scores):
            candidate.rerank = score
        ordered = sorted(head, key=lambda c: -c.rerank)
        for rank, candidate in enumerate(ordered, start=1):
            candidate.rerank_rank = rank
        return ordered + found.candidates[depth:]

    def _parents(self, principal: Principal, ranked: list[Candidate],
                 children: dict[str, dict]) -> list[ParentOut]:
        """Parents of the best children, in rank order, within the context budget."""
        budget = self.settings.rag_context_tokens
        order: list[str] = []
        selected_by: dict[str, list[str]] = {}
        depth = max(self.settings.rag_rerank_depth, 8)
        for candidate in ranked[:max(depth, 12)]:
            parent_id = children[candidate.chunk_id]['parent_id']
            if parent_id is None:
                continue
            parent_id = str(parent_id)
            if parent_id not in selected_by:
                order.append(parent_id)
                selected_by[parent_id] = []
            selected_by[parent_id].append(candidate.chunk_id)
        with transaction(self.engine, principal.user_id) as conn:
            repo = RagRepository(conn)
            rows = repo.parents(order)
            members = repo.parent_children(order)
            rules = repo.reviewed_rules([c for ids in members.values() for c in ids])
        out: list[ParentOut] = []
        used = 0
        for parent_id in order:
            row = rows.get(parent_id)
            if row is None:
                continue
            cost = row['token_count'] + PARENT_OVERHEAD
            if out and used + cost > budget:
                continue          # a smaller later parent may still fit
            used += cost
            meta = row['meta'] or {}
            parent_rules = {r['assertion_id']: r for cid in members.get(parent_id, [])
                            for r in rules.get(cid, [])}
            out.append(ParentOut(
                handle=f'P{len(out) + 1}', parent_id=parent_id,
                book_title=meta.get('book_title', ''), school=meta.get('school'),
                breadcrumb=meta.get('breadcrumb') or [], header=meta.get('header', ''),
                page_start=meta.get('page_start'), page_end=meta.get('page_end'),
                summary=row['summary'], text=row['text'], tokens=row['token_count'],
                child_ids=selected_by[parent_id], expert_reviewed=bool(parent_rules),
                reviewed_rules=[ReviewedRule(**r) for r in parent_rules.values()]))
        return out

    async def _generate(self, out: AskOut, question: str, thinking: bool) -> None:
        if not out.parents:
            out.status = 'no_match'
            return
        if self.llm is None:
            out.status = 'provider_not_configured'
            return
        payload = [{'handle': p.handle, 'text': p.text, 'header': p.header,
                    'reviewed_rules': [r.model_dump() for r in p.reviewed_rules]}
                   for p in out.parents]
        messages = prompts.answer_messages(question, payload)
        try:
            draft, completion = await self.llm.structured(
                messages, prompts.DraftAnswer, self.settings.rag_answer_tokens,
                self.settings.rag_temperature, thinking)
        except LLMError as exc:
            out.status, out.error = 'provider_error', exc.code
            return
        out.usage = {'prompt_tokens': completion.prompt_tokens,
                     'completion_tokens': completion.completion_tokens,
                     'model': completion.model, 'latency_ms': completion.latency_ms}
        self._validate(out, draft)

    def _validate(self, out: AskOut, draft: prompts.DraftAnswer) -> None:
        handles = {p.handle for p in out.parents}
        out.raw_answer = draft.answer
        out.model_said_insufficient = draft.insufficient
        named = HANDLE.findall(draft.answer) + [c.strip('[] ') for c in draft.cited]
        valid = [h for h in dict.fromkeys(named) if h in handles]
        out.invalid_citations = [h for h in dict.fromkeys(named) if h not in handles]
        answer = draft.answer
        for bad in out.invalid_citations:
            answer = answer.replace(f'[{bad}]', '')
        out.answer = answer.strip()
        out.cited = valid
        for parent in out.parents:
            parent.cited = parent.handle in valid
        if draft.insufficient or not valid:
            out.status = 'insufficient_evidence'
            if not out.answer:
                out.answer = INSUFFICIENT

    # ---- views ---------------------------------------------------------------------------------
    def _children_out(self, ranked: list[Candidate], children: dict[str, dict],
                      parents: list[ParentOut]) -> list[ChildOut]:
        handle_of = {p.parent_id: p.handle for p in parents}
        reviewed = {cid for p in parents for cid in p.child_ids if p.expert_reviewed}
        out = []
        for rank, candidate in enumerate(ranked[:SHOWN_CHILDREN], start=1):
            row = children[candidate.chunk_id]
            meta = dict(row['meta'] or {})
            parent_id = str(row['parent_id']) if row['parent_id'] else None
            out.append(ChildOut(
                chunk_id=candidate.chunk_id, rank=rank, book_title=row['book_title'],
                edition=row['edition_label'], school=meta.get('school'),
                breadcrumb=meta.get('breadcrumb') or [], section_path=row['section_path'],
                page_start=meta.get('page_start'), page_end=meta.get('page_end'),
                printed_pages=meta.get('printed_pages'), speaker_layer=row['speaker_layer'],
                unit_kind=meta.get('unit_kind') or row['kind'], header=meta.get('header', ''),
                text=row['text'], also_in=candidate.also_in,
                scores=Scores(dense_raw=candidate.dense_raw, sparse_raw=candidate.sparse_raw,
                              dense=round(candidate.dense, 4), sparse=round(candidate.sparse, 4),
                              fused=round(candidate.fused, 4), rerank=candidate.rerank,
                              dense_rank=candidate.dense_rank, sparse_rank=candidate.sparse_rank,
                              rerank_rank=candidate.rerank_rank),
                parent_handle=handle_of.get(parent_id), expert_reviewed=candidate.chunk_id in reviewed,
                meta={k: meta.get(k) for k in ('entities', 'charts', 'has_chart', 'extraction',
                                               'ocr_confidence', 'tokens', 'oversized_unit')},
                spans=[{'page_revision_id': str(sp['page_revision_id']),
                        'physical_page_number': sp['physical_page_number'],
                        'printed_page_label': sp['printed_page_label'],
                        'start_offset': sp['start_offset'], 'end_offset': sp['end_offset']}
                       for sp in row.get('spans', [])]))
        return out

    def _settings(self, thinking: bool, body: AskIn) -> dict:
        s = self.settings
        return {'dense_weight': s.rag_dense_weight, 'sparse_weight': s.rag_sparse_weight,
                'dense_candidates': s.rag_dense_candidates,
                'sparse_candidates': s.rag_sparse_candidates,
                'rerank_depth': s.rag_rerank_depth if body.rerank else 0,
                'rerank_chars': s.rag_rerank_chars, 'dedupe_bits': s.rag_dedupe_bits,
                'context_tokens': s.rag_context_tokens, 'answer_tokens': s.rag_answer_tokens,
                'temperature': s.rag_temperature, 'thinking': thinking,
                'school_keys': body.school_keys}

    def _versions(self) -> dict:
        s = self.settings
        return {'llm': self.llm.config.model if self.llm else None,
                'embedder': f'{s.rag_embedding_model}@{s.rag_embedding_revision[:12]}',
                'reranker': f'{s.rag_reranker_model}@{s.rag_reranker_revision[:12]}',
                'answer_prompt': prompts.ANSWER_PROMPT_VERSION,
                'summary_prompt': prompts.SUMMARY_PROMPT_VERSION}


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
