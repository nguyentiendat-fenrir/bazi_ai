"""ObjectStore contract for both adapters, plus objects-table integration.

The contract suite runs against the local volume and an S3-compatible endpoint
(moto's in-process S3 implementation). The DB part needs BAZI_TEST_DATABASE_URL.
"""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import uuid

import boto3
from moto import mock_aws

from backend.app.storage.base import (ChecksumMismatch, InvalidKey, ObjectNotFound, StorageError,
                                      copy_verified, object_key)
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.s3 import S3ObjectStore
from backend.app.storage.service import ObjectInUse, delete_object, orphan_blobs, store_object
from tests.integration.db import ADMIN_URL, database_url, drop_database, engine_for, migrated_database

PAYLOAD = 'Khách Chủ — 甲乙丙丁'.encode('utf-8') * 3
BIG = bytes(range(256)) * (3 * 4096 + 7)  # ~3 MiB, crosses the 1 MiB chunk size


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_all(chunks) -> bytes:
    return b''.join(chunks)


class StoreContract:
    """Mixin: subclasses provide ``self.store`` and ``staging_leftovers()``."""

    def make_store(self, max_bytes=None):
        raise NotImplementedError

    def staging_leftovers(self) -> int:
        raise NotImplementedError

    def test_roundtrip_is_content_addressed(self):
        stored = self.store.put_if_absent(io.BytesIO(PAYLOAD))
        self.assertEqual(stored.key, object_key(sha(PAYLOAD)))
        self.assertTrue(stored.created)
        self.assertEqual(read_all(self.store.get_stream(stored.key)), PAYLOAD)
        stat = self.store.stat(stored.key)
        self.assertEqual((stat.size_bytes, stat.sha256), (len(PAYLOAD), sha(PAYLOAD)))
        self.assertIn(stored.key, {s.key for s in self.store.list_manifest()})

    def test_identical_bytes_are_stored_once(self):
        first = self.store.put_if_absent(io.BytesIO(PAYLOAD))
        second = self.store.put_if_absent(io.BytesIO(PAYLOAD))
        self.assertEqual((first.key, second.created), (second.key, False))
        self.assertEqual(len(list(self.store.list_manifest())), 1)
        self.assertEqual(self.staging_leftovers(), 0)

    def test_large_stream_roundtrip(self):
        stored = self.store.put_if_absent(io.BytesIO(BIG))
        self.assertEqual((stored.sha256, stored.size_bytes), (sha(BIG), len(BIG)))
        self.assertEqual(sha(read_all(self.store.get_stream(stored.key))), sha(BIG))

    def test_checksum_mismatch_stores_nothing(self):
        with self.assertRaises(ChecksumMismatch):
            self.store.put_if_absent(io.BytesIO(PAYLOAD), expected_sha256=sha(b'other'))
        self.assertEqual(list(self.store.list_manifest()), [])
        self.assertEqual(self.staging_leftovers(), 0)

    def test_size_limit_enforced_while_streaming(self):
        small = self.make_store(max_bytes=10)
        with self.assertRaises(StorageError):
            small.put_if_absent(io.BytesIO(PAYLOAD))
        self.assertEqual(list(small.list_manifest()), [])
        self.assertEqual(self.staging_leftovers(), 0)

    def test_ranges(self):
        key = self.store.put_if_absent(io.BytesIO(BIG)).key
        for start, end in ((0, 1), (5, 17), (1024 * 1024 - 3, 1024 * 1024 + 9), (None, 10),
                           (len(BIG) - 4, None), (10, 10)):
            with self.subTest(start=start, end=end):
                self.assertEqual(read_all(self.store.get_stream(key, start, end)),
                                 BIG[start:end] if (start, end) != (10, 10) else b'')

    def test_keys_are_allowlisted(self):
        for key in ('objects/../../etc/passwd', '../objects/aa/' + 'a' * 64,
                    'staging/' + 'a' * 64, 'objects/AA/' + 'A' * 64, f'objects/zz/{"a" * 64}',
                    'objects/aa/' + 'a' * 63, '/objects/aa/' + 'a' * 64):
            with self.subTest(key=key):
                for call in (lambda: read_all(self.store.get_stream(key)),
                             lambda: self.store.stat(key), lambda: self.store.delete(key)):
                    with self.assertRaises(InvalidKey):
                        call()

    def test_missing_object(self):
        key = object_key(sha(b'never stored'))
        self.assertIsNone(self.store.stat(key))
        with self.assertRaises(ObjectNotFound):
            read_all(self.store.get_stream(key))

    def test_delete(self):
        key = self.store.put_if_absent(io.BytesIO(PAYLOAD)).key
        self.store.delete(key)
        self.assertIsNone(self.store.stat(key))
        self.store.delete(key)  # idempotent


