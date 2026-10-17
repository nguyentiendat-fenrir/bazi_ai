"""Cost reservations and usage (docs/09 · budget): reserve before the call, settle after.

A call first holds its worst-case cost — estimated input plus the full output
allowance at the profile's prices — in its own committed transaction, under a
per-profile lock, after checking the profile's shared ``daily_budget``: two
callers can never both pass the ceiling. The hold expires on its own if the
worker dies; settling records the provider's token counts (actual cost from
the profile's prices) or the failure. Local models usually price at zero and
still record tokens. Usage rows are owner-private; the daily total across owners
comes from a definer function that returns sums only.
"""
from __future__ import annotations

from datetime import datetime, time as day_start, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from .providers import LLMProfile

HOLD_MINUTES = 10


def _price(profile: LLMProfile, input_tokens: int, output_tokens: int) -> Decimal:
    cfg = profile.config
    return (Decimal(str(cfg.get('price_input_per_1k', 0))) * input_tokens
            + Decimal(str(cfg.get('price_output_per_1k', 0))) * output_tokens) / 1000


def _today() -> tuple[datetime, datetime]:
    start = datetime.combine(datetime.now(timezone.utc).date(), day_start(), timezone.utc)
    return start, start + timedelta(days=1)


def spent_today(conn: Connection, profile_id) -> Decimal:
    since, until = _today()
    return conn.execute(text(
        'SELECT coalesce(sum(cost), 0) FROM bazi_usage_totals(:s, :u) WHERE profile_id = :p'),
        {'s': since, 'u': until, 'p': profile_id}).scalar_one()


def reserve(conn: Connection, owner_id, profile: LLMProfile, input_tokens: int,
            max_output_tokens: int, run_id=None) -> str:
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bazi.budget.' || :p))"),
                 {'p': profile.id})
    estimate = _price(profile, input_tokens, max_output_tokens)
    cap = profile.config.get('daily_budget')
    if cap is not None and spent_today(conn, profile.id) + estimate > Decimal(str(cap)):
        raise AppError(429, 'BUDGET_EXCEEDED', 'The daily budget of this model is spent',
                       headers={'Retry-After': '3600'})
    usage_id = conn.execute(text(
        'INSERT INTO usage_records (owner_id, run_id, profile_id, input_tokens, output_tokens,'
        " estimated_cost, currency, status) VALUES (:o, :r, :p, :i, :out, :c, :cur, 'reserved')"
        ' RETURNING id'),
        {'o': owner_id, 'r': run_id, 'p': profile.id, 'i': input_tokens, 'out': max_output_tokens,
         'c': estimate, 'cur': profile.config.get('currency', 'USD')}).scalar_one()
    conn.execute(text(
        'INSERT INTO budget_reservations (owner_id, usage_id, reserved_cost, expires_at)'
        ' VALUES (:o, :u, :c, now() + make_interval(mins => :m))'),
        {'o': owner_id, 'u': usage_id, 'c': estimate, 'm': HOLD_MINUTES})
    return str(usage_id)


def complete(conn: Connection, profile: LLMProfile, usage_id, input_tokens: int,
             output_tokens: int, request_id: str | None) -> None:
    conn.execute(text(
        "UPDATE usage_records SET status = 'completed', input_tokens = :i, output_tokens = :o,"
        ' actual_cost = :c, provider_request_id = :req WHERE id = :u'),
        {'u': usage_id, 'i': input_tokens, 'o': output_tokens,
         'c': _price(profile, input_tokens, output_tokens), 'req': request_id})
    conn.execute(text("UPDATE budget_reservations SET status = 'consumed' WHERE usage_id = :u"
                      " AND status = 'held'"), {'u': usage_id})


def fail(conn: Connection, usage_id) -> None:
    conn.execute(text("UPDATE usage_records SET status = 'failed', actual_cost = 0 WHERE id = :u"),
                 {'u': usage_id})
    conn.execute(text("UPDATE budget_reservations SET status = 'released' WHERE usage_id = :u"
                      " AND status = 'held'"), {'u': usage_id})


def summary(conn: Connection, owner_id, since: datetime, until: datetime, profile_id=None,
            aggregate: bool = False) -> dict:
    own = conn.execute(text(
        'SELECT profile_id, currency, count(*) AS requests, sum(input_tokens) AS input_tokens,'
        ' sum(output_tokens) AS output_tokens, sum(coalesce(actual_cost, estimated_cost))'
        " FILTER (WHERE status = 'completed') AS cost FROM usage_records WHERE owner_id = :o"
        ' AND created_at >= :s AND created_at < :u'
        ' AND (CAST(:p AS uuid) IS NULL OR profile_id = CAST(:p AS uuid))'
        ' GROUP BY profile_id, currency'),
        {'o': owner_id, 's': since, 'u': until,
         'p': str(profile_id) if profile_id else None}).mappings().all()
    rows = lambda items: [{'profile_id': str(r['profile_id']), 'currency': r['currency'].strip(),
                           'requests': r['requests'], 'input_tokens': int(r['input_tokens'] or 0),
                           'output_tokens': int(r['output_tokens'] or 0),
                           'cost': float(r['cost'] or 0)} for r in items]
    result = {'from': since, 'to': until, 'own': rows(own)}
    if aggregate:
        totals = conn.execute(text(
            'SELECT * FROM bazi_usage_totals(:s, :u)'
            ' WHERE (CAST(:p AS uuid) IS NULL OR profile_id = CAST(:p AS uuid))'),
            {'s': since, 'u': until, 'p': str(profile_id) if profile_id else None}).mappings().all()
        result['all'] = rows(totals)
    budgets = conn.execute(text(
        "SELECT id, config->>'daily_budget' AS cap, coalesce(config->>'currency', 'USD') AS cur"
        " FROM model_profiles WHERE kind = 'llm' AND config ? 'daily_budget'")).mappings().all()
    result['budgets'] = [{'profile_id': str(b['id']), 'daily_budget': float(b['cap']),
                          'currency': b['cur'], 'spent_today': float(spent_today(conn, b['id']))}
                         for b in budgets]
    return result
