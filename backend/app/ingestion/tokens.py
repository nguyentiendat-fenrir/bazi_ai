"""Token counting for chunk and context budgets.

Jina embeddings v5 and Qwen3 share the Qwen3 tokenizer, so one count serves the
embedder limit and the LLM context budget. The tokenizer file is read from the
model cache (``RAG_TOKENIZER`` = a ``tokenizer.json`` path, or a Hugging Face
repo id resolved offline from ``HF_HOME``). Without it (unit tests, empty
caches) an approximation is used: Vietnamese is about 1.4 Qwen tokens per
syllable, punctuation one each. The name of whichever counter ran is part of
the chunker version, so switching counters makes a new generation.
"""
from __future__ import annotations

from functools import lru_cache
import logging
import os
import re

log = logging.getLogger('bazi.tokens')
DEFAULT_REPO = 'jinaai/jina-embeddings-v5-text-small'
_WORD = re.compile(r'\w+|[^\w\s]', re.UNICODE)


@lru_cache(maxsize=1)
def _tokenizer():
    source = os.environ.get('RAG_TOKENIZER', DEFAULT_REPO)
    try:
        from tokenizers import Tokenizer
    except ImportError:
        return None
    try:
        if source.endswith('.json'):
            return Tokenizer.from_file(source)
        from huggingface_hub import hf_hub_download
        return Tokenizer.from_file(hf_hub_download(source, 'tokenizer.json', local_files_only=True))
    except Exception:  # noqa: BLE001 - missing cache is a supported state, not an error
        log.info('tokenizer not available, using approximation', extra={'event': 'tokenizer_fallback'})
        return None


def counter_name() -> str:
    return 'qwen3-tokenizer' if _tokenizer() is not None else 'approx-1.4'


def count_tokens(text: str) -> int:
    tokenizer = _tokenizer()
    if tokenizer is not None:
        return len(tokenizer.encode(text, add_special_tokens=False).ids)
    words = _WORD.findall(text)
    return round(sum(1.4 if w[0].isalnum() else 1.0 for w in words))
