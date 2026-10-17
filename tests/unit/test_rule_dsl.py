"""bazi-rule/1: schema and type checks, tri-valued evaluation, allowed functions (T022)."""
import copy
import unittest

from backend.app.rules.dsl import MAX_NODES, evaluate, run_rule, validate
from backend.app.rules.facts import STEMS, ten_god

RULE = {
    '$schema_version': 'bazi-rule/1', 'rule_key': 'synthetic.wood_day_master',
    'school_id': 'test_only', 'method_id': 'structural_fixture',
    'fact_schema_version': 'chart-facts/1',
    'when': {'op': 'eq', 'left': {'fact': 'pillars.day.stem_element'},
             'right': {'literal': 'wood'}},
    'requires': [], 'evidence_ids': [],
    'emits': [{'claim_key': 'fixture.day_element', 'value': 'wood', 'kind': 'structural'}],
    'explanation_template': 'Nhật can thuộc Mộc theo dữ kiện tính toán.',
    'limits': {'max_nodes': 256}}


def rule(**changes):
    document = copy.deepcopy(RULE)
    document.update(changes)
    return document


def fact(path):
    return {'fact': path}


def lit(value):
    return {'literal': value}


class ValidationTests(unittest.TestCase):
    def test_docs_example_is_valid(self):
        self.assertEqual(validate(RULE), [])

    def test_schema_errors(self):
        self.assertEqual(validate({**RULE, 'approved': True})[0]['path'], 'approved')
        broken = rule()
        del broken['when']
        self.assertIn('when', [e['path'] for e in validate(broken)])
        for key, value in (('$schema_version', 'bazi-rule/2'), ('school_id', 'Manh Phái'),
                           ('rule_key', 'Bad Key'), ('fact_schema_version', 'chart-facts/9'),
                           ('emits', []), ('limits', {'max_nodes': 10_000}),
                           ('requires', ['not-a-uuid'])):
            with self.subTest(key=key):
                self.assertTrue(validate(rule(**{key: value})))

    def test_types_never_mix(self):
        cases = {
            'stem vs branch': {'op': 'eq', 'left': fact('pillars.day.stem'),
                               'right': fact('pillars.day.branch')},
            'branch literal for a stem': {'op': 'eq', 'left': fact('pillars.day.stem'),
                                          'right': lit('zi')},
            'string vs number': {'op': 'eq', 'left': fact('pillars.day.na_yin'), 'right': lit(3)},
            'ordering strings': {'op': 'gt', 'left': fact('pillars.day.na_yin'),
                                 'right': lit('x')},
            'unknown fact': {'op': 'exists', 'arg': fact('pillars.day.secret')},
            'not a function': {'call': 'eval', 'args': []},
            'wrong arity': {'call': 'count_branch', 'args': []},
            'non-boolean all': {'op': 'all', 'args': [fact('pillars.day.stem')]},
            'jsonpath': {'fact': '$..stem'},
        }
        for name, expr in cases.items():
            with self.subTest(case=name):
                self.assertTrue(validate(rule(when=expr)), name)
        # "wu" is both a stem and a branch: valid against either type, never across.
        for path in ('pillars.day.stem', 'pillars.day.branch'):
            self.assertEqual(validate(rule(when={'op': 'eq', 'left': fact(path),
                                                 'right': lit('wu')})), [])
        self.assertEqual(validate(rule(when={'op': 'in', 'left': fact('pillars.day.branch'),
                                             'right': lit(['zi', 'wu'])})), [])

    def test_limits(self):
        wide = {'op': 'all', 'args': [{'op': 'exists', 'arg': fact('pillars.day.stem')}] * MAX_NODES}
        self.assertTrue(any('nodes' in e['message'] for e in validate(rule(when=wide))))
        deep = {'op': 'exists', 'arg': fact('pillars.day.stem')}
        for _ in range(20):
            deep = {'op': 'not', 'arg': deep}
        self.assertTrue(any('deeper' in e['message'] for e in validate(rule(when=deep))))


