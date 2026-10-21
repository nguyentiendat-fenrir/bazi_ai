"""Soft source links of the glossary (docs/10 · Nguồn): book key + page + anchor → a page here.

``/sources/resolve`` answers in JSON; ``/sources/open`` redirects the browser to the page
viewer with the anchor highlighted, so a link stays valid on every machine whatever its
row ids are (see ``knowledge/sources.py``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db
from ..auth.service import Principal
from ..core.errors import AppError
from ..knowledge import sources
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, permission, problem_responses

router = APIRouter(tags=['sources'])


def _ref(book: str, q: str, page: int | None, para: int | None) -> dict:
    return {'book': book, 'anchor': q, 'page': page, 'para': para}


Book = Query(..., min_length=1, max_length=80, description='Book key from books.json')
Anchor = Query(..., min_length=1, max_length=400, description='Words printed on the page')
Page = Query(default=None, ge=1, le=100000, description='Hinted PDF page (1-based)')
Para = Query(default=None, ge=1, le=1000000, description='Hinted DOCX paragraph')


@router.get('/sources/resolve', response_model=Envelope[dict[str, Any]],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('R'))
def resolve(book: str = Book, q: str = Anchor, page: int | None = Page, para: int | None = Para,
            principal: Principal = Depends(current_principal), conn: Connection = Depends(db)):
    return envelope(sources.resolve(conn, principal, _ref(book, q, page, para)))


@router.get('/sources/open', status_code=302, response_class=RedirectResponse,
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('R'))
def open_source(request: Request, book: str = Book, q: str = Anchor, page: int | None = Page,
                para: int | None = Para, principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)):
    found = sources.resolve(conn, principal, _ref(book, q, page, para))
    if found['matched'] == 'not_found':
        raise AppError(404, 'SOURCE_NOT_FOUND', f"Source not found: {found.get('reason')}")
    base = request.app.state.settings.public_base_path.rstrip('/')
    return RedirectResponse(base + found['url'], status_code=302)
