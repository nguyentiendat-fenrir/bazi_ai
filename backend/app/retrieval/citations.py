"""Evidence bundles and citation resolution (docs/07 · Citation validation, T037).

A packed bundle is stored for its owner with the release and visibility epoch
it was built on; a model cites its handles (``E1``…), never page numbers.
Resolving a claim checks, for each handle:

* existence — the handle is in this owner's unexpired bundle, and its book
  version is still active, not ``restricted`` and readable by the principal
  (re-checked when the visibility epoch moved since the bundle was built);
* span — every span still lies inside its block on the immutable revision, the
  text is exactly what was handed over (hash), and a quoted string, if the claim
  gives one, occurs in it;
* support — a lexical heuristic: the share of the claim's content words found
  in the cited text. It flags ``insufficient_evidence``, it does not prove
  entailment; a model judge and the human gold come later (T038, T025).

A claim with any existence or span problem is ``invalid`` and must not be shown;
valid citations carry materialised evidence spans and a viewer locator
(physical and printed page, block box).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..documents.catalog import visibility_clause
from ..documents.text import fold, nfc
from .search import STOPWORDS

BUNDLE_TTL_HOURS = 24
SUPPORTED, WEAK = 0.5, 0.2
_WORD = re.compile(r'\w+', re.UNICODE)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def save_bundle(conn: Connection, principal: Principal, release_id, epoch: int, query: str,
                bundle: dict) -> str:
    groups = [{key: group[key] for key in (
        'evidence_id', 'book_id', 'book_title', 'book_version_id', 'edition_label', 'section_title',
        'speaker_layer', 'school_key', 'pages', 'printed_pages', 'spans', 'chunk_ids')}
        | {'excerpt_hash': _sha(group['excerpt'])} for group in bundle['groups']]
    return str(conn.execute(text(
        'INSERT INTO evidence_bundles (owner_id, corpus_release_id, visibility_epoch, query_hash,'
        " groups, expires_at) VALUES (:o, :r, :e, :q, CAST(:g AS jsonb),"
        ' now() + make_interval(hours => :ttl)) RETURNING id'),
        {'o': principal.user_id, 'r': release_id, 'e': epoch, 'q': _sha(fold(query)),
         'g': json.dumps(groups, ensure_ascii=False), 'ttl': BUNDLE_TTL_HOURS}).scalar_one())


def _words(value: str, accented: bool) -> set[str]:
    base = nfc(value).lower() if accented else fold(value)
    return {w for w in _WORD.findall(base) if fold(w) not in STOPWORDS and len(w) > 1}


# Numbers, years, URLs and code-like tokens ("sk-live-123"): a claim may only state the ones
# its sources contain. Word overlap cannot catch an invented detail inside a quoted sentence.
_DETAIL = re.compile(r'https?://\S+|[\w.-]*\d[\w.-]*', re.UNICODE)


def details(value: str) -> set[str]:
    return {d.strip('.-').lower() for d in _DETAIL.findall(nfc(value)) if d.strip('.-')}


def support(claim: str, source: str) -> float:
    """Share of the claim's content words in the source; with diacritics when the claim has
    them ("lắm" is not "làm", "to" is not "tố"), folded only for an accent-free claim."""
    accented = fold(claim) != nfc(claim).lower()
    wanted = _words(claim, accented)
    return round(len(wanted & _words(source, accented)) / len(wanted), 3) if wanted else 0.0


def _readable_versions(conn: Connection, principal: Principal, versions: list[str]) -> set[str]:
    visible, params = visibility_clause(principal)
    return {str(v) for v in conn.execute(text(
        'SELECT v.id FROM book_versions v JOIN books b ON b.id = v.book_id'
        " WHERE v.id = ANY(CAST(:ids AS uuid[])) AND v.status = 'active'"
        f" AND v.rights_status <> 'restricted' AND b.deleted_at IS NULL AND {visible}"),
        {**params, 'ids': versions}).scalars()}


def _span_rows(conn: Connection, spans: list[dict]) -> list[dict] | None:
    rows = []
    for span in spans:
        row = conn.execute(text(
            'SELECT substr(r.normalized_text, :s + 1, :e - :s) AS quote, b.bbox, b.speaker_layer,'
            ' r.printed_page_label FROM page_revisions r JOIN blocks b ON b.page_revision_id = r.id'
            ' WHERE r.id = :r AND b.id = :b AND b.start_offset <= :s AND b.end_offset >= :e'),
            {'r': span['page_revision_id'], 'b': span['block_id'], 's': span['start_offset'],
             'e': span['end_offset']}).mappings().first()
        if row is None:
            return None
        rows.append({**span, **dict(row)})
    return rows


def _materialise(conn: Connection, version_id, row: dict) -> str:
    existing = conn.execute(text(
        "SELECT id FROM evidence_spans WHERE page_revision_id = :r AND block_id = :b"
        " AND start_offset = :s AND end_offset = :e AND origin = 'source_explicit' LIMIT 1"),
        {'r': row['page_revision_id'], 'b': row['block_id'], 's': row['start_offset'],
         'e': row['end_offset']}).scalar()
    if existing:
        return str(existing)
    return str(conn.execute(text(
        'INSERT INTO evidence_spans (book_version_id, page_revision_id, block_id, start_offset,'
        ' end_offset, quote_hash, speaker_layer, origin) VALUES (:v, :r, :b, :s, :e,'
        " bazi_sha256_text(:q), :sp, 'source_explicit') RETURNING id"),
        {'v': version_id, 'r': row['page_revision_id'], 'b': row['block_id'],
         's': row['start_offset'], 'e': row['end_offset'], 'q': row['quote'],
         'sp': row['speaker_layer']}).scalar_one())


def resolve(conn: Connection, principal: Principal, bundle_id: uuid.UUID,
            claims: list[dict]) -> dict:
    bundle = conn.execute(text(
        'SELECT id, corpus_release_id, visibility_epoch, groups, expires_at FROM evidence_bundles'
        ' WHERE id = :b'), {'b': bundle_id}).mappings().first()
    if bundle is None:
        raise AppError(404, 'NOT_FOUND', 'Evidence bundle not found')
    if bundle['expires_at'] <= datetime.now(timezone.utc):
        raise AppError(410, 'BUNDLE_EXPIRED', 'The evidence bundle expired; search again')
    epoch = conn.execute(text("SELECT visibility_epoch FROM active_corpus WHERE slot = 'default'")
                         ).scalar()
    groups = {g['evidence_id']: g for g in bundle['groups']}
    readable = _readable_versions(conn, principal,
                                  sorted({g['book_version_id'] for g in groups.values()}))
    results = []
    for index, claim in enumerate(claims):
        problems, citations, scores, cited_texts = [], [], [], []
        for handle in dict.fromkeys(claim['evidence_ids']):
            group = groups.get(handle)
            if group is None:
                problems.append({'evidence_id': handle, 'code': 'UNKNOWN_EVIDENCE'})
                continue
            if group['book_version_id'] not in readable:
                problems.append({'evidence_id': handle, 'code': 'SOURCE_WITHDRAWN'})
                continue
            rows = _span_rows(conn, group['spans'])
            if rows is None:
                problems.append({'evidence_id': handle, 'code': 'SPAN_INVALID'})
                continue
            cited = '\n\n'.join(r['quote'] for r in rows)
            if _sha(cited) != group['excerpt_hash']:
                problems.append({'evidence_id': handle, 'code': 'SOURCE_CHANGED'})
                continue
            quote = claim.get('quote')
            if quote and ' '.join(nfc(quote).split()) not in ' '.join(cited.split()):
                problems.append({'evidence_id': handle, 'code': 'QUOTE_MISMATCH'})
                continue
            score = support(claim['text'], cited)
            scores.append(score)
            cited_texts.append(cited)
            citations.append({
                'evidence_id': handle,
                'evidence_span_ids': [_materialise(conn, group['book_version_id'], r)
                                      for r in rows],
                'book_id': group['book_id'], 'book_title': group['book_title'],
                'book_version_id': group['book_version_id'],
                'edition_label': group['edition_label'], 'section_title': group['section_title'],
                'speaker_layer': group['speaker_layer'], 'pages': group['pages'],
                'printed_pages': group['printed_pages'],
                'quote': quote or cited[:300], 'support': score,
                'viewer': [{'page_revision_id': r['page_revision_id'],
                            'physical_page_number': r['physical_page_number'],
                            'printed_page_label': r['printed_page_label'],
                            'start_offset': r['start_offset'], 'end_offset': r['end_offset'],
                            'bbox': r['bbox']} for r in rows]})
        invented = details(claim['text']) - details('\n'.join(cited_texts))
        if cited_texts and invented:
            problems.append({'evidence_id': claim['evidence_ids'][0], 'code': 'UNSUPPORTED_DETAIL'})
        if problems or not claim['evidence_ids']:
            status = 'invalid'
            citations = []
        elif max(scores) < WEAK:
            status = 'insufficient_evidence'
        else:
            status = 'supported' if max(scores) >= SUPPORTED else 'weak'
        results.append({'index': index, 'status': status, 'problems': problems,
                        'support': max(scores, default=0.0), 'citations': citations})
    return {'bundle_id': str(bundle['id']), 'release_id': str(bundle['corpus_release_id']),
            'epoch_changed': epoch != bundle['visibility_epoch'], 'claims': results}
