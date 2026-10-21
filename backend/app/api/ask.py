"""``POST /ask``: one grounded RAG answer with everything retrieved (RAG pilot).

Thin router: it validates input, resolves the caller, and hands over to
``rag.service``. The handler is ``async`` because the model call is awaited I/O;
the service moves the blocking work (database, CPU models) to threads.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth.deps import current_principal
from ..auth.service import Principal
from ..rag.deps import rag_service
from ..rag.schemas import AskIn, AskOut
from ..rag.service import RagService
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, permission

router = APIRouter(tags=['rag'])


@router.post('/ask', response_model=Envelope[AskOut], responses=AUTHENTICATED_ERRORS,
             openapi_extra=permission('R'),
             summary='Answer a question from the published books only, with sources')
async def ask(body: AskIn, principal: Principal = Depends(current_principal),
              service: RagService = Depends(rag_service)) -> dict:
    return envelope(await service.ask(principal, body))
