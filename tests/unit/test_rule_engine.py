"""Ruleset runs (T031/T032): order, dependencies, limits, trace, conflicts, cycle_at."""
import unittest
import uuid

from backend.app.calc.chart import compute
from backend.app.calc.timebase import BirthInput
from backend.app.rules import dsl
from backend.app.rules.engine import Member, RuleGraphError, conflicts, order, run


def rule(key: str, when: dict, emits=('test.claim', 'x'), requires=(), unless=None) -> dict:
    document = {'$schema_version': 'bazi-rule/1', 'rule_key': key, 'school_id': 'test_only',
                'method_id': 'fixture', 'fact_schema_version': 'chart-facts/1', 'when': when,
                'requires': list(requires), 'evidence_ids': [],
                'emits': [{'claim_key': emits[0], 'value': emits[1], 'kind': 'structural'}],
                'explanation_template': 'fixture'}
    if unless:
        document['unless'] = unless
    assert dsl.validate(document) == [], dsl.validate(document)
    return document


def eq(path: str, value) -> dict:
    return {'op': 'eq', 'left': {'fact': path}, 'right': {'literal': value}}


def member(document: dict, ordinal: int = 0, revision: str | None = None) -> Member:
    return Member(revision or str(uuid.uuid4()), document['rule_key'], document, ordinal)


FACTS = {'pillars': {'day': {'stem': 'jia', 'stem_element': 'wood'}, 'hour': None},
         'cycles': {'direction': 'forward'}}


class OrderTests(unittest.TestCase):
    def test_dependencies_first_then_ordinal(self):
        base = member(rule('t.base', eq('pillars.day.stem', 'jia')), ordinal=5)
        child = member(rule('t.child', eq('pillars.day.stem', 'jia'),
                            requires=[base.revision_id]), ordinal=0)
        lone = member(rule('t.lone', eq('pillars.day.stem', 'yi')), ordinal=1)
        self.assertEqual([m.rule_key for m in order([child, lone, base])],
                         ['t.lone', 't.base', 't.child'])

    def test_missing_dependency_and_cycle_are_refused(self):
        ghost = str(uuid.uuid4())
        with self.assertRaises(RuleGraphError) as caught:
            order([member(rule('t.a', eq('pillars.day.stem', 'jia'), requires=[ghost]))])
        self.assertEqual((caught.exception.code, caught.exception.rules),
                         ('DEPENDENCY_MISSING', [ghost]))
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        with self.assertRaises(RuleGraphError) as caught:
            order([member(rule('t.a', eq('pillars.day.stem', 'jia'), requires=[b]), revision=a),
                   member(rule('t.b', eq('pillars.day.stem', 'jia'), requires=[a]), revision=b)])
        self.assertEqual(caught.exception.code, 'RULE_CYCLE')


