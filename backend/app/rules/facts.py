"""Fact paths and value types a rule may read: ChartFacts ``chart-facts/1`` (docs/08 · A).

Only computed, verified fields are listed; presentation labels and heuristic
scores are not rule facts. Enum IDs are stable ASCII; the stem ``wu`` (戊) and the
branch ``wu`` (午) are different values because they live in different types.
"""
from __future__ import annotations

# The tables are the calculation engine's, so rules and charts never disagree on them.
from ..calc.tables import (BRANCHES, CONTROLS, ELEMENTS, GENERATES, GROWTH,  # noqa: F401
                           STEM_ELEMENT, STEMS, TEN_GODS, ten_god)

FACT_SCHEMA_VERSION = 'chart-facts/1'

POSITIONS = ('year', 'month', 'day', 'hour')
RELATIONS = ('stem_combination', 'stem_clash', 'six_combination', 'three_combination',
             'half_combination', 'directional_combination', 'clash', 'punishment',
             'self_punishment', 'harm', 'destruction')
COMPLETENESS = ('full', 'partial', 'any')
CYCLE_TYPES = ('da_yun', 'liu_nian')
GANZHI = tuple(f'{STEMS[i % 10]}-{BRANCHES[i % 12]}' for i in range(60))
ENUMS = {'stem': STEMS, 'branch': BRANCHES, 'element': ELEMENTS, 'ten_god': TEN_GODS,
         'growth_stage': GROWTH, 'position': POSITIONS, 'relation': RELATIONS,
         'completeness': COMPLETENESS, 'cycle_type': CYCLE_TYPES, 'ganzhi': GANZHI}

FACTS: dict[str, str] = {}
for _p in POSITIONS:
    FACTS.update({f'pillars.{_p}.stem': 'stem', f'pillars.{_p}.branch': 'branch',
                  f'pillars.{_p}.stem_element': 'element', f'pillars.{_p}.ten_god': 'ten_god',
                  f'pillars.{_p}.growth_stage': 'growth_stage', f'pillars.{_p}.na_yin': 'string',
                  f'pillars.{_p}.void': 'bool'})
FACTS['cycles.direction'] = 'string'
# The moment a question is about (analysis input, not chart data); absent → unknown.
FACTS['query.as_of'] = 'instant'

# name -> (argument types, result type); arguments are typed like facts.
FUNCTIONS: dict[str, tuple[tuple[str, ...], str]] = {
    'has_relation': (('relation', 'list:position', 'completeness'), 'bool'),
    'hidden_stem_contains': (('position', 'stem'), 'bool'),
    'ten_god_of': (('stem', 'stem'), 'ten_god'),
    'count_branch': (('branch',), 'number'),
    'rule_fired': (('string',), 'bool'),
    # The luck or annual pillar running at an instant, as "stem-branch".
    'cycle_at': (('instant', 'cycle_type'), 'ganzhi'),
}
