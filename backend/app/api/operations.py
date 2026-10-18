"""Operations metrics and alerts for admins (docs/12 · Observability; T051)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..ops import metrics
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, permission

router = APIRouter(prefix='/operations', tags=['operations'])


class Alert(BaseModel):
    code: str
    severity: Literal['low', 'medium', 'high']
    message: str


class OperationsMetrics(BaseModel):
    collected_at: datetime
    database: dict = Field(description='counts across owners: queues, failures, leases, pages,'
                           ' chat runs, rejected claims, rule outcomes, usage, backups')
    process: dict = Field(description='this API process: retrieval latency window, DB pool, disk')
    alerts: list[Alert]


@router.get('/metrics', response_model=Envelope[OperationsMetrics],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('A'))
def operations_metrics(request: Request, principal: Principal = Depends(require_role('admin')),
                       conn: Connection = Depends(db)) -> dict:
    settings = request.app.state.settings
    root = settings.storage_root if settings.storage_backend == 'local' else None
    return envelope(metrics.collect(conn, request.app.state.engine, root, principal.user_id))
