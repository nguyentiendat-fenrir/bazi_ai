import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts import verify_inputs as v
from tests.fixtures.rar_factory import make_rar


PAYLOADS = {'backend/bazi.py': b'# synthetic_test\r\nraise RuntimeError("NEVER EXECUTE")\r\n',
            '.gitignore': b'.venv/\r\n'}
EXPECTED = {p: {'size_bytes': len(b), 'sha256': v.digest(b)} for p, b in PAYLOADS.items()}
ENTRIES = [('bazi/' + p, b) for p, b in PAYLOADS.items()]


class PathTests(unittest.TestCase):
    def test_malicious_paths(self):
        for name in ['../escape', 'bazi/../../escape', '/tmp/escape', 'C:/escape',
                     'C:escape', '\\\\server\\share', 'bazi\\..\\escape',
                     'bazi/./x', 'bazi//x', 'bazi/x:stream', 'bazi/NUL.txt',
                     'bazi/COM1', 'bazi/LPT¹.txt', 'bazi/x.', 'bazi/x ',
                     'bazi/a\x00b', 'bazi/a\nb', 'bazi/*.py', 'bazi/?.py', '']:
            with self.subTest(name=name), self.assertRaises(v.VerificationError):
                v.safe_member(name)

    def test_windows_separator_and_directory(self):
        self.assertEqual(v.safe_member('bazi\\backend\\x.py'), 'bazi/backend/x.py')
        self.assertEqual(v.safe_member('bazi/backend/', True), 'bazi/backend')

    def test_exclusions(self):
        for path in ['.venv/a.py', '.git/config', 'backend/__pycache__/a.pyc',
                     'backend/X.PYD', 'frontend/node_modules/x.js', 'bin/x.exe']:
            self.assertTrue(v.excluded(path), path)
        self.assertFalse(v.excluded('.gitignore'))
        self.assertFalse(v.excluded('backend/bazi.py'))


