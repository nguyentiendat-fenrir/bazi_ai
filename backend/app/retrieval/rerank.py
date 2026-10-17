"""Rerank adapters (docs/07 · step 6): order fused candidates by a cross-encoder.

The active reranker is the newest enabled ``model_profiles`` row of kind
``reranker``. ``openai_compatible`` posts ``{model, query, documents}`` to
``{base_url}/rerank`` (llama.cpp, TEI and Jina-style servers answer
``{results: [{index, relevance_score}]}``); ``fixture-overlap`` scores word
overlap offline for tests and is refused in production. A reranker orders
candidates, it never decides facts or which sources are valid; when it is
missing, slow or failing, the fused order stands and the result says so.
Excerpts are book text: an external profile only sees them when every
candidate's version allows external processing.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..documents.text import fold

TIMEOUT = 10.0
MAX_CANDIDATES = 40
_WORD = re.compile(r'\w+', re.UNICODE)


class RerankError(Exception):
    pass


@dataclass(frozen=True)
class RerankProfile:
    id: str
    provider: str
    model_name: str
    config: dict
    secret_ref: str | None

    @property
    def local(self) -> bool:
        return self.provider.startswith('fixture') or self.config.get('locality') == 'local'


def active_profile(conn: Connection) -> RerankProfile | None:
    row = conn.execute(text(
        "SELECT id, provider, model_name, config, secret_ref FROM model_profiles"
        " WHERE kind = 'reranker' AND enabled ORDER BY created_at DESC LIMIT 1")).mappings().first()
    return RerankProfile(str(row['id']), row['provider'], row['model_name'], row['config'] or {},
                         row['secret_ref']) if row else None


class OverlapReranker:
    """Folded word overlap with the query. Deterministic, offline, not semantic."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        wanted = set(_WORD.findall(fold(query)))
        scores = []
        for document in documents:
            words = set(_WORD.findall(fold(document)))
            scores.append(len(wanted & words) / (len(wanted) or 1))
        return scores


class OpenAICompatibleReranker:
    def __init__(self, profile: RerankProfile, transport: httpx.BaseTransport | None = None):
        self.profile = profile
        self.transport = transport

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        base = self.profile.config.get('base_url')
        if not base:
            raise RerankError('reranker profile has no base_url')
        headers = {}
        if self.profile.secret_ref and os.environ.get(self.profile.secret_ref):
            headers['Authorization'] = f'Bearer {os.environ[self.profile.secret_ref]}'
        try:
            with httpx.Client(transport=self.transport,
                              timeout=self.profile.config.get('timeout', TIMEOUT)) as client:
                response = client.post(f"{base.rstrip('/')}/rerank", headers=headers, json={
                    'model': self.profile.model_name, 'query': query, 'documents': documents})
        except httpx.HTTPError as exc:
            raise RerankError(f'reranker unreachable: {type(exc).__name__}') from None
        if response.status_code != 200:
            raise RerankError(f'reranker answered {response.status_code}')
        scores = [None] * len(documents)
        for item in response.json().get('results', []):
            index = item.get('index')
            if isinstance(index, int) and 0 <= index < len(documents):
                scores[index] = float(item.get('relevance_score', item.get('score', 0.0)))
        if any(s is None for s in scores):
            raise RerankError('reranker skipped documents')
        return scores


def build(profile: RerankProfile, app_env: str, transport=None):
    if profile.provider == 'fixture-overlap':
        if app_env == 'production':
            raise RerankError('fixture reranker is test-only')
        return OverlapReranker()
    if profile.provider == 'openai_compatible':
        return OpenAICompatibleReranker(profile, transport)
    raise RerankError(f'unsupported reranker provider {profile.provider}')


def rerank_hits(conn: Connection, query: str, hits: list[dict], app_env: str,
                transport=None) -> tuple[list[dict], str | None]:
    """Hits reordered by the reranker (top ``MAX_CANDIDATES``), or unchanged with a reason."""
    profile = active_profile(conn)
    if profile is None or not hits:
        return hits, None if profile else 'reranker_not_configured'
    head, tail = hits[:MAX_CANDIDATES], hits[MAX_CANDIDATES:]
    if not profile.local:
        allowed = conn.execute(text(
            'SELECT bool_and(external_processing_allowed) FROM book_versions'
            ' WHERE id = ANY(CAST(:ids AS uuid[]))'),
            {'ids': sorted({h['book_version_id'] for h in head})}).scalar()
        if not allowed:
            return hits, 'reranker_skipped_external'
    try:
        scores = build(profile, app_env, transport).rerank(query, [h['text'] for h in head])
    except RerankError:
        return hits, 'reranker_unavailable'
    for hit, score in zip(head, scores):
        hit['rerank_score'] = score
    ordered = sorted(head, key=lambda h: (-h['rerank_score'], -h['score'], h['chunk_id']))
    return ordered + tail, None