class EvaluationTests(unittest.TestCase):
    def test_statuses(self):
        self.assertEqual(run_rule(RULE, {'pillars': {'day': {'stem_element': 'wood'}}})['status'],
                         'fired')
        self.assertEqual(run_rule(RULE, {'pillars': {'day': {'stem_element': 'fire'}}})['status'],
                         'not_matched')
        self.assertEqual(run_rule(RULE, {'pillars': {'day': None}})['status'], 'pending')
        guarded = rule(unless={'op': 'eq', 'left': fact('pillars.hour.stem'), 'right': lit('jia')})
        wood = {'pillars': {'day': {'stem_element': 'wood'}, 'hour': {'stem': 'jia'}}}
        self.assertEqual(run_rule(guarded, wood)['status'], 'blocked_exception')
        no_hour = {'pillars': {'day': {'stem_element': 'wood'}, 'hour': None}}
        self.assertEqual(run_rule(guarded, no_hour)['status'], 'pending')
        dependent = rule(requires=['5c5bd9b4-0f5e-4c1b-9a2e-3f8a9b6f2a11'])
        facts = {'pillars': {'day': {'stem_element': 'wood'}}}
        self.assertEqual(run_rule(dependent, facts)['status'], 'pending')
        self.assertEqual(run_rule(dependent, facts, {'fired_rules': []})['status'],
                         'dependency_blocked')
        self.assertEqual(run_rule(dependent, facts, {'fired_rules': dependent['requires']})
                         ['status'], 'fired')

    def test_three_valued_logic(self):
        facts = {'pillars': {'day': {'stem': 'jia'}, 'hour': None}}
        true = {'op': 'eq', 'left': fact('pillars.day.stem'), 'right': lit('jia')}
        false = {'op': 'eq', 'left': fact('pillars.day.stem'), 'right': lit('yi')}
        unknown = {'op': 'eq', 'left': fact('pillars.hour.stem'), 'right': lit('jia')}
        self.assertIsNone(evaluate({'op': 'not', 'arg': unknown}, facts))
        self.assertIs(evaluate({'op': 'all', 'args': [false, unknown]}, facts), False)
        self.assertIsNone(evaluate({'op': 'all', 'args': [true, unknown]}, facts))
        self.assertIs(evaluate({'op': 'any', 'args': [true, unknown]}, facts), True)
        self.assertIsNone(evaluate({'op': 'any', 'args': [false, unknown]}, facts))
        self.assertIsNone(evaluate({'op': 'exists', 'arg': fact('pillars.hour.stem')}, facts))
        self.assertIs(evaluate({'op': 'exists', 'arg': fact('pillars.month.stem')}, facts), False)

    def test_functions(self):
        facts = {'pillars': {
            'year': {'branch': 'zi', 'hidden_stems': [{'stem': 'gui'}]},
            'month': {'branch': 'wu', 'hidden_stems': [{'stem': 'ding'}, {'stem': 'ji'}]},
            'day': {'stem': 'jia', 'branch': 'zi', 'hidden_stems': [{'stem': 'gui'}]},
            'hour': None},
            'relations': [{'type': 'clash', 'positions': ['year', 'month'],
                           'completeness': 'full'}]}
        call = lambda name, *args: evaluate({'call': name, 'args': [lit(a) for a in args]}, facts)
        self.assertIs(call('hidden_stem_contains', 'month', 'ji'), True)
        self.assertIs(call('has_relation', 'clash', ['year', 'month'], 'full'), True)
        self.assertIs(call('has_relation', 'clash', ['day', 'month'], 'any'), False)
        self.assertIsNone(call('count_branch', 'zi'))      # the hour could be another zi
        facts['pillars']['hour'] = {'branch': 'zi'}
        self.assertEqual(call('count_branch', 'zi'), 3)
        self.assertEqual(call('ten_god_of', 'geng', 'jia'), 'seven_killings')

    def test_ten_gods_from_jia(self):
        expected = ['peer', 'rob_wealth', 'eating_god', 'hurting_officer', 'indirect_wealth',
                    'direct_wealth', 'seven_killings', 'direct_officer', 'indirect_resource',
                    'direct_resource']
        self.assertEqual([ten_god(s, 'jia') for s in STEMS], expected)
        self.assertEqual(ten_god('jia', 'yi'), 'rob_wealth')
        self.assertEqual(ten_god('xin', 'yi'), 'seven_killings')


if __name__ == '__main__':
    unittest.main()
