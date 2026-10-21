"""Chat research mode on the RAG pilot pipeline (reasoner worker side).

The reasoner is a synchronous worker, so each run drives ``RagService.ask`` in its
own event loop (the async Qwen client is created and closed inside it); the CPU
models and the BM25 index are process-wide and survive between runs.

The validated ``AskOut`` becomes the chat ``Answer``: the answer text with its
``[P#]`` markers is the summary, and each cited parent becomes a validated
``source_statement`` claim whose citation opens the source page at the span of
the retrieved child (citations stay display data in the structured answer; the
pilot does not materialise evidence rows for them).
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

from ..auth.service import Principal
from ..core.config import load_settings
from ..reasoning.answer import Answer, Citation, Claim
from .llm import AsyncLLM, config_from
from .models import embedder, embedder_spec, reranker, reranker_spec
from .schemas import AskIn, AskOut
from .service import RagService, SparseCache

STATUS = {'ok': 'supported', 'insufficient_evidence': 'insufficient_evidence',
          'empty_corpus': 'empty_corpus', 'no_match': 'insufficient_evidence',
          'provider_not_configured': 'provider_not_configured', 'provider_error': 'partial'}


@lru_cache(maxsize=1)
def _shared():
    settings = load_settings()
    return settings, SparseCache()


def enabled() -> bool:
    """Research runs use the RAG pilot where its models are loaded (not in unit/integration
    tests, which set ``RAG_LOAD_MODELS=false`` and keep the fixture-provider path)."""
    return _shared()[0].rag_load_models


def run_research(engine, principal: Principal, question: str, school_keys: list[str],
                 book_ids: list) -> AskOut:
    settings, sparse = _shared()

    async def go() -> AskOut:
        config = config_from(settings)
        llm = AsyncLLM(config) if config else None
        try:
            service = RagService(engine, settings, llm, sparse,
                                 embedder(embedder_spec(settings)),
                                 reranker(reranker_spec(settings)) if settings.rag_rerank_depth
                                 else None)
            return await service.ask(principal, AskIn(question=question, school_keys=school_keys,
                                                      book_ids=book_ids))
        finally:
            if llm is not None:
                await llm.aclose()
    return asyncio.run(go())


def to_answer(out: AskOut, trace_ref: dict) -> Answer:
    children = {c.chunk_id: c for c in out.children}
    claims = []
    for parent in out.parents:
        if not parent.cited:
            continue
        spans = [s for cid in parent.child_ids if cid in children for s in children[cid].spans]
        pages = sorted({s.physical_page_number for s in spans}) or \
            [p for p in (parent.page_start, parent.page_end) if p]
        claims.append(Claim(
            id=parent.handle, text=f'[{parent.handle}] {parent.header}', kind='source_statement',
            school_key=None, support_status='validated', inference_level='direct',
            citations=[Citation(
                handle=parent.handle, evidence_span_ids=[], book_id='', book_title=parent.book_title,
                edition_label='', section_title=' › '.join(parent.breadcrumb) or None,
                speaker_layer='unknown', pages=pages,
                printed_pages=[s.printed_page_label for s in spans if s.printed_page_label],
                quote=(parent.summary or parent.text[:400]), support=1.0,
                viewer=[{'page_revision_id': s.page_revision_id, 'start_offset': s.start_offset,
                         'end_offset': s.end_offset} for s in spans[:3]])]))
    limitations = []
    if out.invalid_citations:
        limitations.append('Đã bỏ mã nguồn không có trong tài liệu: ' + ', '.join(out.invalid_citations))
    if out.degraded:
        limitations.append('Truy xuất suy giảm: ' + ', '.join(out.degraded))
    if out.status == 'provider_error':
        limitations.append(f'Mô hình lỗi ({out.error}); chưa có câu trả lời.')
    summary = out.answer or {
        'empty_corpus': 'Kho tra cứu chưa có sách nào được publish.',
        'no_match': 'Không tìm thấy đoạn sách nào liên quan.',
        'provider_not_configured': 'Chưa cấu hình mô hình ngôn ngữ; xem các đoạn nguồn bên dưới.',
    }.get(out.status, 'Không có câu trả lời.')
    return Answer(status=STATUS.get(out.status, 'partial'), mode='research', summary=summary,
                  claims=claims, limitations=limitations,
                  trace_ref={**trace_ref, 'rag': {'versions': out.versions, 'settings': out.settings,
                                                  'timings_ms': out.timings_ms}})
