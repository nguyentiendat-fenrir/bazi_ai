"""Run a ruleset on one chart's facts: order, dependencies, limits, trace, conflicts
(docs/08 · B: Evaluation semantics, Trace, Conflict).

* Rules run in topological order of ``requires`` (rule revision ids); ties break by
  member ordinal, then revision id, so a run is deterministic. A dependency that is
  pending makes the rule pending; one that did not fire makes it ``dependency_blocked``.
* Each run has a budget (rules, node evaluations, CPU time). When it runs out the run is
  ``resource_limit``: traces so far are kept, the rest are ``skipped``, and no full
  analysis is claimed.
* Claims of fired rules are grouped by claim key; different values for one key are a
  conflict carrying every source, never silently merged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import json
import time

from .dsl import ResourceLimit, evaluate

LIMITS = {'max_rules': 5000, 'max_node_evals': 100_000, 'cpu_seconds': 2.0}


class RuleGraphError(ValueError):
    def __init__(self, code: str, message: str, rules: list[str]):
        super().__init__(message)
        self.code = code
        self.rules = rules


@dataclass(frozen=True)
class Member:
    revision_id: str
    rule_key: str
    dsl: dict
    ordinal: int = 0
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def requires(self) -> list[str]:
        return [str(r) for r in self.dsl.get('requires') or []]


def order(members: list[Member]) -> list[Member]:
    """Dependencies first; refuses a missing dependency or a cycle."""
    by_id = {m.revision_id: m for m in members}
    missing = sorted({r for m in members for r in m.requires if r not in by_id})
    if missing:
        raise RuleGraphError('DEPENDENCY_MISSING', 'required rule revisions are not members',
                             missing)
    waiting = {m.revision_id: len(set(m.requires)) for m in members}
    dependents: dict[str, list[str]] = {}
    for m in members:
        for r in set(m.requires):
            dependents.setdefault(r, []).append(m.revision_id)
    ready = [(m.ordinal, m.revision_id) for m in members if waiting[m.revision_id] == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        _, revision = heapq.heappop(ready)
        result.append(by_id[revision])
        for dependent in dependents.get(revision, []):
            waiting[dependent] -= 1
            if waiting[dependent] == 0:
                heapq.heappush(ready, (by_id[dependent].ordinal, dependent))
    if len(result) != len(members):
        stuck = sorted(r for r, n in waiting.items() if n > 0)
        raise RuleGraphError('RULE_CYCLE', 'rules require each other in a cycle', stuck)
    return result


def _dependency_state(member: Member, statuses: dict[str, str]) -> str:
    states = [statuses[r] for r in member.requires]
    if any(s == 'pending' for s in states):
        return 'pending'
    if any(s != 'fired' for s in states):
        return 'blocked'
    return 'ok'


def run(members: list[Member], facts: dict, limits: dict | None = None) -> dict:
    """Trace of every member, the claims of fired rules and their conflicts."""
    limits = {**LIMITS, **(limits or {})}
    ordered = order(members)
    counter = {'evals': 0, 'limit': limits['max_node_evals']}
    deadline = time.process_time() + limits['cpu_seconds']
    statuses: dict[str, str] = {}
    traces: list[dict] = []
    outcome = 'complete'
    for index, member in enumerate(ordered):
        if index >= limits['max_rules'] or time.process_time() > deadline:
            outcome = 'resource_limit'
        if outcome == 'resource_limit':
            statuses[member.revision_id] = 'skipped'
            traces.append({'revision_id': member.revision_id, 'rule_key': member.rule_key,
                           'status': 'skipped', 'reason': 'resource_limit'})
            continue
        reads: dict = {}
        context = {'counter': counter, 'reads': reads,
                   'fired_rules': [r for r, s in statuses.items() if s == 'fired']}
        before = counter['evals']
        try:
            when = evaluate(member.dsl['when'], facts, context)
            unless = evaluate(member.dsl['unless'], facts, context) if 'unless' in member.dsl \
                else False
        except ResourceLimit:
            outcome = 'resource_limit'
            statuses[member.revision_id] = 'skipped'
            traces.append({'revision_id': member.revision_id, 'rule_key': member.rule_key,
                           'status': 'skipped', 'reason': 'resource_limit'})
            continue
        dependency = _dependency_state(member, statuses)
        if when is False:
            status = 'not_matched'
        elif when is None:
            status = 'pending'
        elif unless is True:
            status = 'blocked_exception'
        elif unless is None or dependency == 'pending':
            status = 'pending'
        elif dependency == 'blocked':
            status = 'dependency_blocked'
        else:
            status = 'fired'
        statuses[member.revision_id] = status
        traces.append({
            'revision_id': member.revision_id, 'rule_key': member.rule_key, 'status': status,
            'when': when, 'unless': unless if 'unless' in member.dsl else None,
            'requires': [{'revision_id': r, 'status': statuses[r]} for r in member.requires],
            'reads': reads, 'evidence_ids': list(member.evidence_ids),
            'emits': [e['claim_key'] for e in member.dsl['emits']] if status == 'fired' else [],
            'node_evals': counter['evals'] - before,
        })
    claims = [{'claim_key': e['claim_key'], 'value': e['value'], 'kind': e['kind'],
               'rule_revision_id': m.revision_id, 'rule_key': m.rule_key,
               'evidence_ids': list(m.evidence_ids),
               'explanation': m.dsl['explanation_template']}
              for m in ordered if statuses.get(m.revision_id) == 'fired' for e in m.dsl['emits']]
    return {'status': outcome, 'traces': traces, 'claims': claims,
            'conflicts': conflicts(claims),
            'counters': {'rules': len(ordered), 'node_evals': counter['evals'],
                         'fired': sum(1 for s in statuses.values() if s == 'fired')}}


def conflicts(claims: list[dict]) -> list[dict]:
    """Claim keys emitted with more than one value, with every source of each value."""
    grouped: dict[str, dict[str, dict]] = {}
    for claim in claims:
        value_key = json.dumps(claim['value'], sort_keys=True)
        entry = grouped.setdefault(claim['claim_key'], {}).setdefault(
            value_key, {'value': claim['value'], 'rule_revision_ids': [], 'evidence_ids': []})
        entry['rule_revision_ids'].append(claim['rule_revision_id'])
        entry['evidence_ids'] += [e for e in claim['evidence_ids'] if e not in entry['evidence_ids']]
    return [{'claim_key': key, 'values': list(values.values())}
            for key, values in sorted(grouped.items()) if len(values) > 1]
