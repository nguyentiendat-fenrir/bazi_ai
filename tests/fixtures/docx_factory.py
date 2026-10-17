"""Minimal valid DOCX packages for tests (headings, paragraphs, tables, content controls)."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.document.main+xml"/></Types>')
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def paragraph(text: str, style: str | None = None) -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ''
    return f'<w:p>{props}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def table(rows: list[list[str]]) -> str:
    body = ''.join('<w:tr>' + ''.join(f'<w:tc>{paragraph(cell)}</w:tc>' for cell in row) + '</w:tr>'
                   for row in rows)
    return f'<w:tbl>{body}</w:tbl>'


def content_control(inner: str) -> str:
    return f'<w:sdt><w:sdtContent>{inner}</w:sdtContent></w:sdt>'


def write_docx(path: Path, body: str, extra: dict | None = None) -> Path:
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document {NS}><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', CONTENT_TYPES)
        archive.writestr('_rels/.rels', RELS)
        archive.writestr('word/document.xml', document)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return path


def sample_body(chapter_suffix: str = '') -> str:
    return ''.join([
        paragraph('LỜI GIỚI THIỆU', 'Title'),
        paragraph('Đoạn mở đầu nói về Manh phái và cách dùng sách này.'),
        paragraph('I. Khách – Chủ' + chapter_suffix, 'Heading1'),
        paragraph('Khách và Chủ được xét theo nhiều cấp độ khác nhau trong lá số.'),
        table([['Thiên Can', 'Giáp', 'Ất'], ['Lộc', 'Dần', 'Mão']]),
        content_control(paragraph('Đoạn nằm trong content control vẫn được đọc.')),
        paragraph('II. Thể – Dụng', 'Heading1'),
        paragraph('Dụng ở đây khác với Dụng Thần của Tử Bình.'),
    ])
