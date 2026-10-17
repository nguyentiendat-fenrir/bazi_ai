"""Backups and restores onto new volumes (T052.1/T053.1).

Needs pg_dump/pg_restore at least as new as the server (PostgreSQL 17): they are in the
app/test image; elsewhere these tests skip, which is not a pass.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import psycopg

from backend.app.ops.backup import BackupError, Database, create_backup, preflight, restore
from backend.app.storage.gc import MAINTENANCE_LOCK, collect
from backend.app.storage.local import LocalObjectStore
from tests.integration.db import create_database, database_url, drop_database
from tests.integration.env import PipelineTestCase

TOOLS = shutil.which('pg_dump') and shutil.which('pg_restore')


@unittest.skipUnless(TOOLS, 'needs PostgreSQL 17 client tools (run in the app/test image)')
class BackupRestoreTests(PipelineTestCase):
    def setUp(self):
        self.dest = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dest, True)

    def owner(self) -> Database:
        return Database.from_conninfo(database_url(self.db))

    def empty_target(self):
        name = create_database()
        self.addCleanup(drop_database, name)
        store = LocalObjectStore(Path(tempfile.mkdtemp()) / 'objects')
        self.addCleanup(shutil.rmtree, store.root.parent, True)
        return Database.from_conninfo(database_url(name)), store

    def test_backup_restores_onto_new_volumes(self):
        version, gen = self.ready()
        self.assertEqual(self.publish(gen).status_code, 201)
        manifest = create_backup(self.owner(), self.store, self.dest, 'nightly-1')
        folder = self.dest / 'nightly-1'
        self.assertTrue((folder / 'manifest.json').is_file())
        self.assertEqual([p.name for p in self.dest.iterdir()], ['nightly-1'])   # no .partial
        self.assertEqual(json.loads((folder / 'manifest.json').read_text('utf-8'))['name'],
                         'nightly-1')
        self.assertGreaterEqual(manifest['counts']['book_versions'], 1)
        self.assertEqual(manifest['active_corpus']['release_id'], self.active())
        source = self.sql('SELECT o.object_key FROM book_versions v JOIN objects o'
                          ' ON o.id = v.object_id WHERE v.id = %s', version)[0][0]
        self.assertIn(source, {o['key'] for o in manifest['objects']['items']})
        with self.assertRaises(BackupError) as caught:
            create_backup(self.owner(), self.store, self.dest, 'nightly-1')
        self.assertEqual(caught.exception.code, 'BACKUP_EXISTS')

        checked = preflight(folder / 'manifest.json')
        self.assertTrue(checked['ok'], checked)
        target, store = self.empty_target()
        with self.assertRaises(BackupError) as caught:
            restore(folder / 'manifest.json', target, store, confirm='nightly')
        self.assertEqual(caught.exception.code, 'CONFIRMATION_MISMATCH')
        report = restore(folder / 'manifest.json', target, store, confirm='nightly-1')
        self.assertEqual((report['objects'], report['schema_head'], report['active_corpus']),
                         (manifest['objects']['count'], manifest['schema_head'],
                          manifest['active_corpus']))
        # The restored system serves the same source page text and bytes.
        with psycopg.connect(target.conninfo()) as conn:
            restored = conn.execute(
                'SELECT r.normalized_text FROM page_revisions r JOIN pages p ON p.id = r.page_id'
                ' WHERE p.book_version_id = %s ORDER BY p.physical_page_number, r.revision_no'
                ' LIMIT 1', (version,)).fetchone()[0]
        original = self.sql(
            'SELECT r.normalized_text FROM page_revisions r JOIN pages p ON p.id = r.page_id'
            ' WHERE p.book_version_id = %s ORDER BY p.physical_page_number, r.revision_no'
            ' LIMIT 1', version)[0][0]
        self.assertEqual(restored, original)
        self.assertEqual(b''.join(store.get_stream(source)), b''.join(self.store.get_stream(source)))
        with self.assertRaises(BackupError) as caught:
            restore(folder / 'manifest.json', target, store, confirm='nightly-1')
        self.assertEqual(caught.exception.code, 'TARGET_NOT_EMPTY')

    def test_preflight_refuses_damaged_backups_and_restores_nothing(self):
        self.ready()
        manifest = create_backup(self.owner(), self.store, self.dest, 'damaged-1')
        folder = self.dest / 'damaged-1'
        blob = folder / manifest['objects']['items'][0]['key']
        blob.write_bytes(blob.read_bytes() + b'x')
        checked = preflight(folder / 'manifest.json')
        self.assertFalse(checked['ok'])
        self.assertEqual([c['name'] for c in checked['checks'] if not c['ok']], ['objects'])
        target, store = self.empty_target()
        with self.assertRaises(BackupError) as caught:
            restore(folder / 'manifest.json', target, store, confirm='damaged-1')
        self.assertEqual(caught.exception.code, 'PREFLIGHT_FAILED')
        with psycopg.connect(target.conninfo()) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM pg_tables"
                                          " WHERE schemaname = 'public'").fetchone()[0], 0)

        dump = folder / 'db.dump'
        dump.write_bytes(dump.read_bytes()[:-10])
        failed = {c['name'] for c in preflight(folder / 'manifest.json')['checks'] if not c['ok']}
        self.assertEqual(failed, {'objects', 'database_dump'})
        newer = json.loads((folder / 'manifest.json').read_text('utf-8'))
        newer['schema_head'] = '9999_from_the_future'
        (folder / 'manifest.json').write_text(json.dumps(newer), 'utf-8')
        failed = {c['name'] for c in preflight(folder / 'manifest.json')['checks'] if not c['ok']}
        self.assertIn('schema', failed)



class MaintenanceLockTests(PipelineTestCase):
    def test_garbage_collection_waits_for_a_backup(self):
        owner = Database.from_conninfo(database_url(self.db))
        with psycopg.connect(owner.conninfo(), autocommit=True) as backup:
            backup.execute('SELECT pg_advisory_lock(hashtext(%s))', (MAINTENANCE_LOCK,))
            self.assertEqual(collect(self.owner_engine, self.store, dry_run=True)['skipped'],
                             'BACKUP_RUNNING')
        self.assertNotIn('skipped', collect(self.owner_engine, self.store, dry_run=True))


if __name__ == '__main__':
    unittest.main()
