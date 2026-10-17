"""Upload format checks before anything is stored (docs/05 validate, docs/12 sandbox).

The type comes from magic bytes and must agree with the extension when one is
given. DOCX is a zip: entry count, total expansion, duplicate or path-like
names, macros, embedded objects and non-hyperlink external relationships are
refused. Deep parsing happens later in the sandboxed worker, not in the API.
"""
from __future__ import annotations

from typing import BinaryIO
import zipfile

PDF = 'application/pdf'
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
EXTENSIONS = {'.pdf': PDF, '.docx': DOCX}
MAX_DOCX_ENTRIES = 2000
MAX_DOCX_EXPANDED = 1024 ** 3
MAX_RELS_BYTES = 2 * 1024 * 1024
HYPERLINK_REL = 'relationships/hyperlink'


class FormatRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def sniff(head: bytes, filename: str) -> str:
    if head.startswith(b'%PDF-'):
        detected = PDF
    elif head.startswith(b'PK\x03\x04'):
        detected = DOCX  # confirmed by validate_docx; other zip kinds fail there
    else:
        raise FormatRejected('UNSUPPORTED_TYPE', 'Only PDF and DOCX files are accepted')
    extension = '.' + filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if extension and EXTENSIONS.get(extension) != detected:
        raise FormatRejected('UNSUPPORTED_TYPE', 'File extension does not match its content')
    return detected


def validate_docx(stream: BinaryIO) -> None:
    try:
        archive = zipfile.ZipFile(stream)
    except zipfile.BadZipFile:
        raise FormatRejected('DOCX_INVALID', 'Not a readable DOCX archive') from None
    with archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if len(entries) > MAX_DOCX_ENTRIES or sum(e.file_size for e in entries) > MAX_DOCX_EXPANDED:
            raise FormatRejected('DOCX_EXPANSION_LIMIT', 'DOCX expands beyond the allowed size')
        if len(set(names)) != len(names):
            raise FormatRejected('DOCX_INVALID', 'DOCX has duplicate entries')
        if any(n.startswith('/') or '..' in n.split('/') or '\\' in n for n in names):
            raise FormatRejected('DOCX_INVALID', 'DOCX has path-like entry names')
        if 'word/document.xml' not in names:
            raise FormatRejected('DOCX_INVALID', 'Archive is not a Word document')
        lowered = [n.lower() for n in names]
        if any('vbaproject' in n or '/embeddings/' in n or n.endswith(('.bin', '.exe'))
               for n in lowered):
            raise FormatRejected('DOCX_ACTIVE_CONTENT', 'DOCX contains macros or embedded objects')
        for entry in entries:
            if not entry.filename.endswith('.rels'):
                continue
            if entry.file_size > MAX_RELS_BYTES:
                raise FormatRejected('DOCX_INVALID', 'DOCX relationship part is too large')
            rels = archive.read(entry).decode('utf-8', 'replace')
            if '<!DOCTYPE' in rels.upper() or '<!ENTITY' in rels.upper():
                raise FormatRejected('DOCX_INVALID', 'DOCX contains XML entity declarations')
            _check_external_relationships(rels)
    stream.seek(0)


def _check_external_relationships(rels: str) -> None:
    import re
    for match in re.finditer(r'<Relationship\b[^>]*>', rels):
        tag = match.group(0)
        if 'TargetMode="External"' in tag and HYPERLINK_REL not in tag:
            # Hyperlinks are inert text; anything else could be fetched by a renderer.
            raise FormatRejected('DOCX_EXTERNAL_RELATIONSHIP',
                                 'DOCX references external resources')
