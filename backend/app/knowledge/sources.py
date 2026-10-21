"""Soft source links: a book key + a page (or DOCX paragraph) + an anchor text.

The books are not in git and each machine has its own copies, so a source never names a row
id or a revision (those differ per machine and change with every OCR correction). It names a
stable book key from ``data/books.json``, the page it was found on, and the words to look for.
``resolve`` turns it into a page of THIS machine's published library, visible to the caller:

1. the book: a published version whose file sha256 is listed for the key, else one whose title
   matches one of the key's titles;
2. the page: the hinted page if the anchor is on it, else the nearest page that has it
   (``exact`` / ``nearby`` within 2 pages / ``search`` anywhere), so another edition or a page
   offset still lands on the right text;
3. the result: book title, physical page, printed page label, an excerpt around the anchor and
   the viewer URL with the anchor highlighted (``/pages/<revision>?from=&to=``).
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..documents.catalog import visibility_clause

BOOKS = Path(__file__).parent / 'data' / 'books.json'
NEARBY = 2
EXCERPT = 160


@lru_cache(maxsize=4)
def registry(path: Path = BOOKS) -> dict[str, dict]:
    return {b['key']: b for b in json.loads(path.read_text(encoding='utf-8'))['books']}


def fold_keep(value: str) -> str:
    """Lower case without diacritics, one output character per input character (đ→d), so an
    index in the folded text is the same index in the original."""
    out = []
    for ch in value:
        base = unicodedata.normalize('NFD', ch.replace('đ', 'd').replace('Đ', 'D'))
        base = ''.join(c for c in base if unicodedata.category(c) != 'Mn') or ch
        out.append(base[0].lower() if len(base) >= 1 else ch)
    return ''.join(out)


_WS = re.compile(r'\s+')


def _folded(value: str) -> tuple[str, list[int]]:
    """``value`` lower-cased without diacritics, and for each folded character the index of the
    character of ``value`` it came from; works whether ``value`` is NFC or decomposed."""
    chars, origin = [], []
    for i, ch in enumerate(value):
        for c in unicodedata.normalize('NFD', ch.replace('đ', 'd').replace('Đ', 'D')):
            if unicodedata.category(c) != 'Mn':
                chars.append(c.lower()[0])
                origin.append(i)
    return ''.join(chars), origin


def find(haystack: str, needle: str) -> tuple[int, int] | None:
    """[start, end) of ``needle`` in ``haystack``: exact (case-insensitive) first, then without
    diacritics; whitespace runs match any whitespace. Offsets index ``haystack`` as given."""
    needle = _WS.sub(' ', unicodedata.normalize('NFC', needle)).strip()
    if not needle:
        return None
    m = re.search(r'\s+'.join(re.escape(w) for w in needle.split(' ')), haystack, re.IGNORECASE)
    if m:
        return m.start(), m.end()
    folded, origin = _folded(haystack)
    m = re.search(r'\s+'.join(re.escape(_folded(w)[0]) for w in needle.split(' ')), folded)
    if m is None or m.start() == m.end():
        return None
    end = origin[m.end() - 1] + 1
    while end < len(haystack) and unicodedata.category(haystack[end]) == 'Mn':
        end += 1                                   # the last letter's own combining marks
    return origin[m.start()], end


def soft_link(ref: dict) -> str:
    """The API path that resolves ``ref`` when opened (the client prefixes its own host)."""
    query = {'book': ref['book'], 'q': ref['anchor']}
    if ref.get('page'):
        query['page'] = ref['page']
    if ref.get('para'):
        query['para'] = ref['para']
    return '/api/v1/sources/open?' + urlencode(query)


def _versions(conn: Connection, principal: Principal) -> list[dict]:
    """Published book versions of the active release that ``principal`` may read."""
    clause, params = visibility_clause(principal)
    return [dict(r) for r in conn.execute(text(
        'SELECT v.id AS version_id, m.generation_id, b.title, o.sha256'
        " FROM active_corpus a JOIN corpus_members m ON m.release_id = a.release_id"
        ' JOIN book_versions v ON v.id = m.book_version_id JOIN books b ON b.id = v.book_id'
        ' JOIN objects o ON o.id = v.object_id'
        f" WHERE a.slot = 'default' AND v.status = 'active' AND v.rights_status <> 'restricted'"
        f' AND b.deleted_at IS NULL AND {clause}'), params).mappings()]


def _match(entry: dict, versions: list[dict]) -> tuple[dict | None, str | None]:
    for v in versions:
        if v['sha256'] in entry.get('sha256', []):
            return v, 'sha256'
    wanted = {fold_keep(t).strip() for t in entry.get('titles', []) + [entry['title']]}
    for v in versions:
        title = fold_keep(v['title']).strip()
        if title in wanted or any(w and w in title for w in wanted):
            return v, 'title'
    return None, None


def _pages(conn: Connection, generation_id, around: int | None = None) -> list[dict]:
    window = ' AND p.physical_page_number BETWEEN :lo AND :hi' if around else ''
    return [dict(r) for r in conn.execute(text(
        'SELECT p.physical_page_number AS page, r.id AS revision_id, r.normalized_text,'
        ' r.printed_page_label FROM generation_pages gp JOIN pages p ON p.id = gp.page_id'
        ' JOIN page_revisions r ON r.id = gp.page_revision_id WHERE gp.generation_id = :g'
        + window + ' ORDER BY p.physical_page_number'),
        {'g': generation_id, 'lo': (around or 0) - NEARBY, 'hi': (around or 0) + NEARBY}).mappings()]


def _page_count(conn: Connection, generation_id) -> int:
    return conn.execute(text('SELECT count(*) FROM generation_pages WHERE generation_id = :g'),
                        {'g': generation_id}).scalar_one()


def _hint(entry: dict, ref: dict, conn: Connection, generation_id) -> int | None:
    if ref.get('page'):
        return int(ref['page'])
    if ref.get('para') and entry.get('paragraphs'):
        # DOCX: the paragraph's share of the document, as a page of the ingested copy
        count = _page_count(conn, generation_id)
        return max(1, round(int(ref['para']) / entry['paragraphs'] * count)) if count else None
    return None


def _excerpt(body: str, start: int, end: int) -> str:
    return (('…' if start > EXCERPT else '') + body[max(0, start - EXCERPT):end + EXCERPT]
            + ('…' if end + EXCERPT < len(body) else ''))


def unresolved(ref: dict, books: dict | None = None) -> dict:
    """What a source says without a library to look in: book, hinted page, anchor, soft link."""
    entry = (books or registry()).get(ref.get('book'))
    return {'book': ref.get('book'), 'title': entry['title'] if entry else None,
            'short': entry['short'] if entry else None, 'page_hint': ref.get('page'),
            'para': ref.get('para'), 'anchor': ref.get('anchor'), 'link': soft_link(ref),
            'matched': 'not_found'}


def resolve_many(conn: Connection, principal: Principal, refs: list[dict]) -> list[dict]:
    versions = _versions(conn, principal)
    return [resolve(conn, principal, ref, versions=versions) for ref in refs]


def resolve(conn: Connection, principal: Principal, ref: dict, books: dict | None = None,
            versions: list[dict] | None = None) -> dict:
    """``ref`` = {book, anchor, page?, para?} → where it is in this library (see module doc).
    ``conn`` must run as ``principal`` (row-level security)."""
    books = books or registry()
    entry = books.get(ref.get('book'))
    out = unresolved(ref, books)
    if entry is None:
        return {**out, 'reason': 'unknown book key'}
    version, matched_by = _match(entry, _versions(conn, principal) if versions is None else versions)
    if version is None:
        return {**out, 'reason': 'book not in this library (or not visible to you)'}
    out.update(matched_by=matched_by, library_title=version['title'])
    hint = _hint(entry, ref, conn, version['generation_id'])
    anchor = ref.get('anchor') or ''
    # the hinted page and its neighbours first; the whole book only when they miss
    g = version['generation_id']
    for load in ((lambda: _pages(conn, g, hint)) if hint else list, lambda: _pages(conn, g)):
        for page in sorted(load(), key=lambda p: (abs(p['page'] - (hint or 0)), p['page'])):
            span = find(page['normalized_text'], anchor)
            if span is None:
                continue
            distance = abs(page['page'] - hint) if hint else None
            start, end = span
            return {**out, 'matched': 'exact' if distance == 0 and ref.get('page') else
                    'nearby' if distance is not None and distance <= NEARBY else 'search',
                    'page': page['page'], 'printed_page': page['printed_page_label'],
                    'revision_id': str(page['revision_id']),
                    'url': f"/pages/{page['revision_id']}?from={start}&to={end}",
                    'excerpt': _excerpt(page['normalized_text'], start, end)}
    return {**out, 'reason': 'anchor not found in this copy'}
