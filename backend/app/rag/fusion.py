"""Hybrid fusion and near-duplicate collapse (pure functions).

Fusion: each candidate list is min-max normalised *per query* to [0, 1], then
``fused = w_dense · dense + w_sparse · sparse``; a child missing from one list
gets 0 on that side. With a single candidate in a list its normalised score is
1. Raw and normalised scores are kept for the judges.

Dedupe: the same passage in another edition (Trích Thiên Tủy ×3, Tử Bình Chân
Thuyên ×2) has a near-identical simhash. Walking the fused order, a child within
``bits`` of an already kept child is folded into it (``also_in``), so every
slot of the shortlist is a distinct passage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..ingestion.chunk_meta import hamming


@dataclass
class Candidate:
    chunk_id: str
    dense_raw: float | None = None
    sparse_raw: float | None = None
    dense: float = 0.0
    sparse: float = 0.0
    fused: float = 0.0
    dense_rank: int | None = None
    sparse_rank: int | None = None
    rerank: float | None = None
    rerank_rank: int | None = None
    also_in: list[dict] = field(default_factory=list)


def _normalise(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    low, high = min(scores.values()), max(scores.values())
    if high - low < 1e-12:
        return {key: 1.0 for key in scores}
    return {key: (value - low) / (high - low) for key, value in scores.items()}


def fuse(dense: list[tuple[str, float]], sparse: list[tuple[str, float]],
         dense_weight: float, sparse_weight: float) -> list[Candidate]:
    """``dense``/``sparse``: (chunk_id, raw score) best first; higher raw = better."""
    candidates: dict[str, Candidate] = {}
    for rank, (chunk_id, score) in enumerate(dense, start=1):
        candidates.setdefault(chunk_id, Candidate(chunk_id))
        candidates[chunk_id].dense_raw, candidates[chunk_id].dense_rank = score, rank
    for rank, (chunk_id, score) in enumerate(sparse, start=1):
        candidates.setdefault(chunk_id, Candidate(chunk_id))
        candidates[chunk_id].sparse_raw, candidates[chunk_id].sparse_rank = score, rank
    dense_norm = _normalise(dict(dense))
    sparse_norm = _normalise(dict(sparse))
    for candidate in candidates.values():
        candidate.dense = dense_norm.get(candidate.chunk_id, 0.0)
        candidate.sparse = sparse_norm.get(candidate.chunk_id, 0.0)
        candidate.fused = dense_weight * candidate.dense + sparse_weight * candidate.sparse
    return sorted(candidates.values(),
                  key=lambda c: (-c.fused, c.dense_rank or 10 ** 6, c.sparse_rank or 10 ** 6))


def collapse(candidates: list[Candidate], simhashes: dict[str, int], books: dict[str, str],
             bits: int) -> list[Candidate]:
    """Fold near-duplicates into the first (best) occurrence; ``books`` names each child's book."""
    if bits <= 0:
        return candidates
    kept: list[Candidate] = []
    for candidate in candidates:
        mine = simhashes.get(candidate.chunk_id)
        twin = None
        if mine is not None:
            twin = next((k for k in kept if simhashes.get(k.chunk_id) is not None
                         and hamming(simhashes[k.chunk_id], mine) <= bits), None)
        if twin is None:
            kept.append(candidate)
        else:
            twin.also_in.append({'chunk_id': candidate.chunk_id,
                                 'book_title': books.get(candidate.chunk_id),
                                 'fused': round(candidate.fused, 4)})
    return kept
