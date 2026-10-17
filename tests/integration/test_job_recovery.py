"""Crash/recovery of the durable job runner on PostgreSQL as the runtime role (T010).

A fake three-unit stage publishes one ``review_items`` row per unit (a table
without a unique constraint, so duplicates would show) and writes a blob in
``compute``. Workers are "killed" by raising at the three write boundaries.
"""
import io
import json
import tempfile
import unittest
import uuid

import psycopg

from backend.app.ingestion import outbox, queue
from backend.app.ingestion.watchdog import QUEUED_TOPIC, sweep
from backend.app.ingestion.worker import RetryableError, Unit, UnitFailed, run_job
from backend.app.storage.local import LocalObjectStore
from tests.integration.db import (create_runtime_login, database_url, drop_database, drop_role,
                                  engine_for, migrated_database, sha)
from tests.integration.factories import Factory

DB_NAME = ROLE = RUNTIME = None


def setUpModule():
    global DB_NAME, ROLE, RUNTIME
    DB_NAME = migrated_database('head')
    try:
        ROLE, RUNTIME = create_runtime_login(DB_NAME)
    except BaseException:
        drop_database(DB_NAME)
        raise


def tearDownModule():
    if DB_NAME:
        drop_database(DB_NAME)
    if ROLE:
        drop_role(ROLE)


class Crash(BaseException):
    """Simulated kill: BaseException so nothing in the runner swallows it."""


class FakeStage:
    name = 'extract'

    def __init__(self, units=3, fail_once=None, fail_always=None):
        self.n = units
        self.fail_once = set(fail_once or ())
        self.fail_always = fail_always
        self.computed = []

    def units(self, ctx):
        return [Unit(f'page:{i}', sha(f'{ctx.source_sha256}:{i}')) for i in range(1, self.n + 1)]

    def compute(self, ctx, unit):
        self.computed.append(unit.key)
        if unit.key in self.fail_once:
            self.fail_once.discard(unit.key)
            raise RetryableError('OCR_TIMEOUT')
        if unit.key == self.fail_always:
            raise UnitFailed('PASSWORD_REQUIRED')
        blob = ctx.store.put_if_absent(io.BytesIO(f'text of {unit.key}'.encode()))
        return {'blob': blob.key}

    def persist(self, conn, ctx, unit, result):
        conn.exec_driver_sql(
            "INSERT INTO review_items (generation_id, reason_code, severity, resolution)"
            " VALUES (%(g)s, %(r)s, 'info', %(res)s::jsonb)",
            {'g': ctx.generation_id, 'r': unit.key, 'res': json.dumps(result)})
        return result


class MemoryBroker:
    def __init__(self):
        self.messages = []

    def send(self, topic, payload, event_id):
        self.messages.append((topic, payload['job_id'], event_id))


class RecoveryTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = engine_for(RUNTIME)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = LocalObjectStore(self.tmp.name)
        self.job, self.generation = self.make_job()

    def make_job(self):
        with psycopg.connect(database_url(DB_NAME), autocommit=True) as conn:
            f = Factory(conn)
            version = f.book_version()
            profile = f.one('INSERT INTO pipeline_profiles (name, parser_version, chunker_version,'
                            " normalizer_version, embedding_profile_id, config_hash)"
                            " VALUES ('p', '1', '1', '1', %s, %s) RETURNING id",
                            f.embedding_profile(), sha(uuid.uuid4().hex))
            generation = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                               ' VALUES (%s, %s) RETURNING id', version, profile)
            job = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                        ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                        version, generation, profile, f.user())
        return job, generation

    def sql(self, query, *params):
        with psycopg.connect(database_url(DB_NAME), autocommit=True) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else cursor.rowcount

    def run_worker(self, stage=None, worker='w1', crash_at=None, crash_on=None):
        stage = stage or FakeStage()
        seen = {'n': 0}

        def fault(point):
            if point == crash_at:
                seen['n'] += 1
                if crash_on is None or seen['n'] == crash_on:
                    raise Crash(point)
        return run_job(self.engine, self.store, self.job, [stage], worker, fault)

    def published(self):
        return dict(self.sql('SELECT reason_code, count(*) FROM review_items'
                             ' WHERE generation_id = %s GROUP BY reason_code', self.generation))

    def job_state(self):
        return self.sql('SELECT state FROM ingestion_jobs WHERE id = %s', self.job)[0][0]

    def expire_leases(self):
        self.sql("UPDATE job_stages SET lease_until = now() - interval '1 second'"
                 " WHERE job_id = %s AND state = 'running'", self.job)


