"""Operations metrics and alerts for admins (docs/12 · Observability; T051)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..ops import metrics
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission

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


class BackupDTO(BaseModel):
    id: str
    name: str
    state: Literal['running', 'succeeded', 'failed', 'verified']
    created_at: datetime
    verified_at: datetime | None
    archive_location: str = Field(description='path on the backup host, as the CLI saw it')
    db_schema_version: str
    encrypted: bool
    manifest_sha256: str


@router.get('/backups', response_model=ListEnvelope[BackupDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('A'))
def list_backups(limit: int = Query(default=30, ge=1, le=200),
                 principal: Principal = Depends(require_role('admin')),
                 conn: Connection = Depends(db)) -> dict:
    """Backups recorded by the CLI, newest first. A restore never depends on this table:
    it reads the manifest beside the archive (docs/12 · Restore runbook)."""
    rows = conn.execute(text(
        "SELECT b.id, j.target_manifest->>'name' AS name, b.state, b.created_at, b.verified_at,"
        ' b.archive_location, b.db_schema_version, b.encryption_key_ref, b.checksum'
        ' FROM backups b JOIN operation_jobs j ON j.id = b.operation_job_id'
        ' ORDER BY b.created_at DESC, b.id DESC LIMIT :n'), {'n': limit}).mappings().all()
    return {**envelope([{'id': str(r['id']), 'name': r['name'], 'state': r['state'],
                         'created_at': r['created_at'], 'verified_at': r['verified_at'],
                         'archive_location': r['archive_location'],
                         'db_schema_version': r['db_schema_version'],
                         'encrypted': r['encryption_key_ref'] != 'none',
                         'manifest_sha256': r['checksum'].strip()} for r in rows]),
            'page': {'next_cursor': None, 'has_more': False}}