class RunTests(unittest.TestCase):
    def test_statuses_follow_tri_valued_semantics_and_dependencies(self):
        fired = member(rule('t.fired', eq('pillars.day.stem', 'jia'), ('t.a', 1)))
        missed = member(rule('t.missed', eq('pillars.day.stem', 'yi'), ('t.b', 2)))
        pending = member(rule('t.pending', eq('pillars.hour.stem', 'jia'), ('t.c', 3)))
        blocked = member(rule('t.blocked', eq('pillars.day.stem', 'jia'), ('t.d', 4),
                              unless=eq('cycles.direction', 'forward')))
        needs_missed = member(rule('t.needs_missed', eq('pillars.day.stem', 'jia'), ('t.e', 5),
                                   requires=[missed.revision_id]))
        needs_pending = member(rule('t.needs_pending', eq('pillars.day.stem', 'jia'), ('t.f', 6),
                                    requires=[pending.revision_id]))
        needs_fired = member(rule('t.needs_fired', eq('pillars.day.stem', 'jia'), ('t.g', 7),
                                  requires=[fired.revision_id]))
        result = run([fired, missed, pending, blocked, needs_missed, needs_pending, needs_fired],
                     FACTS)
        status = {t['rule_key']: t['status'] for t in result['traces']}
        self.assertEqual(status, {'t.fired': 'fired', 't.missed': 'not_matched',
                                  't.pending': 'pending', 't.blocked': 'blocked_exception',
                                  't.needs_missed': 'dependency_blocked',
                                  't.needs_pending': 'pending', 't.needs_fired': 'fired'})
        self.assertEqual(sorted(c['claim_key'] for c in result['claims']), ['t.a', 't.g'])
        trace = next(t for t in result['traces'] if t['rule_key'] == 't.pending')
        self.assertEqual(trace['reads'], {'pillars.hour.stem': None})   # unknown, not false
        self.assertEqual(result['status'], 'complete')

    def test_conflicting_values_keep_every_source(self):
        a = member(rule('t.a', eq('pillars.day.stem', 'jia'), ('t.strength', 'strong')))
        b = member(rule('t.b', eq('pillars.day.stem_element', 'wood'), ('t.strength', 'weak')))
        c = member(rule('t.c', eq('pillars.day.stem', 'jia'), ('t.strength', 'strong')))
        found = run([a, b, c], FACTS)['conflicts']
        self.assertEqual(len(found), 1)
        values = {v['value']: sorted(v['rule_revision_ids']) for v in found[0]['values']}
        self.assertEqual(values, {'strong': sorted([a.revision_id, c.revision_id]),
                                  'weak': [b.revision_id]})
        self.assertEqual(conflicts([]), [])

    def test_budget_exhaustion_is_partial_never_complete(self):
        members = [member(rule(f't.r{i}', eq('pillars.day.stem', 'jia'), (f't.k{i}', i)),
                          ordinal=i) for i in range(10)]
        result = run(members, FACTS, {'max_node_evals': 9})
        self.assertEqual(result['status'], 'resource_limit')
        statuses = [t['status'] for t in result['traces']]
        self.assertEqual(statuses[:3], ['fired'] * 3)
        self.assertEqual(set(statuses[3:]), {'skipped'})
        self.assertEqual(run(members, FACTS, {'max_rules': 2})['traces'][2]['reason'],
                         'resource_limit')

    def test_cycle_at_reads_real_luck_and_annual_pillars(self):
        facts = compute(BirthInput(local_datetime='1990-08-17T06:45', timezone='Asia/Ho_Chi_Minh',
                                   sex_for_luck='male'))
        year_of = {'call': 'cycle_at', 'args': [{'fact': 'query.as_of'},
                                                {'literal': 'liu_nian'}]}
        document = rule('t.year', {'op': 'eq', 'left': year_of, 'right': {'literal': 'bing-wu'}},
                        ('t.year_is', 'bing-wu'))
        self.assertEqual(dsl.validate({**document, 'when': {
            'op': 'eq', 'left': year_of, 'right': {'literal': 'jia-chou'}}})[0]['path'],
            'when.right')                                         # not a sexagenary pair
        self.assertEqual(run([member(document)], {**facts, 'query': {'as_of': '2026-06-01'}})
                         ['traces'][0]['status'], 'fired')
        self.assertEqual(run([member(document)], {**facts, 'query': {'as_of': '2025-06-01'}})
                         ['traces'][0]['status'], 'not_matched')
        self.assertEqual(run([member(document)], facts)['traces'][0]['status'], 'pending')
        luck = dsl.evaluate({'call': 'cycle_at', 'args': [{'literal': '2010-01-01'},
                                                          {'literal': 'da_yun'}]}, facts)
        running = next(d for d in facts['cycles']['da_yun']
                       if d['start'] <= '2010-01-01T00:00:00Z' < d['end'])
        self.assertEqual(luck, f"{running['stem']}-{running['branch']}")
        before = dsl.evaluate({'call': 'cycle_at', 'args': [{'literal': '1991-01-01'},
                                                            {'literal': 'da_yun'}]}, facts)
        self.assertIsNone(before)                 # no luck pillar yet: unknown, not false


if __name__ == '__main__':
    unittest.main()