class CrashBoundaryTests(RecoveryTestCase):
    def test_clean_run(self):
        self.assertEqual(self.run_worker(), 'succeeded')
        self.assertEqual(self.published(), {'page:1': 1, 'page:2': 1, 'page:3': 1})
        states = self.sql('SELECT state, count(*) FROM job_stages WHERE job_id = %s GROUP BY 1',
                          self.job)
        self.assertEqual(states, [('succeeded', 3)])

    def assert_recovers(self, boundary):
        with self.assertRaises(Crash):
            self.run_worker(crash_at=boundary, crash_on=2)
        before = self.published()
        # The dead worker's lease is still live: a second worker must not steal the unit.
        self.assertEqual(self.run_worker(worker='w2'), 'running')
        self.expire_leases()
        self.assertGreaterEqual(sweep(self.engine).expired_leases, 0)
        stage = FakeStage()
        self.assertEqual(self.run_worker(stage=stage, worker='w2'), 'succeeded')
        self.assertEqual(self.published(), {'page:1': 1, 'page:2': 1, 'page:3': 1})
        return before, stage

    def test_kill_after_compute_before_commit(self):
        before, stage = self.assert_recovers('after_compute_before_commit')
        self.assertEqual(before, {'page:1': 1})
        self.assertEqual(stage.computed, ['page:2', 'page:3'])  # page:1 reused

    def test_kill_inside_commit_rolls_back_unit(self):
        before, _ = self.assert_recovers('after_persist_before_complete')
        self.assertEqual(before, {'page:1': 1})  # page:2 rows rolled back with the crash

    def test_kill_after_commit_never_duplicates(self):
        with self.assertRaises(Crash):
            self.run_worker(crash_at='after_commit_before_next', crash_on=2)
        self.assertEqual(self.published(), {'page:1': 1, 'page:2': 1})
        stage = FakeStage()
        self.assertEqual(self.run_worker(stage=stage, worker='w2'), 'succeeded')
        self.assertEqual(stage.computed, ['page:3'])
        self.assertEqual(self.published(), {'page:1': 1, 'page:2': 1, 'page:3': 1})

    def test_stale_worker_cannot_publish(self):
        stage = FakeStage(units=1)
        ctx_unit = stage.units(type('C', (), {'source_sha256': self.source_sha()})())[0]
        key = self.unit_key(ctx_unit)
        with self.engine.begin() as conn:
            queue.start_job(conn, self.job)
            stale = queue.claim(conn, self.job, 'extract', ctx_unit.key, ctx_unit.input_hash, key,
                                'paused-worker').lease
        self.expire_leases()
        self.assertEqual(run_job(self.engine, self.store, self.job, [FakeStage(units=1)], 'w2'),
                         'succeeded')
        with self.assertRaises(queue.LeaseLost):
            with self.engine.begin() as conn:
                conn.exec_driver_sql("INSERT INTO review_items (generation_id, reason_code,"
                                     " severity) VALUES (%(g)s, 'page:1', 'info')",
                                     {'g': self.generation})
                queue.complete(conn, stale, {'stale': True})
        self.assertEqual(self.published(), {'page:1': 1})

    def source_sha(self):
        return self.sql('SELECT o.sha256 FROM ingestion_jobs j JOIN book_versions v'
                        ' ON v.id = j.book_version_id JOIN objects o ON o.id = v.object_id'
                        ' WHERE j.id = %s', self.job)[0][0].strip()

    def unit_key(self, unit):
        version, config = self.sql('SELECT j.book_version_id, p.config_hash FROM ingestion_jobs j'
                                   ' JOIN pipeline_profiles p ON p.id = j.pipeline_profile_id'
                                   ' WHERE j.id = %s', self.job)[0]
        return queue.idempotency_key(version, self.source_sha(), 'extract', unit.key,
                                     config.strip(), unit.input_hash)


class RetryCancelTests(RecoveryTestCase):
    def test_transient_failure_retries_when_due(self):
        stage = FakeStage(fail_once={'page:2'})
        self.assertEqual(self.run_worker(stage=stage), 'retry_wait')
        error = self.sql('SELECT error FROM ingestion_jobs WHERE id = %s', self.job)[0][0]
        self.assertEqual((error['code'], error['retryable']), ('OCR_TIMEOUT', True))
        self.assertEqual(sweep(self.engine).retries_due, 0)  # not due yet
        self.sql("UPDATE ingestion_jobs SET error = jsonb_set(error, '{retry_at}',"
                 " to_jsonb(now() - interval '1 second')) WHERE id = %s", self.job)
        self.assertEqual(sweep(self.engine).retries_due, 1)
        self.assertEqual(self.job_state(), 'queued')
        self.assertEqual(self.run_worker(stage=stage), 'succeeded')
        attempts = dict(self.sql('SELECT unit_key, attempt FROM job_stages WHERE job_id = %s',
                                 self.job))
        self.assertEqual(attempts, {'page:1': 1, 'page:2': 2, 'page:3': 1})
        self.assertEqual(self.published(), {'page:1': 1, 'page:2': 1, 'page:3': 1})

    def test_permanent_failure(self):
        self.assertEqual(self.run_worker(stage=FakeStage(fail_always='page:2')), 'failed')
        error = self.sql('SELECT error FROM ingestion_jobs WHERE id = %s', self.job)[0][0]
        self.assertEqual((error['code'], error['retryable']), ('PASSWORD_REQUIRED', False))
        self.assertEqual(self.published(), {'page:1': 1})  # finished work kept

    def test_cancel_queued_and_running(self):
        with self.engine.begin() as conn:
            self.assertEqual(queue.request_cancel(conn, self.job), 'cancelled')
        self.assertEqual(self.run_worker(), 'cancelled')
        self.assertEqual(self.published(), {})

        self.job, self.generation = self.make_job()
        with self.assertRaises(Crash):
            self.run_worker(crash_at='after_commit_before_next', crash_on=1)
        with self.engine.begin() as conn:
            self.assertEqual(queue.request_cancel(conn, self.job), 'cancel_requested')
        self.assertEqual(self.run_worker(), 'cancelled')  # stops before the next unit
        self.assertEqual(self.published(), {'page:1': 1})

    def test_empty_pipeline_fails_clearly(self):
        self.assertEqual(run_job(self.engine, self.store, self.job, [], 'w1'), 'failed')
        error = self.sql('SELECT error FROM ingestion_jobs WHERE id = %s', self.job)[0][0]
        self.assertEqual(error['code'], 'PIPELINE_NOT_CONFIGURED')


