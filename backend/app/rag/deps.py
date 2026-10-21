"""Composition root of the RAG pilot: what the API builds once and injects per request.

``install(app, settings)`` runs inside the app lifespan: it creates the shared
async Qwen client and the ``RagService``, then loads the CPU models in a
background thread so the process answers ``/health/live`` at once and
``/health/ready`` reports ``rag_models`` until they are warm (cold load takes
~40 s). Tests replace ``rag_service`` through ``app.dependency_overrides`` or
set ``RAG_LOAD_MODELS=false``.
"""
from __future__ import annotations

import asyncio
import logging

import anyio
from fastapi import FastAPI, Request

from ..core.health import CheckResult, ReadinessCheck
from .llm import AsyncLLM, config_from
from .models import embedder, embedder_spec, reranker, reranker_spec
from .service import RagService, SparseCache

log = logging.getLogger('bazi.rag')


async def install(app: FastAPI, settings) -> None:
    config = config_from(settings)
    llm = AsyncLLM(config) if config else None
    app.state.rag = RagService(app.state.engine, settings, llm, SparseCache(),
                               cpu=asyncio.Semaphore(1))
    app.state.rag_models = 'off' if not settings.rag_load_models else 'loading'
    if settings.rag_load_models:
        app.state.rag_loader = asyncio.create_task(_load(app, settings))


async def uninstall(app: FastAPI) -> None:
    loader = getattr(app.state, 'rag_loader', None)
    if loader is not None and not loader.done():
        loader.cancel()
    service = getattr(app.state, 'rag', None)
    if service is not None and service.llm is not None:
        await service.llm.aclose()


async def _load(app: FastAPI, settings) -> None:
    service: RagService = app.state.rag
    try:
        service.embedder = await anyio.to_thread.run_sync(embedder, embedder_spec(settings))
        if settings.rag_rerank_depth:
            service.reranker = await anyio.to_thread.run_sync(reranker, reranker_spec(settings))
        app.state.rag_models = 'ready'
    except Exception:  # noqa: BLE001 - the API still serves; /ask degrades and readiness says why
        log.exception('rag model load failed', extra={'event': 'rag_models_failed'})
        app.state.rag_models = 'failed'


def readiness(app: FastAPI) -> ReadinessCheck:
    async def run() -> CheckResult:
        state = getattr(app.state, 'rag_models', 'off')
        return CheckResult('ok' if state in ('ready', 'off') else 'degraded', state.upper())
    return ReadinessCheck('rag_models', essential=False, run=run)


def rag_service(request: Request) -> RagService:
    return request.app.state.rag
