"""Turn the glossary's sources into soft links and check them against the books on this machine.

A source in ``glossary_v1.json`` is ``{book, page | para, anchor, verified}``: the book key of
``backend/app/knowledge/data/books.json``, the PDF page (1-based, pdfium order) or the DOCX
paragraph (non-empty paragraphs, 1-based), and the words of the term as printed there. The
books are not in git; this script reads them from a folder (default ``inputs/books``), finding
each file by sha256 and else by title, so it runs the same on any machine that has the books.

    python scripts/glossary_sources.py            # report only
    python scripts/glossary_sources.py --check    # exit 1 if a source is not on its page
    python scripts/glossary_sources.py --write    # convert old "TBCT tr.12" strings, fix pages
                                                  # off by one or two, drop unfindable ones

Converting looks for the concept's label or an alias on the cited page, then on the pages
within ±2; a source whose words are on neither is dropped. At most ``MAX_SOURCES`` stay.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
import zipfile
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.knowledge.glossary import GLOSSARY  # noqa: E402
from backend.app.knowledge.sources import BOOKS, find, fold_keep, registry  # noqa: E402

MAX_SOURCES = 6
NEARBY = 2
OLD = re.compile(r'^(?:(?P<short>[A-Z]+) tr\.(?P<page>\d+)|docx¶(?P<para>\d+))$')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def locate(books: dict[str, dict], folder: Path) -> dict[str, tuple[Path, str]]:
    """book key → (file, 'sha256' | 'title')."""
    files = [p for p in folder.iterdir() if p.suffix.lower() in ('.pdf', '.docx')]
    digests = {sha256(p): p for p in files}
    found = {}
    for key, entry in books.items():
        hit = next((digests[d] for d in entry.get('sha256', []) if d in digests), None)
        if hit:
            found[key] = (hit, 'sha256')
            continue
        titles = [fold_keep(t).strip() for t in entry.get('titles', []) + [entry['title']]]
        for p in files:
            name = fold_keep(p.stem).strip()
            if p.suffix.lower() == '.' + entry['kind'] and any(t and (t in name or name in t) for t in titles):
                found[key] = (p, 'title')
                break
    return found


def pdf_pages(path: Path) -> list[str]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(path))
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        body = ElementTree.fromstring(z.read('word/document.xml')).find(W + 'body')
    out = []
    for p in body.iter(W + 'p'):
        line = ''.join(t.text or '' for t in p.iter(W + 't')).strip()
        if line:
            out.append(line)
    return out


def units(path: Path, kind: str) -> list[str]:
    """Index 0 is page/paragraph 1."""
    return pdf_pages(path) if kind == 'pdf' else docx_paragraphs(path)


def words(concept: dict) -> list[str]:
    """The concept's names, longest first (a longer name is a more telling anchor)."""
    names = [concept['label']] + list(concept.get('aliases') or [])
    if concept.get('han'):
        names.append(concept['han'])
    seen, out = set(), []
    for n in sorted(names, key=len, reverse=True):
        if n and fold_keep(n) not in seen and len(n.strip()) >= 2:
            seen.add(fold_keep(n))
            out.append(n.strip())
    return out


def place(texts: list[str], at: int, names: list[str]) -> tuple[int, str, str] | None:
    """(unit, anchor as printed, 'exact' | 'nearby') for the first name found at ``at`` or near."""
    for distance in range(NEARBY + 1):
        for unit in sorted({at - distance, at + distance}):
            if not 1 <= unit <= len(texts):
                continue
            for name in names:
                span = find(texts[unit - 1], name)
                if span:
                    anchor = unicodedata.normalize('NFC', re.sub(r'\s+', ' ', texts[unit - 1][span[0]:span[1]]))
                    return unit, anchor, 'exact' if distance == 0 else 'nearby'
    return None


def convert(concept: dict, books: dict, short: dict, texts: dict) -> tuple[list[dict], Counter]:
    tally, out, seen = Counter(), [], set()
    for src in concept['sources']:
        if isinstance(src, dict):
            key, at = src['book'], src.get('page') or src.get('para')
            names = [src['anchor']] + words(concept)
        else:
            m = OLD.match(src.strip())
            if not m:
                tally['unreadable'] += 1
                continue
            key = 'manh_phai_luoc_dich' if m['para'] else short.get(m['short'])
            at, names = int(m['page'] or m['para']), words(concept)
        if key not in texts:
            tally['book missing here'] += 1
            if isinstance(src, dict):
                out.append(src)                        # keep: another machine may have it
            continue
        hit = place(texts[key], at, names)
        if hit is None:
            tally['dropped (words not on page)'] += 1
            continue
        unit, anchor, verified = hit
        tally[verified] += 1
        if isinstance(src, dict) and verified == 'exact':
            verified = src.get('verified', verified)  # 'nearby' keeps saying the page was moved
        field = 'para' if books[key]['kind'] == 'docx' else 'page'
        if (key, unit) in seen:
            continue
        seen.add((key, unit))
        out.append({'book': key, field: unit, 'anchor': anchor, 'verified': verified})
    return out[:MAX_SOURCES], tally


def dump(glossary: dict) -> str:
    """Indented like the rest of the file, but one source per line."""
    lines = {}
    for concept in glossary['concepts']:
        for i, src in enumerate(concept['sources']):
            token = f'@@source{len(lines)}@@'
            lines[f'"{token}"'] = json.dumps(src, ensure_ascii=False)
            concept['sources'][i] = token
    out = json.dumps(glossary, ensure_ascii=False, indent=1)
    return re.sub(r'"@@source\d+@@"', lambda m: lines[m.group(0)], out) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--books', type=Path, default=ROOT / 'inputs' / 'books')
    parser.add_argument('--glossary', type=Path, default=GLOSSARY)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='exit 1 unless every source is on its page')
    mode.add_argument('--write', action='store_true', help='rewrite the glossary with converted sources')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')

    books = registry(BOOKS)
    short = {b['short']: k for k, b in books.items()}
    located = locate(books, args.books) if args.books.is_dir() else {}
    for key, entry in books.items():
        path, how = located.get(key, (None, None))
        print(f"{entry['short']:5} {entry['title']}: " + (f'{path.name} (by {how})' if path else 'NOT FOUND'))
    texts = {key: units(path, books[key]['kind']) for key, (path, _) in located.items()}

    glossary = json.loads(args.glossary.read_text(encoding='utf-8'))
    total = Counter()
    for concept in glossary['concepts']:
        concept['sources'], tally = convert(concept, books, short, texts)
        total.update(tally)
    print(', '.join(f'{k}: {v}' for k, v in sorted(total.items())))

    if args.write:
        args.glossary.write_text(dump(glossary), encoding='utf-8')
        print(f'written {args.glossary}')
    if args.check:
        bad = total['nearby'] + total['dropped (words not on page)'] + total['unreadable']
        return 1 if bad else 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
