"""Backup archive encryption and the retention policy (T052), without PostgreSQL."""
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.ops import archive
from backend.app.ops.archive import ArchiveError, BackupKey
from backend.app.ops.backup import list_backups, prune


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(archive, 'CHUNK', 1000)       # many chunks from small data
        patcher.start()
        self.addCleanup(patcher.stop)
        self.key = BackupKey.new('s' * 40)

    def sealed(self, data: bytes, path='db.dump') -> bytes:
        out = io.BytesIO()
        self.key.encrypt(io.BytesIO(data), out, path)
        return out.getvalue()

    def opened(self, blob: bytes, path='db.dump') -> bytes:
        return b''.join(self.key.decrypt(io.BytesIO(blob), path))

    def test_round_trip_at_chunk_edges(self):
        for size in (0, 1, 999, 1000, 1001, 3500):
            data = os.urandom(size)
            self.assertEqual(self.opened(self.sealed(data)), data, size)

    def test_tampering_truncation_and_moving_are_detected(self):
        blob = self.sealed(os.urandom(2500))
        first_chunk = 20 + 4 + int.from_bytes(blob[20:24], 'big')
        for bad in (blob[:-1], blob[:first_chunk], blob[:30] + bytes([blob[30] ^ 1]) + blob[31:],
                    blob + blob[20:first_chunk]):
            with self.assertRaises(ArchiveError):
                self.opened(bad)
        with self.assertRaises(ArchiveError):
            self.opened(blob, path='objects/other')            # bound to its path

    def test_the_key_is_checked_and_never_stored(self):
        described = self.key.describe()
        self.assertNotIn('s' * 40, json.dumps(described))
        self.assertEqual(BackupKey.for_manifest('s' * 40, described).key_id, self.key.key_id)
        for secret, code in (('t' * 40, 'WRONG_KEY'), (None, 'KEY_MISSING'),
                             ('short', 'KEY_TOO_SHORT')):
            with self.assertRaises(ArchiveError) as caught:
                BackupKey.for_manifest(secret, described)
            self.assertEqual(caught.exception.code, code)


class RetentionTests(unittest.TestCase):
    def make(self, root: Path, name: str, when: datetime) -> None:
        (root / name).mkdir()
        (root / name / 'manifest.json').write_text(json.dumps(
            {'format': 'bazi-backup-1', 'name': name, 'created_at': when.isoformat()}), 'utf-8')

    def test_seven_daily_and_four_weekly_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = datetime(2026, 10, 18, 3, tzinfo=timezone.utc)
            for day in range(60):                       # one nightly backup for 60 days
                self.make(root, f'n{day:02d}', start - timedelta(days=day))
            self.make(root, 'n00-extra', start - timedelta(hours=2))   # same day, older
            (root / '.half.partial').mkdir()                         # never counted
            plan = prune(root, dry_run=True)
            kept = set(plan['kept'])
            self.assertTrue({f'n{d:02d}' for d in range(7)} <= kept)
            self.assertNotIn('n00-extra', kept)
            self.assertLessEqual(len(kept), 7 + 4)
            self.assertEqual(len(list_backups(root)), 61)      # dry run removed nothing
            prune(root)
            self.assertEqual({b['name'] for b in list_backups(root)}, kept)
            self.assertTrue((root / '.half.partial').exists())


if __name__ == '__main__':
    unittest.main()
