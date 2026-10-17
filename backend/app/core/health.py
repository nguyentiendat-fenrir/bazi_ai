"""Readiness checks: essential failures make the API unready, others degrade it.

Modules register checks when they exist (database at T004, storage at T007,
broker at T010). A check reports a stable code, never exception text, and is
bounded by a timeout so a hung dependency cannot hang the probe.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Awaitable, Callable, Literal

from .config import Settings

Status = Literal['ok', 'degraded', 'fail']
log = logging.getLogger('bazi.health')


@dataclass(frozen=True)
class CheckResult:
    status: Status
    code: str


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    essential: bool
    run: Callable[[], Awaitable[CheckResult]]
    timeout_s: float = 2.0


async def _evaluate(check: ReadinessCheck) -> dict:
    try:
        result = await asyncio.wait_for(check.run(), timeout=check.timeout_s)
    except TimeoutError:
        result = CheckResult('fail', 'TIMEOUT')
    except Exception as exc:  # noqa: BLE001 - report a code, log the cause
        log.warning('readiness check failed', exc_info=(type(exc), exc, exc.__traceback__),
                    extra={'event': 'readiness_check', 'error_code': 'CHECK_ERROR'})
        result = CheckResult('fail', 'CHECK_ERROR')
    return {'name': check.name, 'essential': check.essential,
            'status': result.status, 'code': result.code}


async def evaluate(checks: list[ReadinessCheck]) -> tuple[Status, list[dict]]:
    results = await asyncio.gather(*(_evaluate(c) for c in checks))
    if any(r['essential'] and r['status'] == 'fail' for r in results):
        overall: Status = 'fail'
    elif any(r['status'] != 'ok' for r in results):
        overall = 'degraded'
    else:
        overall = 'ok'
    return overall, list(results)


def llm_provider_check(settings: Settings) -> ReadinessCheck:
    """Missing model is degraded, not fatal: chart and library work without it."""
    async def run() -> CheckResult:
        if settings.llm_configured:
            return CheckResult('ok', 'CONFIGURED')
        return CheckResult('degraded', 'PROVIDER_NOT_CONFIGURED')
    return ReadinessCheck('llm_provider', essential=False, run=run)


def default_checks(settings: Settings) -> list[ReadinessCheck]:
    return [llm_provider_check(settings)]
