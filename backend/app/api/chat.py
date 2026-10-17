"""Conversations, messages, runs and their event stream (docs/09, docs/10 · chat).

The stream replays durable run events after ``Last-Event-ID`` (``{run_id}:{seq}``) and
then follows new ones until the run ends; it never re-runs the model. Validated claims
arrive as ``answer.claim``, the canonical answer as ``answer.completed``.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import time
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Connection, Engine

from ..auth.deps import current_principal, db, engine
from ..auth.service import Principal
from ..chat import conversations as chat
from ..core.concurrency import claim_idempotency, etag
from ..core.db import transaction
from ..core.errors import AppError
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['chat'])
NOT_FOUND = problem_responses(404)
TERMINAL = ('answer.completed', 'run.failed', 'run.cancelled')
HEARTBEAT_SECONDS = 15
STREAM_SECONDS = 300            # a client reconnects with Last-Event-ID after this


class ChatContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['research', 'chart_analysis', 'comparison'] = 'research'
    chart_id: uuid.UUID | None = None
    school_ids: list[uuid.UUID] = Field(default=[], max_length=6)
    method_ids: list[uuid.UUID] = Field(default=[], max_length=6)
    book_ids: list[uuid.UUID] = Field(default=[], max_length=20)
    as_of: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')


class ConversationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='', max_length=200)
    context: ChatContext = ChatContext()


class ConversationPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = Field(default=None, max_length=200)
    starred: bool | None = None
    context: ChatContext | None = None


class ConversationDTO(BaseModel):
    id: uuid.UUID
    title: str
    starred: bool
    context: dict
    revision: int
    messages_count: int
    created_at: datetime
    updated_at: datetime


class MessageDTO(BaseModel):
    id: uuid.UUID
    seq: int
    role: Literal['user', 'assistant']
    content: str
    status: Literal['pending', 'streaming', 'completed', 'failed', 'cancelled']
    run_id: uuid.UUID | None
    answer: dict | None
    created_at: datetime


class MessageInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1, max_length=4000)
    mode: Literal['research', 'chart_analysis', 'comparison'] | None = None


class RunDTO(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    mode: str
    state: Literal['queued', 'running', 'waiting_provider', 'completed', 'failed', 'cancelled']
    error: dict | None
    assistant_message_id: uuid.UUID
    answer: dict | None
    created_at: datetime
    updated_at: datetime


class PostedMessage(BaseModel):
    run: RunDTO
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID


class ConversationDeleted(BaseModel):
    conversation_id: uuid.UUID
    runs_cancelled: int


def _revision(request: Request) -> int:
    value = request.headers.get('If-Match')
    if value is None:
        raise AppError(428, 'PRECONDITION_REQUIRED', 'If-Match header with the revision is required')
    try:
        return int(value.strip().strip('"'))
    except ValueError:
        raise AppError(412, 'REVISION_MISMATCH', 'If-Match must be the revision') from None


@router.get('/conversations', response_model=ListEnvelope[ConversationDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('R/O'))
def list_conversations(q: str | None = Query(default=None, max_length=200),
                       starred: bool | None = None, limit: int = Query(default=30, ge=1, le=100),
                       cursor: str | None = None, _: Principal = Depends(current_principal),
                       conn: Connection = Depends(db)) -> dict:
    """Own conversations, newest first; ``q`` searches titles and message text."""
    items, next_cursor = chat.list_conversations(conn, q, starred, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.post('/conversations', status_code=201, response_model=Envelope[ConversationDTO],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R/O'))
def create_conversation(body: ConversationInput, response: Response,
                        principal: Principal = Depends(current_principal),
                        conn: Connection = Depends(db)) -> dict:
    created = chat.create_conversation(conn, principal, body.title,
                                       body.context.model_dump(mode='json'))
    response.headers['ETag'] = etag(created['revision'])
    return envelope(created)


@router.get('/conversations/{conversation_id}', response_model=Envelope[ConversationDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def get_conversation(conversation_id: uuid.UUID, response: Response,
                     _: Principal = Depends(current_principal),
                     conn: Connection = Depends(db)) -> dict:
    found = chat.get_conversation(conn, conversation_id)
    response.headers['ETag'] = etag(found['revision'])
    return envelope(found)


@router.patch('/conversations/{conversation_id}', response_model=Envelope[ConversationDTO],
              responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(412, 428)},
              openapi_extra=permission('O'))
def update_conversation(conversation_id: uuid.UUID, body: ConversationPatch, request: Request,
                        response: Response, _: Principal = Depends(current_principal),
                        conn: Connection = Depends(db)) -> dict:
    """Rename, star or change context; a new chart or school set starts a new memory window."""
    updated = chat.update_conversation(
        conn, conversation_id, _revision(request), body.title, body.starred,
        body.context.model_dump(mode='json') if body.context else None)
    response.headers['ETag'] = etag(updated['revision'])
    return envelope(updated)


@router.delete('/conversations/{conversation_id}', response_model=Envelope[ConversationDeleted],
               responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def delete_conversation(conversation_id: uuid.UUID, _: Principal = Depends(current_principal),
                        conn: Connection = Depends(db)) -> dict:
    return envelope(chat.delete_conversation(conn, conversation_id))


@router.get('/conversations/{conversation_id}/messages', response_model=Envelope[list[MessageDTO]],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def list_messages(conversation_id: uuid.UUID, after_seq: int = Query(default=0, ge=0),
                  limit: int = Query(default=100, ge=1, le=500),
                  _: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    return envelope(chat.messages(conn, conversation_id, after_seq, limit))


@router.post('/conversations/{conversation_id}/messages', status_code=202,
             response_model=Envelope[PostedMessage],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('O'))
def post_message(conversation_id: uuid.UUID, body: MessageInput, request: Request,
                 response: Response, principal: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    """User message + pending assistant message + queued run, in one transaction."""
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /conversations/{id}/messages',
                             {'conversation_id': str(conversation_id), **body.model_dump()})
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    body_out = envelope(chat.post_message(conn, principal, conversation_id, body.content,
                                          body.mode))
    slot.complete(202, body_out)
    return body_out


@router.get('/runs/{run_id}', response_model=Envelope[RunDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def get_run(run_id: uuid.UUID, _: Principal = Depends(current_principal),
            conn: Connection = Depends(db)) -> dict:
    return envelope(chat.get_run(conn, run_id))


@router.post('/runs/{run_id}/cancel', response_model=Envelope[RunDTO],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def cancel_run(run_id: uuid.UUID, _: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    """Idempotent; a provider may still bill a call already sent (usage reconciles)."""
    return envelope(chat.cancel_run(conn, run_id))


def _after(request: Request, run_id: uuid.UUID, after_seq: int | None) -> int:
    header = request.headers.get('Last-Event-ID')
    if header and ':' in header:
        owner_run, _, seq = header.rpartition(':')
        if owner_run == str(run_id) and seq.isdigit():
            return int(seq)
    return after_seq or 0


@router.get('/runs/{run_id}/events', response_class=StreamingResponse,
            responses={200: {'content': {'text/event-stream': {}},
                             'description': 'SSE: id {run_id}:{seq}, event, data JSON'},
                       **AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(410)},
            openapi_extra=permission('O'))
async def run_events(run_id: uuid.UUID, request: Request, after_seq: int | None = Query(None, ge=0),
                     principal: Principal = Depends(current_principal),
                     db_engine: Engine = Depends(engine)) -> StreamingResponse:
    start = _after(request, run_id, after_seq)

    def fetch(after: int) -> tuple[dict, list[dict]]:
        with transaction(db_engine, principal.user_id) as conn:
            run = chat.get_run(conn, run_id)                     # 404 for another owner
            return run, chat.events(conn, run_id, after)

    run, first = await run_in_threadpool(fetch, start)
    if run['state'] in ('completed', 'failed', 'cancelled') and not first and start == 0:
        # Events past retention: the final run is still there to fetch.
        raise AppError(410, 'EVENTS_EXPIRED', f'events of this run expired; GET /api/v1/runs/{run_id}')

    async def stream():
        after, pending, began, beat = start, first, time.monotonic(), time.monotonic()
        while True:
            for event in pending:
                after = event['seq']
                yield (f"id: {run_id}:{event['seq']}\nevent: {event['type']}\n"
                       f"data: {json.dumps(event['payload'], ensure_ascii=False, default=str)}\n\n")
                if event['type'] in TERMINAL:
                    return
            if await request.is_disconnected() or time.monotonic() - began > STREAM_SECONDS:
                return
            if time.monotonic() - beat > HEARTBEAT_SECONDS:
                beat = time.monotonic()
                yield ': heartbeat\n\n'
            await asyncio.sleep(0.5)
            _, pending = await run_in_threadpool(fetch, after)

    return StreamingResponse(stream(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
