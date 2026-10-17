"""Liveness and readiness probes (docs/10 · Routes xác thực và cấu hình)."""
from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..core.errors import AppError
from ..core.health import evaluate
from ..core.logging import request_id_var
from .schemas import Envelope, LiveStatus, ReadyStatus, permission, problem_responses

router = APIRouter(prefix='/health', tags=['health'])
# RFC 1918 and IPv6 ULA only: ipaddress.is_private also admits documentation and
# other reserved ranges, which must not count as the Compose network.
_INTERNAL_NETWORKS = tuple(ipaddress.ip_network(n) for n in
                           ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7'))


def envelope(data) -> dict:
    return {'data': data, 'meta': {'request_id': request_id_var.get()}}


def _is_internal(request: Request) -> bool:
    # Until admin sessions exist (T006) readiness is internal-only: loopback for
    # local probes, private ranges for the Compose network. The host publishes
    # only the gateway port, so outside callers never arrive with these addresses.
    host = request.client.host if request.client else ''
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host == 'testclient'
    return address.is_loopback or any(address in net for net in _INTERNAL_NETWORKS)


@router.get('/live', response_model=Envelope[LiveStatus], openapi_extra=permission('public'))
async def live() -> dict:
    """Process is up. No dependency calls, versions or configuration."""
    return envelope({'status': 'ok'})


@router.get('/ready', response_model=Envelope[ReadyStatus],
            responses={503: {'model': Envelope[ReadyStatus]}, **problem_responses(403)},
            openapi_extra=permission('A or internal'))
async def ready(request: Request) -> JSONResponse:
    if not _is_internal(request):
        raise AppError(403, 'FORBIDDEN', 'Readiness is available to internal callers only')
    overall, checks = await evaluate(request.app.state.readiness_checks)
    return JSONResponse(envelope({'status': overall, 'checks': checks}),
                        status_code=503 if overall == 'fail' else 200)
