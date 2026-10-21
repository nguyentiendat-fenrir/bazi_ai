"""Bind the harness ports to Qwen (OpenAI-compatible) and to the RAG pilot's retrieval."""
from __future__ import annotations

import re

from pydantic import ValidationError

from ..rag.llm import LLMConfig, LLMError, SyncLLM, _repair
from .ports import Model, ModelError, Passage, Retriever, T

_THINK = re.compile(r'<think>.*?</think>', re.S)


class QwenModel(Model):
    """Qwen through ``rag.llm.SyncLLM``: JSON schema output, thinking off except for the steps
    named in ``thinking_steps``, reasoning text stripped, one repair round on invalid JSON."""

    def __init__(self, config: LLMConfig, temperature: float = 0.1,
                 thinking_steps: frozenset[str] = frozenset(), transport=None):
        self.llm = SyncLLM(config, transport=transport)
        self.temperature, self.thinking_steps = temperature, thinking_steps
        self.usage: list[dict] = []

    def close(self) -> None:
        self.llm.close()

    def _parse(self, schema: type[T], text: str) -> T:
        raw = _THINK.sub('', text).strip()
        if raw.startswith('```'):
            raw = raw.strip('`').removeprefix('json').strip()
        return schema.model_validate_json(raw)

    def structured(self, step: str, messages: list[dict], schema: type[T], max_tokens: int) -> T:
        thinking = step in self.thinking_steps
        try:
            completion = self.llm.complete(messages, max_tokens, self.temperature, thinking, schema)
            self.usage.append({'step': step, 'prompt_tokens': completion.prompt_tokens,
                               'completion_tokens': completion.completion_tokens,
                               'latency_ms': completion.latency_ms})
            try:
                return self._parse(schema, completion.text)
            except ValidationError as error:
                retry = self.llm.complete(_repair(messages, completion, error), max_tokens,
                                          self.temperature, thinking, schema)
                try:
                    return self._parse(schema, retry.text)
                except ValidationError:
                    raise ModelError('SCHEMA_INVALID', f'{step}: invalid JSON twice') from None
        except LLMError as exc:
            raise ModelError(exc.code, str(exc)) from None


class RagRetriever(Retriever):
    """The RAG pilot's retrieval (dense + BM25, 0.8/0.2, dedupe, rerank, child → parent) for one
    principal, without the generation step. Uses ``RagService``'s synchronous internals."""

    def __init__(self, service, principal, school_keys: dict[str | None, str] | None = None):
        self.service, self.principal = service, principal
        # school label in parent meta -> school key ('Manh Phái' -> 'manh_phai' …)
        self.school_keys = school_keys or {'Tử Bình': 'tu_binh', 'Manh Phái': 'manh_phai',
                                           'Manh phái': 'manh_phai'}
        # What the searches returned since reset(), for the judge page: ParentOut by parent id,
        # and the scored children that selected a returned parent (first search wins).
        self.seen_parents: dict[str, object] = {}
        self.seen_children: dict[str, object] = {}

    def reset(self) -> None:
        self.seen_parents, self.seen_children = {}, {}

    def _school(self, value: str | None, asked: str | None) -> str | None:
        if asked:
            return asked
        if value in ('tu_binh', 'manh_phai'):
            return value
        return self.school_keys.get(value)

    def search(self, query: str, school: str | None, k: int) -> list[Passage]:
        from ..rag.schemas import AskIn
        service = self.service
        vector = None
        if service.embedder is not None:
            vector = service.embedder.encode([query], 'query')[0]
        body = AskIn(question=query, school_keys=[school] if school else [])
        found = service._retrieve(self.principal, body, query, vector)
        if found.status != 'ok':
            return []
        ranked = found.candidates
        depth = min(service.settings.rag_rerank_depth, len(ranked))
        if service.reranker is not None and depth:
            head = ranked[:depth]
            chars = service.settings.rag_rerank_chars
            docs = [f"{(found.children[c.chunk_id]['meta'] or {}).get('header', '')}\n"
                    f"{found.children[c.chunk_id]['text'][:chars]}" for c in head]
            for candidate, score in zip(head, service.reranker.rerank(query, docs)):
                candidate.rerank = score
            ranked = sorted(head, key=lambda c: -c.rerank) + ranked[depth:]
        parents = service._parents(self.principal, ranked, found.children)[:k]
        for child in service._children_out(ranked, found.children, parents):
            if child.parent_handle and child.chunk_id not in self.seen_children:
                child.meta['query'] = query
                child.meta['parent_id'] = str(found.children[child.chunk_id]['parent_id'])
                self.seen_children[child.chunk_id] = child
        out = []
        for p in parents:
            self.seen_parents.setdefault(p.parent_id, p)
            pages = ''
            if p.page_start:
                pages = f'tr.{p.page_start}' + (f'–{p.page_end}' if p.page_end and p.page_end != p.page_start else '')
            out.append(Passage(pid=p.parent_id, text=p.text, book=p.book_title, header=p.header,
                               school=self._school(p.school, school), pages=pages,
                               meta={'summary': p.summary, 'breadcrumb': p.breadcrumb}))
        return out
