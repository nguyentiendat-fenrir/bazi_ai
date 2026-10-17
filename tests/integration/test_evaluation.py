"""Retrieval evaluation: metric definitions, datasets, sign-off and runs (T036)."""
import contextlib
import io
import json
import math
import os
import unittest
from unittest.mock import patch
import uuid

from psycopg.conninfo import conninfo_to_dict

from backend.app import cli
from backend.app.core.config import load_settings
from backend.app.retrieval.evaluate import _leakage, _scores, compare, gates
from tests.integration.db import database_url
from tests.integration.env import PipelineTestCase
from tests.integration.test_search import MANH, TU_BINH


class MetricTests(unittest.TestCase):
    def test_graded_metrics(self):
        item = {'kind': 'retrieval', 'expected': {'relevant': [
            {'book_version_id': 'v', 'pages': [3], 'grade': 2},
            {'book_version_id': 'v', 'pages': [7], 'grade': 1}]}}
        result = {'status': 'ok', 'hits': [{'book_version_id': 'v', 'pages': [1]},
                                           {'book_version_id': 'v', 'pages': [3, 4]},
                                           {'book_version_id': 'v', 'pages': [3]}]}
        scores = _scores(item, result)
        self.assertEqual((scores['hit@5'], scores['recall@5'], scores['mrr@10']), (1.0, 0.5, 0.5))
        ideal = 2 + 1 / math.log2(3)
        self.assertAlmostEqual(scores['ndcg@10'], (2 / math.log2(3)) / ideal)   # page 3 counted once
        self.assertEqual(_scores({'kind': 'no_answer', 'expected': {'no_answer': True}},
                                 {'status': 'no_match', 'hits': []}), {'no_answer_correct': 1.0})
        self.assertEqual(scores['page@1'], 0.0)                 # page 1 is not relevant

    def test_school_leakage_counts_hits_outside_the_filter(self):
        item = {'input': {'query': 'x', 'school_ids': ['s1']}}
        hits = {'hits': [{'school_key': 'manh_phai'}, {'school_key': 'tu_binh'}]}
        self.assertEqual(_leakage(item, hits, {'s1': 'manh_phai'}), {'school_leakage': 0.5})
        self.assertEqual(_leakage({'input': {'query': 'x'}}, hits, {}), {})   # no filter, no metric

    def test_gates_and_regressions(self):
        checks = {g['metric']: g['passed'] for g in gates({'recall@20': 0.95, 'ndcg@10': 0.5})}
        self.assertEqual(checks, {'recall@20': True, 'ndcg@10': False, 'school_leakage': None})
        rows = {r['metric']: r for r in compare(
            {'recall@20': 0.85, 'ndcg@10': 0.79, 'school_leakage': 0.1},
            {'recall@20': 0.90, 'ndcg@10': 0.80, 'school_leakage': 0.0}, 0.02)}
        self.assertEqual((rows['recall@20']['regressed'], rows['ndcg@10']['regressed'],
                          rows['school_leakage']['regressed']), (True, False, True))
        self.assertEqual(rows['recall@20']['delta'], -0.05)


class EvaluationTests(PipelineTestCase):
    def test_dataset_run_and_sign_off(self):
        manh, tu_binh = self.publish_book(MANH, 'manh_phai'), self.publish_book(TU_BINH, 'tu_binh')
        items = [
            {'key': 'q1', 'kind': 'retrieval', 'input': {'query': 'thực thần sinh tài'},
             'expected': {'relevant': [{'book_version_id': manh, 'pages': [1], 'grade': 2},
                                       {'book_version_id': tu_binh, 'pages': [1]}]}},
            {'key': 'q2', 'kind': 'retrieval', 'input': {'query': 'cách cục thành thì quý'},
             'expected': {'relevant': [{'book_version_id': tu_binh, 'pages': [2], 'grade': 2}]},
             'split': 'test'},
            {'key': 'q3', 'kind': 'no_answer', 'input': {'query': 'xyzzy qwerty'},
             'expected': {'no_answer': True}}]
        created = self.c.post('/api/v1/evaluation-datasets', json={
            'name': 'seed', 'version': '1', 'items': items})
        self.assertEqual(created.status_code, 201, created.text)
        dataset = created.json()['data']
        self.assertEqual((dataset['state'], dataset['items'], dataset['split_manifest']),
                         ('draft', 3, {'dev': 2, 'test': 1, 'holdout': 0}))
        self.assertEqual(self.c.post('/api/v1/evaluation-datasets', json={
            'name': 'seed', 'version': '1', 'items': items}).status_code, 409)

        run = self.c.post('/api/v1/evaluation-runs', json={'dataset_id': dataset['id']})
        self.assertEqual(run.status_code, 201, run.text)
        data = run.json()['data']
        self.assertEqual((data['status'], data['metrics']['items']), ('completed', 3))
        self.assertEqual((data['metrics']['hit@5'], data['metrics']['recall@10'],
                          data['metrics']['no_answer_correct']), (1.0, 1.0, 1.0))
        self.assertEqual([r['status'] for r in data['results']], ['passed'] * 3)
        test_only = self.c.post('/api/v1/evaluation-runs', json={
            'dataset_id': dataset['id'], 'split': 'test'}).json()['data']
        self.assertEqual([r['key'] for r in test_only['results']], ['q2'])
        self.assertEqual(self.c.get(f"/api/v1/evaluation-runs/{data['id']}").json()['data']
                         ['metrics'], data['metrics'])

        approved = self.c.post(f"/api/v1/evaluation-datasets/{dataset['id']}/approve")
        self.assertEqual(approved.json()['data']['state'], 'approved')
        signed = self.c.get(f"/api/v1/evaluation-datasets/{dataset['id']}/items").json()['data']
        self.assertTrue(all(i['reviewer_id'] for i in signed))
        self.assertEqual(self.c.post(f"/api/v1/evaluation-datasets/{dataset['id']}/approve")
                         .status_code, 409)
        reader, _ = self.client('reader')
        self.assertEqual(reader.get('/api/v1/evaluation-datasets').status_code, 403)


class RegressionTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        test = cls('test_strategies_baselines_and_the_ci_exit_code')
        cls.manh = test.publish_book(MANH, 'manh_phai')
        cls.tu_binh = test.publish_book(TU_BINH, 'tu_binh')

    def run_cli(self, *args) -> tuple[int, dict]:
        url = conninfo_to_dict(database_url(self.db))
        env = {'POSTGRES_HOST': url['host'], 'POSTGRES_PORT': str(url['port']),
               'POSTGRES_DB': url['dbname'], 'POSTGRES_USER': url['user'],
               'POSTGRES_PASSWORD': url['password']}
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings(_env_file=None)
        out = io.StringIO()
        with patch.object(cli, 'load_settings', return_value=settings), \
                contextlib.redirect_stdout(out):
            code = cli.main(['evaluate', *args])
        return code, json.loads(out.getvalue())

    def test_strategies_baselines_and_the_ci_exit_code(self):
        manh_school = self.sql("SELECT id::text FROM schools WHERE key = 'manh_phai'")[0][0]
        items = [
            {'key': 'q1', 'kind': 'retrieval', 'input': {'query': 'thực thần sinh tài'},
             'expected': {'relevant': [{'book_version_id': self.manh, 'pages': [1], 'grade': 2},
                                       {'book_version_id': self.tu_binh, 'pages': [1]}]}},
            {'key': 'q2', 'kind': 'retrieval',
             'input': {'query': 'thực thần sinh tài', 'school_ids': [manh_school]},
             'expected': {'relevant': [{'book_version_id': self.manh, 'pages': [1]}]}},
            {'key': 'q3', 'kind': 'no_answer', 'input': {'query': 'xyzzy qwerty'},
             'expected': {'no_answer': True}}]
        name = f'reg-{uuid.uuid4().hex[:6]}'
        dataset = self.c.post('/api/v1/evaluation-datasets', json={
            'name': name, 'version': '1', 'items': items}).json()['data']

        runs = {}
        for strategy in ('lexical', 'hybrid'):
            made = self.c.post('/api/v1/evaluation-runs', json={
                'dataset_id': dataset['id'], 'strategy': strategy, 'rerank': False})
            self.assertEqual(made.status_code, 201, made.text)
            runs[strategy] = made.json()['data']
            self.assertEqual(runs[strategy]['config']['strategy'], strategy)
        metrics = runs['hybrid']['metrics']
        self.assertEqual((metrics['school_leakage'], metrics['no_answer_precision'],
                          metrics['no_answer_recall'], metrics['page@1']), (0.0, 1.0, 1.0, 1.0))
        leakage = next(g for g in runs['hybrid']['gates'] if g['metric'] == 'school_leakage')
        self.assertTrue(leakage['passed'])
        self.assertIsNone(runs['hybrid']['comparison'])

        listed = self.c.get('/api/v1/evaluation-runs', params={'dataset_id': dataset['id']})
        self.assertEqual([r['id'] for r in listed.json()['data']],
                         [runs['hybrid']['id'], runs['lexical']['id']])          # newest first
        self.assertNotIn('results', listed.json()['data'][0])

        same = self.c.post('/api/v1/evaluation-runs', json={
            'dataset_id': dataset['id'], 'strategy': 'hybrid',
            'baseline_run_id': runs['hybrid']['id']}).json()['data']
        self.assertFalse(same['regressed'])
        self.assertTrue(all(d['delta'] == 0 for d in same['comparison']))
        other = self.c.post('/api/v1/evaluation-datasets', json={
            'name': f'{name}-x', 'version': '1', 'items': items[:1]}).json()['data']
        wrong = self.c.post('/api/v1/evaluation-runs', json={
            'dataset_id': dataset['id'], 'baseline_run_id': self.c.post(
                '/api/v1/evaluation-runs', json={'dataset_id': other['id']}).json()['data']['id']})
        self.assertEqual(wrong.status_code, 422)

        reviewer = self.sql('SELECT email FROM users WHERE id = %s', self.user)[0][0]
        code, report = self.run_cli('--dataset', name, '--version', '1', '--as', reviewer,
                                    '--strategy', 'hybrid', '--baseline', 'latest')
        self.assertEqual((code, report['ok'], report['regressed']), (0, True, []))
        # A baseline better than anything reachable: the same run now regresses, exit 1.
        self.sql("UPDATE evaluation_runs SET metrics = metrics || '{\"mrr@10\": 2.0}'"
                 ' WHERE id = %s', report['run_id'])
        code, report = self.run_cli('--dataset', name, '--version', '1', '--as', reviewer,
                                    '--strategy', 'hybrid', '--baseline', 'latest')
        self.assertEqual((code, report['regressed']), (1, ['mrr@10']))
        code, report = self.run_cli('--dataset', name, '--version', '1', '--as', 'nobody@x.test')
        self.assertEqual((code, report['code']), (2, 'USER_NOT_FOUND'))


if __name__ == '__main__':
    unittest.main()