class LocalStoreTests(StoreContract, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = self.make_store()

    def make_store(self, max_bytes=None):
        return LocalObjectStore(self.tmp.name, max_bytes)

    def staging_leftovers(self):
        staging = Path(self.tmp.name) / 'staging'
        return len(list(staging.iterdir())) if staging.is_dir() else 0

    def test_symlink_escape_rejected(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        digest = sha(b'x')
        (Path(self.tmp.name) / 'objects').mkdir()
        try:
            (Path(self.tmp.name) / 'objects' / digest[:2]).symlink_to(outside.name,
                                                                     target_is_directory=True)
        except OSError:
            self.skipTest('symlinks need privileges on this OS')
        with self.assertRaises(InvalidKey):
            self.store.stat(object_key(digest))


class S3StoreTests(StoreContract, unittest.TestCase):
    def setUp(self):
        mock = mock_aws()
        mock.start()
        self.addCleanup(mock.stop)
        self.client = boto3.client('s3', region_name='us-east-1', aws_access_key_id='testing',
                                   aws_secret_access_key='testing')
        self.bucket = f'bazi-{uuid.uuid4().hex[:8]}'
        self.client.create_bucket(Bucket=self.bucket)
        self.store = self.make_store()

    def make_store(self, max_bytes=None):
        return S3ObjectStore(self.client, self.bucket, max_bytes)

    def staging_leftovers(self):
        return self.client.list_objects_v2(Bucket=self.bucket, Prefix='staging/')['KeyCount']

    def test_copy_verified_between_adapters(self):
        local_dir = tempfile.TemporaryDirectory()
        self.addCleanup(local_dir.cleanup)
        local = LocalObjectStore(local_dir.name)
        key = local.put_if_absent(io.BytesIO(BIG)).key
        copied = copy_verified(local, key, self.store)
        self.assertEqual((copied.key, copied.sha256), (key, sha(BIG)))
        self.assertEqual(self.store.stat(key).sha256, sha(BIG))


class ObjectServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ADMIN_URL:
            raise unittest.SkipTest('BAZI_TEST_DATABASE_URL is not set')
        cls.db = migrated_database('head')
        cls.engine = engine_for(database_url(cls.db))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        drop_database(cls.db)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = LocalObjectStore(self.tmp.name)

    def store_bytes(self, data):
        with self.engine.begin() as conn:
            return store_object(conn, self.store, io.BytesIO(data), 'application/pdf')

    def test_same_bytes_share_one_row(self):
        data = uuid.uuid4().bytes * 100
        first, second = self.store_bytes(data), self.store_bytes(data)
        self.assertEqual((first['id'], first['created'], second['created']),
                         (second['id'], True, False))
        self.assertEqual(first['state'], 'ready')

    def test_unreferenced_object_deleted_row_then_blob(self):
        row = self.store_bytes(uuid.uuid4().bytes)
        self.assertTrue(delete_object(self.engine, self.store, row['id']))
        self.assertIsNone(self.store.stat(row['object_key']))
        self.assertFalse(delete_object(self.engine, self.store, row['id']))

    def test_referenced_object_cannot_be_deleted(self):
        row = self.store_bytes(uuid.uuid4().bytes)
        with self.engine.begin() as conn:
            user = conn.exec_driver_sql(
                "INSERT INTO users (email, password_hash, role) VALUES (%(e)s, 'x', 'admin')"
                ' RETURNING id', {'e': f'{uuid.uuid4().hex}@example.test'}).scalar()
            book = conn.exec_driver_sql(
                "INSERT INTO books (title, normalized_title, language, created_by)"
                " VALUES ('t', 't', 'vi', %(u)s) RETURNING id", {'u': user}).scalar()
            conn.exec_driver_sql(
                "INSERT INTO book_versions (book_id, object_id, edition_label, version_no,"
                " rights_status, uploaded_by) VALUES (%(b)s, %(o)s, 'v1', 1, 'unknown', %(u)s)",
                {'b': book, 'o': row['id'], 'u': user})
        with self.assertRaises(ObjectInUse):
            delete_object(self.engine, self.store, row['id'])
        self.assertIsNotNone(self.store.stat(row['object_key']))  # blob untouched

    def test_orphans_are_blobs_without_rows(self):
        stray = self.store.put_if_absent(io.BytesIO(uuid.uuid4().bytes)).key
        kept = self.store_bytes(uuid.uuid4().bytes)['object_key']
        with self.engine.connect() as conn:
            orphans = orphan_blobs(conn, self.store)
        self.assertIn(stray, orphans)
        self.assertNotIn(kept, orphans)


if __name__ == '__main__':
    unittest.main()
