"""Named calculation policies (docs/08 · Chính sách thời gian; DB ``calculation_policies``).

A policy fixes every choice schools disagree on; the chart records the whole config and
its hash, so two charts are comparable only when their policy hashes match.
"""
from __future__ import annotations

import hashlib
import json

POLICIES: dict[str, dict] = {
    'standard-v1': {
        'clock_basis': 'civil',               # civil | apparent_solar (needs longitude)
        'day_rollover': 'midnight',           # midnight | zi_start_23
        'late_zi_hour_stem': 'next_day',      # 23:00-24:00 is the next day's Zi hour
        'year_boundary': 'li_chun',           # year changes at Lập Xuân, not lunar new year
        'month_boundary': 'jie',              # months change at the twelve jie terms
        'yun_method': 'traditional_units',    # 3 days = 1 year, 1 day = 4 months, 2 h = 10 days
        'void_basis': 'day',                  # không vong from the day pillar's decade
        'growth_basis': 'day_master',         # 12 stages of each branch for the day stem
        'hidden_stems': 'three_qi',           # main/middle/residual
        'eot_model': None,
    },
    'zi23-v1': {
        'clock_basis': 'civil', 'day_rollover': 'zi_start_23', 'late_zi_hour_stem': 'next_day',
        'year_boundary': 'li_chun', 'month_boundary': 'jie', 'yun_method': 'traditional_units',
        'void_basis': 'day', 'growth_basis': 'day_master', 'hidden_stems': 'three_qi',
        'eot_model': None,
    },
    'solar-time-v1': {
        'clock_basis': 'apparent_solar', 'day_rollover': 'midnight',
        'late_zi_hour_stem': 'next_day', 'year_boundary': 'li_chun', 'month_boundary': 'jie',
        'yun_method': 'traditional_units', 'void_basis': 'day', 'growth_basis': 'day_master',
        'hidden_stems': 'three_qi', 'eot_model': 'noaa-spencer-1971',
    },
}
DEFAULT_POLICY = 'standard-v1'


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def policy(policy_id: str) -> dict:
    """The snapshot stored in a chart: id, full config and its hash."""
    config = POLICIES[policy_id]
    return {'id': policy_id, **config,
            'policy_hash': hashlib.sha256(canonical(config).encode()).hexdigest()}
