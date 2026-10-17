"""Reprocessing keeps corrections, withdrawal revokes at once, GC keeps referenced bytes (T019)."""
from datetime import timedelta
import io
import os
import time
import uuid

from backend.app.storage.gc import collect
from backend.app.storage.service import store_object
from tests.integration.env import PipelineTestCase


class ReprocessTests(PipelineTestCase):
    def process(self, version, **body):
        return self.c.post(f'/api/v1/book-versions/{version}/process', json=body,
                           headers={'Idempotency-Key': uuid.uuid4().hex})

    def withdraw(self, version):
        return self.c.post(f'/api/v1/book-versions/{version}/withdraw',
                           json={'reason': 'quyền sử dụng bị thu hồi'})

    def linked(self, gen, number):
        return self.sql('SELECT r.id::text, r.revision_no FROM generation_pages gp'
                        ' JOIN pages p ON p.id = gp.page_id JOIN page_revisions r'
                        ' ON r.id = gp.page_revision_id WHERE gp.generation_id = %s'
                        ' AND p.physical_page_number = %s', gen, number)[0]

    def test_full_reprocess_keeps_the_latest_correction(self):
        version, gen = self.ready(pages=3)
        page = next(p for p in self.c.get(f'/api/v1/book-versions/{version}/pages')
                    .json()['data'] if p['physical_page_number'] == 2)
        blocks = self.c.get(f"/api/v1/page-revisions/{page['revision_id']}").json()['data']
        block = next(b for b in blocks['blocks'] if b['kind'] == 'paragraph')
        fixed = block['text'].replace('thương quan', 'thương quan kiến quan')
        correction = self.c.post(
            f"/api/v1/pages/{page['page_id']}/corrections",
            headers={'If-Match': f'"{page["revision_id"]}"', 'Idempotency-Key': uuid.uuid4().hex},
            json={'base_revision_id': page['revision_id'], 'reason': 'sửa chữ',
                  'changes': [{'ordinal': block['ordinal'], 'text': fixed}]})
        self.assertEqual(correction.status_code, 201, correction.text)
        corrected = correction.json()['data']['revision']['id']
        busy = self.process(version)                    # the correction's rebuild is queued
        self.assertEqual((busy.status_code, busy.json()['code']), (409, 'JOB_ACTIVE'))
        self.assertEqual(self.run_pipeline(correction.json()['data']['job_id']), 'succeeded')
        revisions = self.sql('SELECT count(*) FROM page_revisions r JOIN pages p'
                             ' ON p.id = r.page_id WHERE p.book_version_id = %s', version)[0][0]

        response = self.process(version)
        self.assertEqual(response.status_code, 202, response.text)
        job = response.json()['data']
        self.assertEqual((job['state'], job['parent_job_id']), ('queued', None))
        busy = self.process(version)
        self.assertEqual((busy.status_code, busy.json()['code']), (409, 'JOB_ACTIVE'))
        self.assertEqual(self.run_pipeline(job['id']), 'succeeded')
        rebuilt = job['generation_id']
        # The fix survives a rebuild from source; nothing is re-extracted.
        self.assertEqual(self.linked(rebuilt, 2)[0], corrected)
        self.assertEqual(self.linked(rebuilt, 1), self.linked(gen, 1))
        self.assertEqual(self.sql('SELECT count(*) FROM page_revisions r JOIN pages p'
                                  ' ON p.id = r.page_id WHERE p.book_version_id = %s',
                                  version)[0][0], revisions)
        texts = ' '.join(t for (t,) in self.sql(
            'SELECT c.text FROM generation_chunks gc JOIN chunks c ON c.id = gc.chunk_id'
            ' WHERE gc.generation_id = %s', rebuilt))
        self.assertIn('thương quan kiến quan', texts)
        self.assertEqual(self.sql('SELECT state FROM generations WHERE id = %s', rebuilt),
                         [('ready',)])

    def test_withdrawal_revokes_visibility_immediately(self):
        (a, gen_a), (b, gen_b) = self.ready(), self.ready()
        for gen in (gen_a, gen_b):
            self.assertEqual(self.publish(gen).status_code, 201)
        before = self.active()
        epoch = self.sql("SELECT visibility_epoch FROM active_corpus")[0][0]
        response = self.withdraw(a)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()['data']
        self.assertNotEqual(data['active_release_id'], before)
        self.assertEqual(data['visibility_epoch'], epoch + 1)
        members = self.members(self.active())
        self.assertNotIn(a, {v for v, _ in members})
        self.assertIn((b, gen_b), members)
        self.assertEqual(self.sql('SELECT state FROM generations WHERE id = %s', gen_a),
                         [('withdrawn',)])
        again = self.withdraw(a)                         # idempotent, no further epoch bump
        self.assertEqual((again.status_code, again.json()['data']['visibility_epoch']),
                         (200, epoch + 1))
        refused = self.publish(gen_a)
        self.assertEqual(refused.json()['code'], 'VERSION_WITHDRAWN')
        self.assertEqual(self.process(a).json()['code'], 'VERSION_WITHDRAWN')
        # The next publication never brings the withdrawn version back.
        _, gen_c = self.ready()
        self.assertEqual(self.publish(gen_c).status_code, 201)
        self.assertNotIn(a, {v for v, _ in self.members(self.active())})
        audit = self.sql("SELECT redacted_diff->>'reason', redacted_diff->>'already_withdrawn'"
                         " FROM audit_logs WHERE action = 'book_version.withdraw'"
                         " AND target_id = %s ORDER BY created_at", a)
        self.assertEqual(audit, [('quyền sử dụng bị thu hồi', 'false'),
                                 ('quyền sử dụng bị thu hồi', 'true')])

    def test_withdrawal_cancels_jobs_in_flight(self):
        version, gen, job = self.queue()
        self.assertEqual(self.withdraw(version).status_code, 200)
        self.assertEqual(self.sql('SELECT state FROM ingestion_jobs WHERE id = %s', job),
                         [('cancelled',)])
        self.assertEqual(self.sql('SELECT state FROM generations WHERE id = %s', gen),
                         [('withdrawn',)])
        self.assertEqual(self.run_pipeline(job), 'cancelled')

    def test_gc_removes_only_old_unreferenced_bytes(self):
        version, _ = self.ready()
        referenced = self.sql('SELECT o.id::text, o.object_key FROM objects o JOIN book_versions v'
                              ' ON v.object_id = o.id WHERE v.id = %s', version)[0]
        with self.engine.begin() as conn:
            old = store_object(conn, self.store, io.BytesIO(os.urandom(64)), 'application/pdf')
            new = store_object(conn, self.store, io.BytesIO(os.urandom(64)), 'application/pdf')
        self.sql("UPDATE objects SET created_at = now() - interval '3 days' WHERE id = ANY(%s)",
                 [str(old['id']), referenced[0]])
        orphan_old = self.store.put_if_absent(io.BytesIO(os.urandom(64)))
        orphan_new = self.store.put_if_absent(io.BytesIO(os.urandom(64)))
        stale = time.time() - 3 * 86400
        os.utime(self.store._path(orphan_old.key), (stale, stale))

        dry = collect(self.owner_engine, self.store, timedelta(hours=24), dry_run=True)
        self.assertGreaterEqual(dry['unreferenced_objects'], 1)
        self.assertGreaterEqual(dry['orphan_blobs'], 1)
        self.assertIsNotNone(self.store.stat(orphan_old.key))
        result = collect(self.owner_engine, self.store, timedelta(hours=24))
        self.assertGreaterEqual(result['removed_objects'], 1)
        self.assertIsNone(self.store.stat(orphan_old.key))
        self.assertIsNotNone(self.store.stat(orphan_new.key))
        self.assertIsNotNone(self.store.stat(referenced[1]))
        remaining = {r for (r,) in self.sql('SELECT id::text FROM objects')}
        self.assertNotIn(str(old['id']), remaining)
        self.assertTrue({str(new['id']), referenced[0]} <= remaining)


if __name__ == '__main__':
    import unittest
    unittest.main()
