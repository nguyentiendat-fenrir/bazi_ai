"""Read-only local corpus inventory. This is preflight, not ingestion or OCR.

No model calls, publication, source edits or extracted-text files. JSON goes to
stdout; optional previews are explicitly requested and must stay local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

MAX_BYTES = 250 * 1024**2
MAX_XML_BYTES = 20 * 1024**2
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def preview(text: str, limit: int) -> dict:
    return {'preview': text[:limit]} if limit else {}


def inspect_pdf(path: Path, sample_chars: int) -> dict:
    from pypdf import PdfReader

    with path.open('rb') as stream:
        reader = PdfReader(stream)
        if reader.is_encrypted:
            raise ValueError('PASSWORD_REQUIRED')
        if len(reader.pages) > 3000:
            raise ValueError('PAGE_LIMIT')
        pages = []
        snippets = []
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ''
            chars = len(text.strip())
            replacements = text.count('\ufffd')
            # This is a text heuristic only: no layout, image-area or OCR verdict.
            pages.append({'page': number, 'chars': chars,
                          'replacement_chars': replacements,
                          'review_required': chars < 100 or replacements > 0})
            if sample_chars and number <= 3:
                snippets.append({'page': number, **preview(text, sample_chars)})
        return {'page_count': len(pages), 'text_chars': sum(p['chars'] for p in pages),
                'review_pages': [p['page'] for p in pages if p['review_required']],
                'pages': pages, 'route': 'native_then_page_review',
                'source_role': 'book_unreviewed',
                **({'samples': snippets} if sample_chars else {})}


def inspect_docx(path: Path, sample_chars: int) -> dict:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(e.file_size for e in entries) > 1024**3:
            raise ValueError('DOCX_EXPANSION_LIMIT')
        if len({e.filename for e in entries}) != len(entries):
            raise ValueError('DOCX_DUPLICATE_MEMBER')
        if any('vbaproject' in e.filename.lower() or '/embeddings/' in e.filename.lower()
               for e in entries):
            raise ValueError('DOCX_ACTIVE_CONTENT')

        def xml(name: str):
            entry = archive.getinfo(name)
            if entry.file_size > MAX_XML_BYTES:
                raise ValueError('DOCX_XML_LIMIT')
            payload = archive.read(entry)
            if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper() or b'\x00' in payload:
                raise ValueError('DOCX_UNSAFE_XML')
            return ET.fromstring(payload)

        external = 0
        for entry in entries:
            if entry.filename.endswith('.rels'):
                external += sum(r.attrib.get('TargetMode') == 'External'
                                for r in xml(entry.filename))
        document = xml('word/document.xml')
        paragraphs = [''.join(t.text or '' for t in p.iter(W + 't'))
                      for p in document.iter(W + 'p')]
        text = '\n'.join(paragraphs)
        return {'paragraph_count': len(paragraphs),
                'table_count': sum(1 for _ in document.iter(W + 'tbl')),
                'text_chars': len(text), 'external_relationships': external,
                'source_role': 'unclassified_draft',
                'route': 'classify_then_docx_anchors_and_canonical_render',
                **preview(text, sample_chars)}


def inspect_file(path: Path, sample_chars: int = 0) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('FILE_SIZE_LIMIT')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    base = {'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest,
            'publication': 'not_approved'}
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        details = inspect_pdf(path, sample_chars)
    elif suffix == '.docx':
        details = inspect_docx(path, sample_chars)
    elif suffix == '.md':
        text = path.read_text(encoding='utf-8-sig')
        details = {'text_chars': len(text), 'source_role': 'derived_unreviewed',
                   'route': 'hold_out_for_case_and_citation_review',
                   **preview(text, sample_chars)}
    else:
        raise ValueError('UNSUPPORTED_FORMAT')
    return {**base, **details}


def inspect_corpus(root: Path, sample_chars: int = 0) -> dict:
    if not root.is_dir() or root.is_symlink():
        return {'status': 'FAILED', 'files': [], 'errors': [{'code': 'INPUT_DIRECTORY_INVALID'}]}
    files, errors, seen = [], [], {}
    for path in sorted(root.rglob('*')):
        if path.name == '.gitkeep':
            continue
        if path.is_symlink() or any((root / p).is_symlink()
                                   for p in path.relative_to(root).parents):
            errors.append({'name': path.relative_to(root).as_posix(), 'code': 'SYMLINK_REJECTED'})
            continue
        if not path.is_file():
            continue
        try:
            record = inspect_file(path, sample_chars)
            record['name'] = path.relative_to(root).as_posix()
            if record['sha256'] in seen:
                record['duplicate_of'] = seen[record['sha256']]
            else:
                seen[record['sha256']] = record['name']
            files.append(record)
        except Exception as error:
            # Avoid logging parser exceptions containing document text or paths.
            code = str(error) if isinstance(error, ValueError) and str(error).isupper() else type(error).__name__
            errors.append({'name': path.relative_to(root).as_posix(), 'code': code})
    return {'status': 'FAILED' if errors else ('INSPECTED' if files else 'EMPTY'),
            'file_count': len(files), 'pdf_pages': sum(f.get('page_count', 0) for f in files),
            'limitations': 'Text preflight only; no OCR/layout validation or approved knowledge.',
            'files': files, 'errors': errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'inputs/books')
    parser.add_argument('--sample-chars', type=int, default=0, choices=range(0, 2001), metavar='0..2000')
    args = parser.parse_args(argv)
    result = inspect_corpus(args.directory, args.sample_chars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['status'] == 'FAILED' else 0


if __name__ == '__main__':
    sys.exit(main())