class ArchiveTests(unittest.TestCase):
    def reject(self, entries, code, expected=EXPECTED):
        with self.assertRaisesRegex(v.VerificationError, code):
            v.archive_payloads(make_rar(entries), expected)

    def test_real_rar_roundtrip_bytes(self):
        payloads, listing = v.archive_payloads(make_rar(ENTRIES), EXPECTED)
        self.assertEqual(payloads, PAYLOADS)
        self.assertEqual(len(listing), 2)

    def test_excluded_runtime_is_never_extracted(self):
        excluded = [('bazi/.venv/x.exe', b'not executable'),
                    ('bazi/.git/config', b'private'),
                    ('bazi/backend/__pycache__/x.pyc', b'cache')]
        payloads, listing = v.archive_payloads(make_rar(ENTRIES + excluded), EXPECTED)
        self.assertEqual(payloads, PAYLOADS)
        self.assertEqual(sum(x['action'] == 'excluded' for x in listing), 3)

    def test_traversal_even_inside_excluded_folder(self):
        for path in ['../escape.py', 'bazi/../../escape.py', 'bazi/.venv/../../escape.py',
                     'C:/escape.py', 'bazi/a:stream', 'bazi\\..\\escape.py']:
            with self.subTest(path=path):
                self.reject(ENTRIES + [(path, b'evil')], 'UNSAFE_ARCHIVE_PATH')

    def test_duplicate_casefolded_path(self):
        self.reject(ENTRIES + [('bazi/backend/BAZI.py', b'bad')], 'DUPLICATE_ARCHIVE_PATH')

    def test_symlink_and_device(self):
        for mode in [0o120777, 0o020666, 0o010666]:
            with self.subTest(mode=mode):
                self.reject(ENTRIES + [('bazi/.venv/link', b'target', mode)],
                            'ARCHIVE_LINK_OR_SPECIAL_FILE')

    def test_file_directory_collision(self):
        self.reject(ENTRIES + [('bazi/.git/x', b'1'), ('bazi/.git/x/y', b'2')],
                    'ARCHIVE_FILE_DIRECTORY_COLLISION')

    def test_wrong_source_size(self):
        self.reject([('bazi/backend/bazi.py', b'bad')], 'SOURCE_SIZE_MISMATCH')

    def test_wrong_source_hash(self):
        rows = [('bazi/' + p, b'x' * len(b)) for p, b in PAYLOADS.items()]
        self.reject(rows, 'SOURCE_HASH_MISMATCH')

    def test_missing_source(self):
        self.reject(ENTRIES[:1], 'MISSING_SOURCE_MEMBERS')

    def test_unexpected_source(self):
        self.reject(ENTRIES + [('bazi/new.py', b'1')], 'UNEXPECTED_SOURCE_FILE')

    def test_unexpected_root(self):
        self.reject([('other/bazi.py', b'1')], 'UNEXPECTED_ARCHIVE_ROOT')

    def test_wrong_inventory_totals(self):
        with self.assertRaisesRegex(v.VerificationError, 'ARCHIVE_TOTALS_MISMATCH'):
            v.archive_payloads(make_rar(ENTRIES), EXPECTED, {'entries': 999, 'expanded_bytes': 0})

    def test_expansion_limit(self):
        from unittest.mock import patch
        with patch.object(v, 'MAX_EXPANDED', 1):
            self.reject(ENTRIES, 'ARCHIVE_EXPANSION_LIMIT')

    def test_corrupt_rar(self):
        with self.assertRaisesRegex(v.VerificationError, 'RAR_READ_FAILED'):
            v.archive_payloads(b'not a RAR', EXPECTED)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_extract_and_idempotency_without_execution(self):
        self.assertEqual(v.preserve(self.root, PAYLOADS, EXPECTED), 'EXTRACTED_VERIFIED')
        times = {p: (self.root / 'legacy/bazi' / p).stat().st_mtime_ns for p in PAYLOADS}
        self.assertEqual(v.preserve(self.root, PAYLOADS, EXPECTED), 'ALREADY_VERIFIED')
        for p, data in PAYLOADS.items():
            target = self.root / 'legacy/bazi' / p
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(target.stat().st_mtime_ns, times[p])

    def test_modified_source_is_not_overwritten(self):
        v.preserve(self.root, PAYLOADS, EXPECTED)
        path = self.root / 'legacy/bazi/backend/bazi.py'
        path.write_bytes(b'user edit')
        with self.assertRaisesRegex(v.VerificationError, 'LEGACY_HASH_MISMATCH'):
            v.preserve(self.root, PAYLOADS, EXPECTED)
        self.assertEqual(path.read_bytes(), b'user edit')

    def test_partial_tree_is_not_repaired(self):
        target = self.root / 'legacy/bazi'
        target.mkdir(parents=True)
        with self.assertRaisesRegex(v.VerificationError, 'INCOMPLETE_LEGACY'):
            v.preserve(self.root, PAYLOADS, EXPECTED)
        self.assertEqual(list(target.iterdir()), [])

    def test_extra_files_are_not_deleted(self):
        v.preserve(self.root, PAYLOADS, EXPECTED)
        target = self.root / 'legacy/bazi/user.txt'
        target.write_bytes(b'keep me')
        with self.assertRaisesRegex(v.VerificationError, 'UNEXPECTED_LEGACY_FILE'):
            v.verify_legacy(self.root, EXPECTED)
        self.assertEqual(target.read_bytes(), b'keep me')

    def test_empty_runtime_directory_rejected(self):
        v.preserve(self.root, PAYLOADS, EXPECTED)
        (self.root / 'legacy/bazi/.venv').mkdir()
        with self.assertRaisesRegex(v.VerificationError, 'UNEXPECTED_LEGACY_DIRECTORY'):
            v.verify_legacy(self.root, EXPECTED)

    def test_bad_payload_never_published(self):
        with self.assertRaisesRegex(v.VerificationError, 'PAYLOAD_HASH_MISMATCH'):
            v.preserve(self.root, {p: b'bad' for p in PAYLOADS}, EXPECTED)
        self.assertFalse((self.root / 'legacy').exists())

    def test_hardlink_destination_rejected(self):
        v.preserve(self.root, PAYLOADS, EXPECTED)
        path = self.root / 'legacy/bazi/backend/bazi.py'
        os.link(path, self.root / 'external.py')
        with self.assertRaisesRegex(v.VerificationError, 'UNSAFE_LOCAL_LINK'):
            v.verify_legacy(self.root, EXPECTED)


class ContractTests(unittest.TestCase):
    def test_audit_source_count_matches_verified_manifest(self):
        inputs, sources, totals, issues = v.load_contract(v.ROOT)
        self.assertEqual(len(inputs), 4)
        self.assertEqual(len(sources), 10)
        self.assertEqual(totals, {'entries': 1444, 'expanded_bytes': 43471231})
        self.assertNotIn('SPEC_CONFLICT_SOURCE_COUNT', issues)
        self.assertNotIn('SPEC_CONFLICT_PDF_HASH', issues)


class SecretScanTests(unittest.TestCase):
    def test_local_env_must_be_ignored_and_untracked(self):
        from scripts.scan_secrets import ignored_local_env
        self.assertTrue(ignored_local_env(Path(__file__).resolve().parents[2]))

    def test_synthetic_secret_is_detected_without_echoing_value(self):
        from scripts.scan_secrets import findings
        synthetic = 'sk-' + 'SYNTHETIC0' * 4
        results = findings('token = "' + synthetic + '"')
        self.assertEqual(results, [{'rule': 'provider_token', 'line': 1}])
        self.assertNotIn(synthetic, json.dumps(results))


if __name__ == '__main__':
    unittest.main()
