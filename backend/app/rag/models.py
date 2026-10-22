"""In-process Jina models: embeddings (query/document) and the listwise reranker.

Loaded once per process — by the API lifespan, or on first use in a worker —
from the model cache (``HF_HOME``) at a pinned revision, because both repos
ship remote code. Inference is CPU-bound and blocking: the API calls it via
``anyio.to_thread`` behind a semaphore, never on the event loop.

Measured on this host (i7-13700K, 16 threads, fp32; scratch spike 2026-10-21; documents are
batched shortest-first, 2.2× faster than input order on mixed lengths, same vectors):
query embedding ~100 ms; documents ~1.8/s at ~300 tokens; reranking 8
candidates of ~600 chars ~4 s, 12 ~7 s. int8 dynamic quantisation gave no gain
(no AVX-512/AMX), so fp32 stays.

GPU: ``RAG_DEVICE=cuda`` loads both on the GPU (OCR moved to another machine, so the 4090 has
room); ``RAG_DTYPE`` picks the weights' precision there (bf16 by default on the GPU: fp32 of
both models does not fit next to Qwen and Gemma). Vectors from bf16 differ from fp32 ones in
the last digits, so a collection embedded on the CPU should be re-embedded (or measured) after
the switch. No GPU in the container → the CPU, with a warning, so the API still starts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
import threading
import time

log = logging.getLogger('bazi.rag.models')
_LOCK = threading.Lock()
_CACHE: dict[tuple, object] = {}


DTYPES = {'fp32': 'float32', 'bf16': 'bfloat16', 'fp16': 'float16'}


def _env_device() -> str:
    return os.environ.get('RAG_DEVICE', 'cpu').strip() or 'cpu'


def _env_dtype() -> str:
    return os.environ.get('RAG_DTYPE', '').strip()


@dataclass(frozen=True)
class ModelSpec:
    name: str
    revision: str
    threads: int = 16
    device: str = field(default_factory=_env_device)     # cpu | cuda | cuda:N
    dtype: str = field(default_factory=_env_dtype)       # fp32 | bf16 | fp16; '' = by device


def _torch(threads: int):
    import torch
    torch.set_num_threads(threads)
    return torch


def placement(spec: ModelSpec, torch) -> tuple[str, object]:
    """(device, torch dtype) to load with: CUDA only when present; half precision only there."""
    device = spec.device
    if device.startswith('cuda') and not torch.cuda.is_available():
        log.warning('no GPU visible; Jina models stay on the CPU',
                    extra={'event': 'rag_device_fallback', 'model': spec.name})
        device = 'cpu'
    name = spec.dtype or ('bf16' if device.startswith('cuda') else 'fp32')
    if name not in DTYPES:
        raise ValueError(f'RAG_DTYPE must be one of {sorted(DTYPES)}')
    if device == 'cpu':
        name = 'fp32'                 # half precision on this CPU is slower, not faster
    return device, getattr(torch, DTYPES[name])


def _load(spec: ModelSpec):
    torch = _torch(spec.threads)
    from transformers import AutoModel
    device, dtype = placement(spec, torch)
    model = AutoModel.from_pretrained(spec.name, revision=spec.revision, trust_remote_code=True,
                                      dtype=dtype).to(device).eval()
    return model, device, str(dtype).removeprefix('torch.')


class JinaEmbedder:
    """jina-embeddings-v5-text-small, retrieval adapter, L2-normalised 1024-d vectors."""

    max_length = 1024
    batch_size = 16

    def __init__(self, spec: ModelSpec):
        started = time.perf_counter()
        self.model, self.device, self.dtype = _load(spec)
        self.spec = spec
        self.dimension = int(self.model.config.hidden_size)
        log.info('embedder loaded', extra={'event': 'model_loaded', 'model': spec.name,
                                           'device': self.device, 'dtype': self.dtype,
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
        started = time.perf_counter()
        self.model, self.device, self.dtype = _load(spec)
        self.spec = spec
        log.info('reranker loaded', extra={'event': 'model_loaded', 'model': spec.name,
                                           'device': self.device, 'dtype': self.dtype,
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
