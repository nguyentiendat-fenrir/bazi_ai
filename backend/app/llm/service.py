"""One budgeted model call: hold the cost, call outside any transaction, settle (docs/09)."""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.engine import Engine

from ..auth.service import Principal
from ..core.db import transaction
from ..core.errors import AppError
from . import budget, providers


def generate(engine: Engine, principal: Principal, messages: list[dict], max_tokens: int = 512,
             schema: type[BaseModel] | None = None, app_env: str = 'dev', transport=None,
             profile_id=None, run_id=None) -> tuple[providers.LLMResult, providers.LLMProfile]:
    with transaction(engine, principal.user_id) as conn:
        profile = providers.load(conn, profile_id)
        if profile is None:
            raise AppError(503, 'PROVIDER_NOT_CONFIGURED', 'No language model is configured')
        adapter = providers.build(profile, app_env, transport)
        usage_id = budget.reserve(conn, principal.user_id, profile,
                                  providers.estimate_tokens(messages), max_tokens, run_id)
    try:
        result = adapter.generate(messages, max_tokens, schema=schema)
    except providers.LLMError as exc:
        with transaction(engine, principal.user_id) as conn:
            budget.fail(conn, usage_id)
        raise AppError(503 if exc.retryable else 502, exc.code, str(exc)[:300]) from None
    with transaction(engine, principal.user_id) as conn:
        budget.complete(conn, profile, usage_id, result.input_tokens, result.output_tokens,
                        result.request_id)
    return result, profile