class OutboxTests(RecoveryTestCase):
    def emit(self):
        with self.engine.begin() as conn:
            outbox.emit(conn, QUEUED_TOPIC, {'job_id': str(self.job)})

    def unpublished(self):
        return self.sql("SELECT count(*) FROM outbox_events WHERE published_at IS NULL"
                        " AND payload->>'job_id' = %s", str(self.job))[0][0]

    def test_crash_between_send_and_mark_resends_and_consumer_dedupes(self):
        self.emit()
        broker = MemoryBroker()

        def crash(point):
            raise Crash(point)
        with self.assertRaises(Crash):
            outbox.dispatch(self.engine, broker, fault=crash)
        self.assertEqual(self.unpublished(), 1)  # not marked: will be resent
        outbox.dispatch(self.engine, broker)
        self.assertEqual(self.unpublished(), 0)
        mine = [m for m in broker.messages if m[1] == str(self.job)]
        self.assertEqual(len(mine), 2)
        self.assertEqual(mine[0][2], mine[1][2])  # same event id
        with self.engine.begin() as conn:
            self.assertTrue(outbox.first_delivery(conn, 'worker', mine[0][2]))
            self.assertFalse(outbox.first_delivery(conn, 'worker', mine[1][2]))

    def test_broker_loss_recovered_from_database(self):
        self.emit()
        broker = MemoryBroker()
        outbox.dispatch(self.engine, broker)
        broker.messages.clear()  # Redis restarted with an empty queue
        self.assertEqual(sweep(self.engine, stale_after='0 seconds').resignalled >= 1, True)
        outbox.dispatch(self.engine, broker)
        self.assertIn(str(self.job), [m[1] for m in broker.messages])
        self.assertEqual(self.run_worker(), 'succeeded')
        # A finished job is never re-signalled.
        broker.messages.clear()
        sweep(self.engine, stale_after='0 seconds')
        outbox.dispatch(self.engine, broker)
        self.assertNotIn(str(self.job), [m[1] for m in broker.messages])

    def test_running_job_with_live_lease_not_resignalled(self):
        with self.assertRaises(Crash):
            self.run_worker(crash_at='after_compute_before_commit', crash_on=1)
        sweep(self.engine, stale_after='0 seconds')
        self.assertEqual(self.unpublished(), 0)  # a worker still holds a live lease


class OperationLeaseTests(RecoveryTestCase):
    def test_operation_jobs_share_fencing(self):
        user = self.sql("INSERT INTO users (email, password_hash, role) VALUES (%s, 'x', 'admin')"
                        ' RETURNING id', f'{uuid.uuid4().hex}@example.test')[0][0]
        op = self.sql("INSERT INTO operation_jobs (kind, requested_by, target_manifest,"
                      " idempotency_key) VALUES ('backup', %s, '{}', %s) RETURNING id",
                      user, sha(uuid.uuid4().hex))[0][0]
        with self.engine.begin() as conn:
            first = queue.claim_operation(conn, op)
        with self.engine.begin() as conn:
            with self.assertRaises(queue.UnitBusy):
                queue.claim_operation(conn, op)
        self.sql("UPDATE operation_jobs SET lease_until = now() - interval '1 second' WHERE id = %s",
                 op)
        sweep(self.engine)
        with self.engine.begin() as conn:
            second = queue.claim_operation(conn, op)
        self.assertGreater(second.token, first.token)
        with self.assertRaises(queue.LeaseLost):
            with self.engine.begin() as conn:
                queue.finish_operation(conn, first, 'succeeded', {})
        with self.engine.begin() as conn:
            queue.finish_operation(conn, second, 'succeeded', {'done': True})


if __name__ == '__main__':
    unittest.main()
