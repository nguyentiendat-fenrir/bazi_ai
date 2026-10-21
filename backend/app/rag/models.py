"""In-process Jina models on CPU: embeddings (query/document) and the listwise reranker.

Loaded once per process — by the API lifespan, or on first use in a worker —
from the model cache (``HF_HOME``) at a pinned revision, because both repos
ship remote code. Inference is CPU-bound and blocking: the API calls it via
``anyio.to_thread`` behind a semaphore, never on the event loop.

Measured on this host (i7-13700K, 16 threads, fp32; scratch spike 2026-10-21; documents are
batched shortest-first, 2.2× faster than input order on mixed lengths, same vectors):
query embedding ~100 ms; documents ~1.8/s at ~300 tokens; reranking 8
candidates of ~600 chars ~4 s, 12 ~7 s. int8 dynamic quantisation gave no gain
(no AVX-512/AMX), so fp32 stays.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time

log = logging.getLogger('bazi.rag.models')
_LOCK = threading.Lock()
_CACHE: dict[tuple, object] = {}


@dataclass(frozen=True)
class ModelSpec:
    name: str
    revision: str
    threads: int = 16


def _torch(threads: int):
    import torch
    torch.set_num_threads(threads)
    return torch


class JinaEmbedder:
    """jina-embeddings-v5-text-small, retrieval adapter, L2-normalised 1024-d vectors."""

    max_length = 1024
    batch_size = 16

    def __init__(self, spec: ModelSpec):
        torch = _torch(spec.threads)
        from transformers import AutoModel
        started = time.perf_counter()
        self.model = AutoModel.from_pretrained(spec.name, revision=spec.revision,
                                               trust_remote_code=True, dtype=torch.float32).eval()
        self.spec = spec
        self.dimension = int(self.model.config.hidden_size)
        log.info('embedder loaded', extra={'event': 'model_loaded', 'model': spec.name,
                                           'seconds': round(time.perf_counter() - started, 1)})

    def encode(self, texts: list[str], prompt: str = 'document') -> list[list[float]]:
        """Vectors in input order. Texts are batched shortest-first so a batch pads to
        similar lengths (padding to one long chunk made ingestion ~3× slower)."""
        import torch
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        vectors: list[list[float] | None] = [None] * len(texts)
        with torch.inference_mode():
            for start in range(0, len(order), self.batch_size):
                indices = order[start:start + self.batch_size]
                out = self.model.encode(texts=[texts[i] for i in indices], task='retrieval',
                                        prompt_name=prompt, max_length=self.max_length)
                for i, vector in zip(indices, out):
                    vectors[i] = vector.float().tolist()
        return vectors


class JinaReranker:
    """jina-reranker-v3.5 (listwise): one forward pass scores all candidates together."""

    def __init__(self, spec: ModelSpec):
        torch = _torch(spec.threads)
        from transformers import AutoModel
        started = time.perf_counter()
        self.model = AutoModel.from_pretrained(spec.name, revision=spec.revision,
                                               trust_remote_code=True, dtype=torch.float32).eval()
        self.spec = spec
        log.info('reranker loaded', extra={'event': 'model_loaded', 'model': spec.name,
                                           'seconds': round(time.perf_counter() - started, 1)})

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Relevance score per document, in input order."""
        import torch
        if not documents:
            return []
        with torch.inference_mode():
            results = self.model.rerank(query, documents)
        scores = [0.0] * len(documents)
        for item in results:
            scores[int(item['index'])] = float(item['relevance_score'])
        return scores


def embedder(spec: ModelSpec) -> JinaEmbedder:
    return _shared(('embedder', spec), lambda: JinaEmbedder(spec))


def reranker(spec: ModelSpec) -> JinaReranker:
    return _shared(('reranker', spec), lambda: JinaReranker(spec))


def _shared(key: tuple, factory):
    with _LOCK:
        if key not in _CACHE:
            _CACHE[key] = factory()
        return _CACHE[key]


def embedder_spec(settings) -> ModelSpec:
    return ModelSpec(settings.rag_embedding_model, settings.rag_embedding_revision,
                     settings.rag_cpu_threads)


def reranker_spec(settings) -> ModelSpec:
    return ModelSpec(settings.rag_reranker_model, settings.rag_reranker_revision,
                     settings.rag_cpu_threads)
