"""Rule DSL ``bazi-rule/1``: schema, AST and type checks, tri-valued evaluation (docs/08 · B).

An expression is ``{literal}``, ``{fact}``, ``{op, ...}`` or ``{call, args}`` — no
JSONPath, code, regex, IO or loops. Types are checked before anything runs: a
stem is never compared with a branch, a string never with a number; a literal
takes the type of the other side and must be a member of it (``wu`` is a valid
stem and a valid branch, but they are not the same value).

Evaluation is three-valued: T, F and U (unknown). An unknown fact (no hour) makes
a comparison U; ``not U = U``; ``all`` is F if any F, else U if any U; ``any`` is T
if any T, else U if any U. ``exists`` is F for an absent path and U for a known
path whose value is unknown. A rule fires only when ``when`` is T and ``unless``
is absent or F; ``unless`` T blocks it, U leaves it pending; a dependency that
is not known to have fired keeps it pending — unknown never becomes "false" that
triggers a negative conclusion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import uuid

from .facts import ENUMS, FACT_SCHEMA_VERSION, FACTS, FUNCTIONS, ten_god

SCHEMA_VERSION = 'bazi-rule/1'
MAX_NODES = 256
MAX_DEPTH = 16
COMPARE = ('eq', 'ne', 'gt', 'gte', 'lt', 'lte')
ORDERED = ('number',)
RULE_KEY = re.compile(r'^[a-z][a-z0-9_]{0,59}(\.[a-z0-9_]{1,60}){0,5}$')
CLAIM_KEY = re.compile(r'^[a-z][a-z0-9_]{0,59}(\.[a-z0-9_]{1,60}){0,5}$')
EMIT_KINDS = ('structural', 'interpretation_candidate', 'source_statement')
STATUSES = ('fired', 'not_matched', 'pending', 'blocked_exception', 'dependency_blocked')
MISSING = object()          # path absent from the facts snapshot


class DslError(ValueError):
    def __init__(self, errors: list[dict]):
        super().__init__('; '.join(f"{e['path']}: {e['message']}" for e in errors))
        self.errors = errors


@dataclass
class _Check:
    errors: list
    nodes: int = 0

    def fail(self, path: str, message: str) -> None:
        self.errors.append({'path': path, 'message': message})


INSTANT = re.compile(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$')


class ResourceLimit(Exception):
    """A run evaluated more nodes than its budget allows."""


def parse_instant(value: str) -> datetime | None:
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None


def _literal_type(value, expected: str | None) -> str | None:
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, (int, float)):
        return 'number'
    if isinstance(value, str):
        if expected in ENUMS:
            return expected if value in ENUMS[expected] else None
        if expected == 'instant':
            return 'instant' if INSTANT.match(value) and parse_instant(value) else None
        return 'string'
    return None


def _type(expr, path: str, check: _Check, depth: int, expected: str | None = None) -> str | None:
    """Static type of ``expr`` (``None`` when it is invalid; errors are recorded)."""
    check.nodes += 1
    if depth > MAX_DEPTH:
        check.fail(path, f'deeper than {MAX_DEPTH}')
        return None
    if not isinstance(expr, dict) or len(expr) == 0:
        check.fail(path, 'an expression is an object with literal, fact, op or call')
        return None
    if 'literal' in expr:
        value = expr['literal']
        if set(expr) != {'literal'}:
            check.fail(path, 'literal takes no other keys')
        if isinstance(value, list):
            inner = expected[5:] if expected and expected.startswith('list:') else expected
            types = {_literal_type(v, inner) for v in value}
            if not value or None in types or len(types) != 1:
                check.fail(path, f'list literal must be non-empty and all {inner or "one type"}')
                return None
            return f'list:{types.pop()}'
        found = _literal_type(value, expected)
        if found is None:
            check.fail(path, f'{value!r} is not a valid {expected or "scalar"}')
        return found
    if 'fact' in expr:
        if set(expr) != {'fact'} or expr['fact'] not in FACTS:
            check.fail(path, f"unknown fact {expr.get('fact')!r} in {FACT_SCHEMA_VERSION}")
            return None
        return FACTS[expr['fact']]
    if 'call' in expr:
        name = expr['call']
        if name not in FUNCTIONS or set(expr) - {'call', 'args'}:
            check.fail(path, f'function {name!r} is not allowed')
            return None
        params, result = FUNCTIONS[name]
        args = expr.get('args', [])
        if not isinstance(args, list) or len(args) != len(params):
            check.fail(path, f'{name} takes {len(params)} arguments')
            return None
        for i, (arg, param) in enumerate(zip(args, params)):
            got = _type(arg, f'{path}.args[{i}]', check, depth + 1, param)
            if got is not None and got != param:
                check.fail(f'{path}.args[{i}]', f'{name} expects {param}, got {got}')
        return result
    op = expr.get('op')
    if op in ('all', 'any'):
        args = expr.get('args')
        if set(expr) != {'op', 'args'} or not isinstance(args, list) or not args:
            check.fail(path, f'{op} takes a non-empty args list')
            return None
        for i, arg in enumerate(args):
            if _type(arg, f'{path}.args[{i}]', check, depth + 1, 'bool') not in ('bool', None):
                check.fail(f'{path}.args[{i}]', f'{op} needs boolean arguments')
        return 'bool'
    if op in ('not', 'exists'):
        if set(expr) != {'op', 'arg'}:
            check.fail(path, f'{op} takes one arg')
            return None
        got = _type(expr['arg'], f'{path}.arg', check, depth + 1, 'bool' if op == 'not' else None)
        if op == 'not' and got not in ('bool', None):
            check.fail(f'{path}.arg', 'not needs a boolean')
        if op == 'exists' and 'fact' not in expr['arg']:
            check.fail(f'{path}.arg', 'exists applies to a fact')
        return 'bool'
    if op in COMPARE + ('in', 'contains'):
        if set(expr) != {'op', 'left', 'right'}:
            check.fail(path, f'{op} takes left and right')
            return None
        left_expr, right_expr = expr['left'], expr['right']
        # Type the non-literal side first so a literal can take its namespace.
        left_first = 'literal' not in left_expr
        first, second = (left_expr, right_expr) if left_first else (right_expr, left_expr)
        names = ('left', 'right') if left_first else ('right', 'left')
        first_type = _type(first, f'{path}.{names[0]}', check, depth + 1)
        hint = first_type
        if op == 'in':
            hint = f'list:{first_type}' if left_first else (first_type or '')[5:] or None
        elif op == 'contains':
            hint = (first_type or '')[5:] or None if left_first else f'list:{first_type}'
        second_type = _type(second, f'{path}.{names[1]}', check, depth + 1, hint)
        if first_type is None or second_type is None:
            return 'bool'
        left_type, right_type = ((first_type, second_type) if left_first
                                 else (second_type, first_type))
        if op == 'in' and right_type != f'list:{left_type}':
            check.fail(path, f'in needs a list of {left_type}, got {right_type}')
        elif op == 'contains' and left_type != f'list:{right_type}':
            check.fail(path, f'contains needs a list of {right_type}, got {left_type}')
        elif op in COMPARE and left_type != right_type:
            check.fail(path, f'cannot compare {left_type} with {right_type}')
        elif op in ('gt', 'gte', 'lt', 'lte') and left_type not in ORDERED:
            check.fail(path, f'{op} needs numbers, got {left_type}')
        return 'bool'
    check.fail(path, f'unknown operator {op!r}')
    return None


def validate(dsl: dict) -> list[dict]:
    """All problems of a rule document; empty when it is valid ``bazi-rule/1``."""
    check = _Check([])
    if not isinstance(dsl, dict):
        return [{'path': '$', 'message': 'a rule is a JSON object'}]
    required = ('$schema_version', 'rule_key', 'school_id', 'method_id', 'fact_schema_version',
                'when', 'emits', 'evidence_ids', 'explanation_template')
    allowed = set(required) | {'unless', 'requires', 'limits'}
    for key in required:
        if key not in dsl:
            check.fail(key, 'required')
    for key in set(dsl) - allowed:
        check.fail(key, 'not part of bazi-rule/1')
    if dsl.get('$schema_version') != SCHEMA_VERSION:
        check.fail('$schema_version', f'must be {SCHEMA_VERSION}')
    if dsl.get('fact_schema_version') != FACT_SCHEMA_VERSION:
        check.fail('fact_schema_version', f'must be {FACT_SCHEMA_VERSION}')
    if not isinstance(dsl.get('rule_key'), str) or not RULE_KEY.fullmatch(dsl['rule_key']):
        check.fail('rule_key', 'lower-case dotted key')
    for key in ('school_id', 'method_id'):
        if not isinstance(dsl.get(key), str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,39}', dsl[key]):
            check.fail(key, 'a registry key such as manh_phai, not a UUID')
    for key in ('when', 'unless'):
        if key in dsl and _type(dsl[key], key, check, 1, 'bool') not in ('bool', None):
            check.fail(key, 'must be a boolean expression')
    for key in ('requires', 'evidence_ids'):
        value = dsl.get(key, [])
        if not isinstance(value, list):
            check.fail(key, 'a list of UUIDs')
            continue
        for i, item in enumerate(value):
            try:
                uuid.UUID(str(item))
            except ValueError:
                check.fail(f'{key}[{i}]', 'not a UUID')
    emits = dsl.get('emits')
    if not isinstance(emits, list) or not emits:
        check.fail('emits', 'at least one claim')
    else:
        for i, emit in enumerate(emits):
            if (not isinstance(emit, dict) or set(emit) != {'claim_key', 'value', 'kind'}
                    or not isinstance(emit.get('claim_key'), str)
                    or not CLAIM_KEY.fullmatch(emit['claim_key'])
                    or emit.get('kind') not in EMIT_KINDS
                    or not isinstance(emit.get('value'), (str, int, float, bool))):
                check.fail(f'emits[{i}]', 'claim_key, scalar value and kind '
                           f'({", ".join(EMIT_KINDS)})')
    template = dsl.get('explanation_template')
    if not isinstance(template, str) or not 1 <= len(template) <= 500:
        check.fail('explanation_template', '1-500 characters')
    limits = dsl.get('limits', {})
    if not isinstance(limits, dict) or set(limits) - {'max_nodes'} or not (
            1 <= limits.get('max_nodes', MAX_NODES) <= MAX_NODES):
        check.fail('limits', f'only max_nodes, at most {MAX_NODES}')
    elif check.nodes > limits.get('max_nodes', MAX_NODES):
        check.fail('when', f'{check.nodes} nodes exceed max_nodes')
    return check.errors


# ---- evaluation -------------------------------------------------------------------

def _lookup(facts: dict, path: str):
    node = facts
    for part in path.split('.'):
        if node is None:
            return None                     # a known-unknown parent (hour not given)
        if not isinstance(node, dict) or part not in node:
            return MISSING
        node = node[part]
    return node


def _unknown(value) -> bool:
    return value is None or value is MISSING


def _call(name: str, args: list, facts: dict, context: dict):
    if any(_unknown(a) for a in args):
        return None
    if name == 'ten_god_of':
        return ten_god(args[0], args[1])
    if name == 'count_branch':
        pillars = facts.get('pillars') or {}
        if any(pillars.get(p) is None for p in ('year', 'month', 'day', 'hour')):
            return None                     # an unknown pillar could change the count
        return sum(1 for p in pillars.values() if p.get('branch') == args[0])
    if name == 'hidden_stem_contains':
        pillar = (facts.get('pillars') or {}).get(args[0])
        if pillar is None:
            return None
        return any(h.get('stem') == args[1] for h in pillar.get('hidden_stems') or [])
    if name == 'has_relation':
        relations = facts.get('relations')
        if relations is None:
            return None
        kind, positions, completeness = args
        for relation in relations:
            if relation.get('type') != kind or not set(positions) <= set(relation.get('positions', [])):
                continue
            if completeness in ('any', relation.get('completeness')):
                return True
        return False
    if name == 'rule_fired':
        fired = context.get('fired_rules')
        return None if fired is None else args[0] in fired
    if name == 'cycle_at':
        return _cycle_at(facts, args[0], args[1])
    return None


def _cycle_at(facts: dict, instant: str, kind: str) -> str | None:
    at = parse_instant(instant)
    entries = ((facts.get('cycles') or {}).get(kind)) if at else None
    if not entries:
        return None
    start, end = ('start', 'end') if kind == 'da_yun' else ('start_instant', 'end_instant')
    for entry in entries:
        if entry.get(start) is None or entry.get(end) is None:
            return None                     # start of the luck cycle is uncertain
        if parse_instant(entry[start]) <= at < parse_instant(entry[end]):
            return f"{entry['stem']}-{entry['branch']}"
    return None                             # before the first or after the last cycle


def evaluate(expr, facts: dict, context: dict | None = None):
    """True, False or None (unknown) for a validated expression."""
    context = context or {}
    counter = context.get('counter')
    if counter is not None:
        counter['evals'] += 1
        if counter['evals'] > counter['limit']:
            raise ResourceLimit(f"more than {counter['limit']} node evaluations")
    if 'literal' in expr:
        return expr['literal']
    if 'fact' in expr:
        value = _lookup(facts, expr['fact'])
        value = None if value is MISSING else value
        if 'reads' in context:
            context['reads'][expr['fact']] = value
        return value
    if 'call' in expr:
        return _call(expr['call'], [evaluate(a, facts, context) for a in expr.get('args', [])],
                     facts, context)
    op = expr['op']
    if op == 'exists':
        value = _lookup(facts, expr['arg']['fact'])
        return False if value is MISSING else (None if value is None else True)
    if op == 'not':
        value = evaluate(expr['arg'], facts, context)
        return None if value is None else not value
    if op in ('all', 'any'):
        values = [evaluate(a, facts, context) for a in expr['args']]
        if op == 'all':
            return False if False in values else (None if None in values else True)
        return True if True in values else (None if None in values else False)
    left, right = evaluate(expr['left'], facts, context), evaluate(expr['right'], facts, context)
    if _unknown(left) or _unknown(right):
        return None
    return {'eq': lambda: left == right, 'ne': lambda: left != right,
            'gt': lambda: left > right, 'gte': lambda: left >= right,
            'lt': lambda: left < right, 'lte': lambda: left <= right,
            'in': lambda: left in right, 'contains': lambda: right in left}[op]()


def run_rule(dsl: dict, facts: dict, context: dict | None = None) -> dict:
    """Status of one rule on one facts snapshot, with the values that decided it."""
    context = context or {}
    when = evaluate(dsl['when'], facts, context)
    unless = evaluate(dsl['unless'], facts, context) if 'unless' in dsl else False
    requires = dsl.get('requires') or []
    fired = context.get('fired_rules')
    if when is False:
        status = 'not_matched'
    elif when is None:
        status = 'pending'
    elif unless is True:
        status = 'blocked_exception'
    elif unless is None:
        status = 'pending'
    elif requires and fired is None:
        status = 'pending'
    elif requires and not set(requires) <= set(fired):
        status = 'dependency_blocked'
    else:
        status = 'fired'
    return {'status': status, 'when': when, 'unless': unless,
            'emits': dsl['emits'] if status == 'fired' else []}
