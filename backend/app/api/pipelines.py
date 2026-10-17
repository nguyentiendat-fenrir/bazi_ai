"""Pipeline profiles a reviewer can pick when uploading or reprocessing (docs/10).

Profiles are created by the local CLI (``pipeline-profile``), next to the embedding
provisioning that needs the owner role; the API only lists them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..ingestion.profiles import list_pipeline_profiles
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, ListEnvelope, permission

router = APIRouter(tags=['ingestion'])


class EmbeddingRef(BaseModel):
    id: uuid.UUID
    provider: str
    model_name: str
    model_revision: str
    dimension: int | None
    locality: Literal['fixture', 'local', 'external'] = Field(
        description='external: book text leaves the server only for versions that allow it')
    ready: bool = Field(description='its vector collection is provisioned')


class PipelineProfileDTO(BaseModel):
    id: uuid.UUID
    name: str
    parser_version: str
    chunker_version: str
    normalizer_version: str
    renderer_version: str | None
    config: dict
    created_at: datetime
    embedding: EmbeddingRef


@router.get('/pipeline-profiles', response_model=ListEnvelope[PipelineProfileDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def pipeline_profiles(_: Principal = Depends(require_role('reviewer')),
                      conn: Connection = Depends(db)) -> dict:
    """Newest first; the UI preselects the newest profile whose collection is ready."""
    return {**envelope(list_pipeline_profiles(conn)),
            'page': {'next_cursor': None, 'has_more': False}}
