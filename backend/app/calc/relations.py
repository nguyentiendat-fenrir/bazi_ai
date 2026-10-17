"""Relations among the pillars' stems and branches (docs/08 · ``relations``).

A relation says which members stand in a known configuration and how complete it is;
it never says the combination transformed or an event happened
(``conditions_evaluated`` stays false at this layer). Positions keep multiplicity: two
zi branches against one wu are two clashes.
"""
from __future__ import annotations

from itertools import combinations

from .tables import (CLASHES, DESTRUCTIONS, DIRECTIONAL, HARMS, PUNISHMENT_GROUPS,
                     PUNISHMENT_PAIRS, SELF_PUNISHMENT, SIX_COMBINATIONS, STEM_CLASHES,
                     STEM_COMBINATIONS, THREE_COMBINATIONS)

ORDER = ('year', 'month', 'day', 'hour')


def _entry(kind: str, positions, members, completeness: str, element: str | None = None) -> dict:
    entry = {'type': kind, 'positions': list(positions), 'members': list(members),
             'completeness': completeness, 'conditions_evaluated': False}
    if element:
        entry['element'] = element
    return entry


def _groups(present: list[tuple[str, str]], frames, kind: str, half: str | None) -> list[dict]:
    """Three-member frames: full when all three branches appear, else partial pairs."""
    out = []
    for members, element in frames:
        found = [(pos, branch) for pos, branch in present if branch in members]
        distinct = {branch for _, branch in found}
        if len(distinct) == 3:
            out.append(_entry(kind, [p for p, _ in found], [b for _, b in found], 'full', element))
        elif len(distinct) == 2:
            out.append(_entry(kind, [p for p, _ in found], [b for _, b in found], 'partial',
                              element))
            # Two members with the frame's cardinal branch form the half combination.
            if half and members[1] in distinct:
                out.append(_entry(half, [p for p, _ in found], [b for _, b in found], 'full',
                                  element))
    return out


def relations(pillars: dict[str, tuple[str, str] | None]) -> list[dict]:
    present = [(pos, pillars[pos]) for pos in ORDER if pillars.get(pos)]
    out: list[dict] = []
    for (pa, (sa, ba)), (pb, (sb, bb)) in combinations(present, 2):
        stems, branches = frozenset((sa, sb)), frozenset((ba, bb))
        if stems in STEM_COMBINATIONS:
            out.append(_entry('stem_combination', (pa, pb), (sa, sb), 'full',
                              STEM_COMBINATIONS[stems]))
        if stems in STEM_CLASHES:
            out.append(_entry('stem_clash', (pa, pb), (sa, sb), 'full'))
        if branches in SIX_COMBINATIONS:
            out.append(_entry('six_combination', (pa, pb), (ba, bb), 'full',
                              SIX_COMBINATIONS[branches]))
        for kind, table in (('clash', CLASHES), ('harm', HARMS), ('destruction', DESTRUCTIONS),
                            ('punishment', PUNISHMENT_PAIRS)):
            if branches in table:
                out.append(_entry(kind, (pa, pb), (ba, bb), 'full'))
        if ba == bb and ba in SELF_PUNISHMENT:
            out.append(_entry('self_punishment', (pa, pb), (ba, bb), 'full'))
    branches = [(pos, branch) for pos, (_, branch) in present]
    out += _groups(branches, THREE_COMBINATIONS, 'three_combination', 'half_combination')
    out += _groups(branches, DIRECTIONAL, 'directional_combination', None)
    out += _groups(branches, [(g, None) for g in PUNISHMENT_GROUPS], 'punishment', None)
    return out
