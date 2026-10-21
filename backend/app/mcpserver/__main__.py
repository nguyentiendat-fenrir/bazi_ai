"""stdio transport for a local MCP client (Claude Code/Desktop, an agent on the same host).

    python -m backend.app.mcpserver          # MCP_USER_EMAIL and the database from the environment

Loads the CPU retrieval models once (RAG_LOAD_MODELS=false runs BM25 only).
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import create_engine, pool

from ..core.config import load_settings
from ..rag.service import RagService, SparseCache
from .backend import Backend
from .tools import build_server


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)   # stdout is the protocol
    settings = load_settings()
    if not settings.mcp_user_email:
        print('MCP_USER_EMAIL is not configured', file=sys.stderr)
        return 2
    embed = rerank = None
    if settings.rag_load_models:
        from ..rag.models import embedder, embedder_spec, reranker, reranker_spec
        embed = embedder(embedder_spec(settings))
        rerank = reranker(reranker_spec(settings)) if settings.rag_rerank_depth else None
    engine = create_engine(settings.runtime_database_url, poolclass=pool.NullPool)
    service = RagService(engine, settings, None, SparseCache(), embed, rerank)
    build_server(Backend(engine, settings, service), settings).run('stdio')
    return 0


if __name__ == '__main__':
    sys.exit(main())
