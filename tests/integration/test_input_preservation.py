"""Filesystem + real RAR reader integration, synthetic_test inputs only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts import verify_inputs as v
from tests.fixtures.rar_factory import make_rar
from tests.unit.test_verify_inputs import ENTRIES, EXPECTED, PAYLOADS


class InputPreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = make_rar(ENTRIES)
        for directory in ['docs', 'evidence', 'inputs/source', 'inputs/books', 'scripts']:
            (self.root / directory).mkdir(parents=True)
        shutil.copyfile(v.ROOT / 'scripts/verify_inputs.py', self.root / 'scripts/verify_inputs.py')
        self.write_contract()

    def write_contract(self, entries=ENTRIES, declared_count=2):
        data = self.archive
        rows = [{'relative_path': p, **expected} for p, expected in EXPECTED.items()]
        (self.root / 'evidence/source_manifest.json').write_text(json.dumps(rows), encoding='utf-8')
        pdf = b'%PDF-synthetic_test'
        (self.root / 'evidence/pdf_metrics.json').write_text(json.dumps([
            {'name': 'synthetic.pdf', 'sha256': v.digest(pdf)}
        ]), encoding='utf-8')
        (self.root / 'docs/02_SOURCE_CODE_AUDIT.md').write_text(
            '# synthetic_test contract\n'
            f'| bazi.rar | {len(data)} | `{v.digest(data)}` |\n'
            f'| synthetic.pdf | {len(pdf)} | `{v.digest(pdf)}` |\n'
            f'RAR có {len(entries)} entries gồm thư mục, '
            f'{sum(len(x[1]) for x in entries)} bytes tổng uncompressed.\n'
            f'source nghiệp vụ ({declared_count} tệp gồm .gitignore)\n', encoding='utf-8')
        (self.root / 'inputs/source/bazi.rar').write_bytes(data)

    def cli(self, mode):
        result = subprocess.run([sys.executable, 'scripts/verify_inputs.py', mode],
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_cli_check_extract_recheck_and_original_bytes(self):
        code, result = self.cli('--check')
        self.assertEqual(code, 1)
        self.assertEqual(result['issues'], ['LEGACY_MISSING'])
        self.assertFalse((self.root / 'legacy').exists())
        code, result = self.cli('--extract')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['legacy'], 'EXTRACTED_VERIFIED')
        self.assertEqual(result['missing_books_optional_for_T001'], ['inputs/books/synthetic.pdf'])
        self.assertEqual((self.root / 'inputs/source/bazi.rar').read_bytes(), self.archive)
        code, result = self.cli('--check')
        self.assertEqual(code, 0, result)
        for p, b in PAYLOADS.items():
            self.assertEqual((self.root / 'legacy/bazi' / p).read_bytes(), b)

    def test_missing_rar_reports_exact_relative_path(self):
        (self.root / 'inputs/source/bazi.rar').unlink()
        code, result = self.cli('--check')
        self.assertEqual(code, 1)
        self.assertIn('SOURCE_ARCHIVE_MISSING', result['issues'])
        self.assertEqual(result['inputs'][0]['path'], 'inputs/source/bazi.rar')
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_wrong_rar_hash_blocks_all_extraction(self):
        (self.root / 'inputs/source/bazi.rar').write_bytes(b'wrong')
        code, result = self.cli('--extract')
        self.assertEqual(code, 1)
        self.assertIn('SOURCE_ARCHIVE_MISMATCH', result['issues'])
        self.assertFalse((self.root / 'legacy').exists())

    def test_present_pdf_hash_is_checked(self):
        path = self.root / 'inputs/books/synthetic.pdf'
        path.write_bytes(b'%PDF-synthetic_test')
        self.assertEqual(self.cli('--extract')[0], 0)
        path.write_bytes(b'changed')
        code, result = self.cli('--check')
        self.assertEqual(code, 1)
        self.assertIn('PDF_HASH_MISMATCH', result['issues'])

    def test_spec_disagreement_blocks_extraction(self):
        self.write_contract(declared_count=1)
        code, result = self.cli('--extract')
        self.assertEqual(code, 1)
        self.assertIn('SPEC_CONFLICT_SOURCE_COUNT', result['issues'])
        self.assertFalse((self.root / 'legacy').exists())

    def test_malicious_rar_never_writes_source_or_outside_file(self):
        entries = ENTRIES + [('bazi/../../escape.py', b'evil')]
        self.archive = make_rar(entries)
        self.write_contract(entries=entries)
        code, result = self.cli('--extract')
        self.assertEqual(code, 1)
        self.assertIn('UNSAFE_ARCHIVE_PATH', result['issues'])
        self.assertFalse((self.root / 'legacy').exists())
        self.assertFalse((self.root / 'escape.py').exists())

    def test_bad_source_crc_never_publishes(self):
        data = bytearray(self.archive)
        index = data.index(PAYLOADS['backend/bazi.py'])
        data[index] ^= 1
        self.archive = bytes(data)
        self.write_contract()
        code, result = self.cli('--extract')
        self.assertEqual(code, 1)
        self.assertTrue(result['issues'][0].startswith('RAR_READ_FAILED'), result)
        self.assertFalse((self.root / 'legacy').exists())

    def test_compressed_rar5_with_local_rar_tool(self):
        # Uses a preinstalled CLI to create test bytes, never any archived code.
        rar = shutil.which('rar')
        if not rar and os.name == 'nt':
            candidate = Path('C:/Program Files/WinRAR/Rar.exe')
            rar = str(candidate) if candidate.is_file() else None
        if not rar:
            self.skipTest('RAR writer unavailable; stored RAR3 cases still run')
        for path, data in PAYLOADS.items():
            target = self.root / 'bazi' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        result = subprocess.run([rar, 'a', '-ma5', '-m3', '-idq', '-r', 'compressed.rar', 'bazi'],
                                cwd=self.root, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        # unrar is intentionally installed outside the archive/environment.
        unrar = Path(rar).with_name('UnRAR.exe' if os.name == 'nt' else 'unrar')
        import rarfile
        previous = rarfile.UNRAR_TOOL
        try:
            rarfile.UNRAR_TOOL = str(unrar)
            data, listing = v.archive_payloads((self.root / 'compressed.rar').read_bytes(), EXPECTED)
        finally:
            rarfile.UNRAR_TOOL = previous
        self.assertEqual(data, PAYLOADS)
        self.assertGreaterEqual(len(listing), 2)


if __name__ == '__main__':
    unittest.main()
