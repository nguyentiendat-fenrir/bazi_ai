"""Embedding providers behind one interface (docs/09 · Provider adapters, ADR-16).

No provider, model or secret is hardcoded: a provider is built from a
``model_profiles`` row. Secrets are referenced by an allowlisted environment
variable name (``secret_ref``), never stored in the profile.

``fixture-hashing`` is a deterministic offline embedder for tests and empty
deployments; it is flagged ``is_fixture`` and refused in production.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
import re

import httpx

SECRET_REFS = frozenset({'EMBEDDING_API_KEY', 'LLM_API_KEY'})
_TOKEN = re.compile(r'\w+', re.UNICODE)


class EmbeddingError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code, self.retryable = code, retryable


@dataclass(frozen=True)
class EmbeddingProfile:
    id: str
    provider: str
    model_name: str
    model_revision: str
    dimension: int
    config: dict
    secret_ref: str | None
    profile_hash: str

    @property
    def is_fixture(self) -> bool:
        return self.provider.startswith('fixture')


def _l2(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class HashingEmbedder:
    """Feature hashing of word unigrams and bigrams. Deterministic, offline, not semantic."""

    def __init__(self, profile: EmbeddingProfile):
        self.profile = profile
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        dim = self.profile.dimension
        vectors = []
        for text_ in texts:
            words = [w.lower() for w in _TOKEN.findall(text_)]
            features = words + [f'{a} {b}' for a, b in zip(words, words[1:])]
            vector = [0.0] * dim
            for feature in features:
                digest = hashlib.blake2b(feature.encode('utf-8'), digest_size=8).digest()
                index = int.from_bytes(digest[:4], 'little') % dim
                vector[index] += 1.0 if digest[4] & 1 else -1.0
            vectors.append(_l2(vector))
        return vectors


class OpenAICompatibleEmbedder:
    """POST {base_url}/embeddings — llama.cpp server and other OpenAI-compatible servers."""

    def __init__(self, profile: EmbeddingProfile, transport: httpx.BaseTransport | None = None):
        self.profile = profile
        base_url = profile.config.get('base_url')
        if not base_url:
            raise EmbeddingError('PROVIDER_NOT_CONFIGURED', 'embedding base_url missing', False)
        headers = {}
        if profile.secret_ref:
            secret = os.environ.get(profile.secret_ref)
            if not secret:
                raise EmbeddingError('PROVIDER_NOT_CONFIGURED',
                                     f'{profile.secret_ref} is not set', False)
            headers['Authorization'] = f'Bearer {secret}'
        self.client = httpx.Client(base_url=base_url.rstrip('/'), headers=headers,
                                   timeout=profile.config.get('timeout', 60), transport=transport)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self.client.post('/embeddings', json={
                'model': self.profile.model_name, 'input': texts})
        except httpx.TimeoutException:
            raise EmbeddingError('PROVIDER_TIMEOUT', 'embedding request timed out', True) from None
        except httpx.TransportError:
            raise EmbeddingError('PROVIDER_UNAVAILABLE', 'embedding server unreachable', True) from None
        if response.status_code == 429 or response.status_code >= 500:
            raise EmbeddingError('PROVIDER_UNAVAILABLE', f'HTTP {response.status_code}', True)
        if response.status_code >= 400:
            raise EmbeddingError('PROVIDER_REJECTED', f'HTTP {response.status_code}', False)
        data = sorted(response.json().get('data', []), key=lambda item: item['index'])
        vectors = [item['embedding'] for item in data]
        if len(vectors) != len(texts):
            raise EmbeddingError('EMBEDDING_COUNT_MISMATCH', 'provider returned a different count',
                                 False)
        return vectors


class LocalJinaEmbedder:
    """jina-embeddings-v5 in this process (CPU, or GPU with RAG_DEVICE=cuda), loaded once per
    process from the model cache.

    Profile config: ``revision`` (pinned commit), ``threads``; documents use the
    ``document`` prompt, queries (``embed_query``) the ``query`` prompt.
    """

    def __init__(self, profile: EmbeddingProfile):
        from ..rag.models import ModelSpec, embedder
        self.profile = profile
        try:
            self.model = embedder(ModelSpec(profile.model_name, profile.model_revision,
                                            int(profile.config.get('threads', 16))))
        except OSError as exc:      # not in the model cache and no network
            raise EmbeddingError('MODEL_UNAVAILABLE', str(exc)[:200], False) from None

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, 'document')

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, 'query')


def build_embedder(profile: EmbeddingProfile, app_env: str = 'dev', transport=None):
    if profile.secret_ref and profile.secret_ref not in SECRET_REFS:
        raise EmbeddingError('SECRET_REF_NOT_ALLOWED', 'secret_ref is not an allowlisted name', False)
    if profile.provider == 'fixture-hashing':
        if app_env == 'production':
            raise EmbeddingError('FIXTURE_IN_PRODUCTION', 'fixture embeddings are test-only', False)
        return HashingEmbedder(profile)
    if profile.provider == 'openai_compatible':
        return OpenAICompatibleEmbedder(profile, transport)
    if profile.provider == 'local-jina':
        return LocalJinaEmbedder(profile)
    raise EmbeddingError('UNKNOWN_PROVIDER', f'unsupported provider {profile.provider}', False)


def checked(vectors: list[list[float]], profile: EmbeddingProfile) -> list[list[float]]:
    for vector in vectors:
        if len(vector) != profile.dimension:
            raise EmbeddingError('EMBEDDING_DIMENSION_MISMATCH',
                                 f'expected {profile.dimension}, got {len(vector)}', False)
        if any(not math.isfinite(v) for v in vector):
            raise EmbeddingError('EMBEDDING_INVALID', 'non-finite value in embedding', False)
    return vectors
