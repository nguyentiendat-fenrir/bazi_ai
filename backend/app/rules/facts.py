"""Fact paths and value types a rule may read: ChartFacts ``chart-facts/1`` (docs/08 · A).

Only computed, verified fields are listed; presentation labels and heuristic
scores are not rule facts. Enum IDs are stable ASCII; the stem ``wu`` (戊) and the
branch ``wu`` (午) are different values because they live in different types.
"""
from __future__ import annotations

FACT_SCHEMA_VERSION = 'chart-facts/1'
STEMS = ('jia', 'yi', 'bing', 'ding', 'wu', 'ji', 'geng', 'xin', 'ren', 'gui')
BRANCHES = ('zi', 'chou', 'yin', 'mao', 'chen', 'si', 'wu', 'wei', 'shen', 'you', 'xu', 'hai')
ELEMENTS = ('wood', 'fire', 'earth', 'metal', 'water')
TEN_GODS = ('peer', 'rob_wealth', 'eating_god', 'hurting_officer', 'indirect_wealth',
            'direct_wealth', 'seven_killings', 'direct_officer', 'indirect_resource',
            'direct_resource')
GROWTH = ('changsheng', 'muyu', 'guandai', 'linguan', 'diwang', 'shuai', 'bing', 'si', 'mu',
          'jue', 'tai', 'yang')
POSITIONS = ('year', 'month', 'day', 'hour')
RELATIONS = ('stem_combination', 'stem_clash', 'six_combination', 'three_combination',
             'half_combination', 'directional_combination', 'clash', 'punishment',
             'self_punishment', 'harm', 'destruction')
COMPLETENESS = ('full', 'partial', 'any')
ENUMS = {'stem': STEMS, 'branch': BRANCHES, 'element': ELEMENTS, 'ten_god': TEN_GODS,
         'growth_stage': GROWTH, 'position': POSITIONS, 'relation': RELATIONS,
         'completeness': COMPLETENESS}

FACTS: dict[str, str] = {}
for _p in POSITIONS:
    FACTS.update({f'pillars.{_p}.stem': 'stem', f'pillars.{_p}.branch': 'branch',
                  f'pillars.{_p}.stem_element': 'element', f'pillars.{_p}.ten_god': 'ten_god',
                  f'pillars.{_p}.growth_stage': 'growth_stage', f'pillars.{_p}.na_yin': 'string',
                  f'pillars.{_p}.void': 'bool'})
FACTS['cycles.direction'] = 'string'

# name -> (argument types, result type); arguments are typed like facts.
FUNCTIONS: dict[str, tuple[tuple[str, ...], str]] = {
    'has_relation': (('relation', 'list:position', 'completeness'), 'bool'),
    'hidden_stem_contains': (('position', 'stem'), 'bool'),
    'ten_god_of': (('stem', 'stem'), 'ten_god'),
    'count_branch': (('branch',), 'number'),
    'rule_fired': (('string',), 'bool'),
}

STEM_ELEMENT = dict(zip(STEMS, ('wood', 'wood', 'fire', 'fire', 'earth', 'earth', 'metal',
                                'metal', 'water', 'water')))
GENERATES = {'wood': 'fire', 'fire': 'earth', 'earth': 'metal', 'metal': 'water', 'water': 'wood'}
CONTROLS = {'wood': 'earth', 'earth': 'water', 'water': 'fire', 'fire': 'metal', 'metal': 'wood'}


def ten_god(stem: str, day_stem: str) -> str:
    """Ten god of ``stem`` seen from the day stem (standard Tử Bình relation)."""
    me, other = STEM_ELEMENT[day_stem], STEM_ELEMENT[stem]
    same = STEMS.index(stem) % 2 == STEMS.index(day_stem) % 2
    if other == me:
        return 'peer' if same else 'rob_wealth'
    if GENERATES[me] == other:
        return 'eating_god' if same else 'hurting_officer'
    if CONTROLS[me] == other:
        return 'indirect_wealth' if same else 'direct_wealth'
    if CONTROLS[other] == me:
        return 'seven_killings' if same else 'direct_officer'
    return 'indirect_resource' if same else 'direct_resource'
