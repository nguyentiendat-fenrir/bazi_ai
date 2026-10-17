"""Real file preflight tests: source preservation, routing and invalid inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from scripts import inspect_corpus as corpus


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pdf(self, name='source.pdf', encrypted=False):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        if encrypted:
            writer.encrypt('fixture')
        path = self.root / name
        writer.write(path)
        return path

    def docx(self, payload=None, extra=None):
        path = self.root / 'source.docx'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', payload or
                f'<w:document xmlns:w="{corpus.W[1:-1]}"><w:body><w:p><w:r>'
                '<w:t>Tiếng Việt</w:t></w:r></w:p><w:tbl/></w:body></w:document>')
            if extra:
                archive.writestr(*extra)
        return path

    def test_inventory_preserves_bytes_and_mtime_and_finds_duplicate(self):
        source = self.pdf()
        (self.root / 'copy.pdf').write_bytes(source.read_bytes())
        before = {p: (hashlib.sha256(p.read_bytes()).digest(), p.stat().st_mtime_ns)
                  for p in self.root.iterdir()}
        result = corpus.inspect_corpus(self.root)
        self.assertEqual(result['status'], 'INSPECTED')
        self.assertEqual(result['pdf_pages'], 2)
        self.assertEqual(result['files'][1]['duplicate_of'], 'copy.pdf')
        for path, state in before.items():
            self.assertEqual(state, (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns))
        self.assertEqual(set(self.root.iterdir()), set(before))

    def test_blank_page_is_review_candidate_not_automatic_ocr(self):
        record = corpus.inspect_file(self.pdf())
        self.assertEqual(record['review_pages'], [1])
        self.assertEqual(record['publication'], 'not_approved')
        self.assertEqual(record['route'], 'native_then_page_review')
        self.assertNotIn('samples', record)

    def test_native_text_page_and_opt_in_preview(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=500, height=500)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(b'BT /F1 12 Tf 10 100 Td (' + b'Native text ' * 20 + b') Tj ET')
        page[NameObject('/Contents')] = writer._add_object(content)
        path = self.root / 'text.pdf'
        writer.write(path)
        record = corpus.inspect_file(path, 25)
        self.assertGreater(record['text_chars'], 100)
        self.assertEqual(len(record['samples'][0]['preview']), 25)

    def test_encrypted_and_corrupt_files_fail_without_hiding_valid_input(self):
        self.pdf(encrypted=True)
        (self.root / 'broken.pdf').write_bytes(b'broken')
        (self.root / 'case.md').write_text('# Case', encoding='utf-8')
        result = corpus.inspect_corpus(self.root)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['file_count'], 1)
        self.assertEqual(len(result['errors']), 2)
        self.assertIn('PASSWORD_REQUIRED', [e['code'] for e in result['errors']])

    def test_docx_anchors_tables_and_external_links_never_fetched(self):
        path = self.docx(extra=('word/_rels/document.xml.rels',
            '<Relationships><Relationship TargetMode="External" Target="https://example.invalid"/></Relationships>'))
        record = corpus.inspect_file(path)
        self.assertEqual(record['paragraph_count'], 1)
        self.assertEqual(record['table_count'], 1)
        self.assertEqual(record['external_relationships'], 1)
        self.assertNotIn('page_count', record)
        self.assertNotIn('preview', record)

    def test_docx_entity_and_embedded_payload_rejected(self):
        path = self.docx(payload='<!DOCTYPE x [<!ENTITY a "expansion">]><x>&a;</x>')
        with self.assertRaisesRegex(ValueError, 'DOCX_UNSAFE_XML'):
            corpus.inspect_file(path)
        path = self.docx(extra=('word/embeddings/payload.bin', b'payload'))
        with self.assertRaisesRegex(ValueError, 'DOCX_ACTIVE_CONTENT'):
            corpus.inspect_file(path)

    def test_limits_enforced_before_xml_parse(self):
        path = self.docx()
        with patch.object(corpus, 'MAX_XML_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'DOCX_XML_LIMIT'):
                corpus.inspect_file(path)
        with patch.object(corpus, 'MAX_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'FILE_SIZE_LIMIT'):
                corpus.inspect_file(path)

    def test_markdown_is_not_promoted_to_book_or_gold(self):
        path = self.root / 'notes.md'
        path.write_text('# Phân tích\nDụng thần', encoding='utf-8')
        record = corpus.inspect_file(path)
        self.assertEqual(record['source_role'], 'derived_unreviewed')
        self.assertEqual(record['publication'], 'not_approved')

    def test_empty_missing_and_unsupported_inputs_are_distinct(self):
        self.assertEqual(corpus.inspect_corpus(self.root)['status'], 'EMPTY')
        self.assertEqual(corpus.inspect_corpus(self.root / 'missing')['status'], 'FAILED')
        (self.root / 'source.rar').write_bytes(b'not supported')
        self.assertEqual(corpus.inspect_corpus(self.root)['errors'][0]['code'], 'UNSUPPORTED_FORMAT')

    def test_cli_returns_nonzero_with_machine_readable_error(self):
        result = subprocess.run([sys.executable, 'scripts/dev', 'inspect-books', str(self.root / 'missing')],
                                cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'FAILED')
