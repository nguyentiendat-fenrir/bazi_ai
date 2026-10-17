"""``extract_candidates`` stage: draft assertions with exact evidence (docs/05, docs/06).

Deterministic proposals, no model and no approval: a sentence becomes a draft
assertion when it reads like a general rule (a condition, a consequence and at
least two domain terms) or a definition of a domain term. Sentences about one
particular chart (a Can-Chi pillar pair, a year) are left to case extraction,
and each page offers at most a few, best-scored first, so reviewers see
proposals worth their time. Only pages whose school a reviewer approved are read
(the assertion's school comes from that scope). Every candidate carries an
evidence span on the exact revision text, the block's speaker layer, origin
``source_explicit`` and an ``info`` review item explaining why it was proposed.
Keys derive from the version and the folded sentence, so re-runs, rebuilds and
corrected pages never duplicate a candidate. A model-backed extractor can
replace :func:`propose` later (T038) behind the same stage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..documents.text import fold
from ..ingestion.worker import JobContext, Unit

EXTRACTOR_VERSION = 'heuristic-2'
MAX_PER_PAGE = 4
# Matching is on lower-case NFC text with diacritics: folding would merge "ắt" (then)
# with the stem "Ất", "tài" (wealth) with "tại" (at), "thể" with "thế".
STEMS = ('giáp', 'ất', 'bính', 'đinh', 'mậu', 'kỷ', 'kỉ', 'canh', 'tân', 'nhâm', 'quý')
BRANCHES = ('tý', 'tí', 'sửu', 'dần', 'mão', 'thìn', 'tỵ', 'tị', 'ngọ', 'mùi', 'thân', 'dậu',
            'tuất', 'hợi')
DOMAIN = (
    STEMS + BRANCHES + ('mộc', 'hỏa', 'hoả', 'thổ', 'kim', 'thủy', 'thuỷ') +
    ('tỷ kiên', 'tỉ kiên', 'kiếp tài', 'thực thần', 'thương quan', 'chính tài', 'thiên tài',
     'chính quan', 'thất sát', 'chính ấn', 'thiên ấn', 'kiêu thần', 'dụng thần', 'hỷ thần',
     'hỉ thần', 'kỵ thần', 'kị thần', 'nhật chủ', 'nhật can', 'nguyệt lệnh', 'cách cục',
     'đại vận', 'lưu niên', 'tam hợp', 'lục hợp', 'lục xung', 'tương sinh', 'tương khắc',
     'thân vượng', 'thân nhược', 'kình dương', 'dương nhận', 'trường sinh', 'thiên can',
     'địa chi', 'ngũ hành', 'tố công', 'ứng kỳ', 'khách chủ', 'thể dụng', 'tài tinh',
     'quan tinh', 'ấn tinh', 'lộc', 'tài', 'ấn', 'sát', 'kiếp', 'kiêu', 'khố', 'mộ'))
CONDITION = re.compile(r'\b(nếu|khi|gặp|hễ|phạm)\b')
CONSEQUENCE = re.compile(r'\b(thì|ắt|tất|sẽ)\b')
OUTCOME = re.compile(r'\b(quý|tiện|phú|bần|thọ|yểu|cát|hung|giàu|nghèo|vượng|nhược|thành cách|'
                     r'phá cách|bại|lợi|tốt|xấu|chủ về|đắc dụng|vô dụng|hữu dụng)\b')
DEFINITION = re.compile(r'^\s*([^,;:.?!"“”()]{2,40}?)\s+(là|gọi là|tức là|được gọi là|nghĩa là)\s+')
STOP_SUBJECT = re.compile(r'^(đây|đó|điều|năm|vận|ngày|tháng|giờ|ta|tôi|người|cái|lúc|như|vì|'
                          r'nhưng|nên|còn|và|hoặc|tức|thật|đúng|chỉ|cũng|mỗi|một|các|những|này)\b')
PILLAR = re.compile(r'\b(' + '|'.join(STEMS) + r')\s+(' + '|'.join(BRANCHES) + r')\b')
YEAR = re.compile(r'\b(1[89]|20)\d\d\b')
_SENTENCE_END = re.compile(r'[.!?…;]+')


@dataclass
class Candidate:
    kind: str            # rule | definition
    start: int           # offsets inside the block text
    end: int
    statement: str       # whitespace-normalised quote
    mentions: list[str]
    score: float


def sentences(block_text: str) -> list[tuple[int, int]]:
    """Sentence spans of a block, trimmed of surrounding whitespace."""
    spans, start = [], 0
    for match in _SENTENCE_END.finditer(block_text):
        spans.append((start, match.end()))
        start = match.end()
    spans.append((start, len(block_text)))
    trimmed = []
    for s, e in spans:
        while s < e and block_text[s].isspace():
            s += 1
        while e > s and block_text[e - 1].isspace():
            e -= 1
        if e > s:
            trimmed.append((s, e))
    return trimmed


def _mentions(lowered: str, vocabulary: tuple[str, ...]) -> list[str]:
    return sorted({term for term in vocabulary if re.search(rf'\b{re.escape(term)}\b', lowered)})


def propose(block_text: str, vocabulary: tuple[str, ...] = DOMAIN) -> list[Candidate]:
    found = []
    for start, end in sentences(block_text):
        statement = ' '.join(block_text[start:end].split())
        lowered = statement.lower()
        words = len(lowered.split())
        if not 6 <= words <= 70 or YEAR.search(lowered):
            continue
        pillars = len(PILLAR.findall(lowered))
        mentions = _mentions(lowered, vocabulary)
        definition = DEFINITION.match(lowered)
        if definition and pillars == 0:
            subject = definition.group(1)
            if (len(subject.split()) <= 4 and not STOP_SUBJECT.match(subject)
                    and _mentions(subject, vocabulary)):
                found.append(Candidate('definition', start, end, statement, mentions,
                                       2 + len(mentions)))
                continue
        if (pillars <= 1 and CONDITION.search(lowered) and CONSEQUENCE.search(lowered)
                and len(mentions) >= 2 and OUTCOME.search(lowered)):
            found.append(Candidate('rule', start, end, statement, mentions, 1 + len(mentions)))
    return found


def _key(version_id, statement: str) -> str:
    digest = hashlib.sha256(f'{version_id}|{fold(statement)}'.encode()).hexdigest()
    return f'cand.{digest[:24]}'


def _vocabulary(conn: Connection, school_id) -> tuple[str, ...]:
    """Built-in domain words plus the approved aliases of the school and the root."""
    extra = conn.execute(text(
        "SELECT DISTINCT lower(t.form_nfc) FROM terms t JOIN concepts c ON c.id = t.concept_id"
        " JOIN schools s ON s.id = c.school_id WHERE t.state = 'approved' AND t.language = 'vi'"
        " AND (c.school_id = :s OR s.parent_id IS NULL)"), {'s': school_id}).scalars().all()
    return tuple(sorted(set(DOMAIN) | {e for e in extra if 2 <= len(e) <= 40}))


class ExtractCandidatesStage:
    name = 'extract_candidates'

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            pages = conn.execute(text(
                'SELECT p.page_kind, p.physical_page_number, gp.page_revision_id, ('
                ' SELECT sc.school_id FROM school_scopes sc WHERE sc.book_version_id = :v'
                " AND sc.state = 'approved' AND (sc.first_page IS NULL OR"
                ' p.physical_page_number BETWEEN sc.first_page AND sc.last_page)'
                ' ORDER BY sc.first_page IS NULL, sc.last_page - sc.first_page LIMIT 1) AS school'
                ' FROM generation_pages gp JOIN pages p ON p.id = gp.page_id'
                ' JOIN page_revisions r ON r.id = gp.page_revision_id'
                " WHERE gp.generation_id = :g AND r.state <> 'excluded'"
                ' ORDER BY p.page_kind, p.physical_page_number'),
                {'g': ctx.generation_id, 'v': ctx.book_version_id}).all()
            vocab = {}
            for school in {row[3] for row in pages if row[3]}:
                vocab[str(school)] = _vocabulary(conn, school)
        ctx.state['candidate_vocab'] = vocab
        units = []
        for kind, number, revision, school in pages:
            if school is None:
                continue                      # no reviewed school for this page: no claims
            words = hashlib.sha256('|'.join(vocab[str(school)]).encode()).hexdigest()
            digest = hashlib.sha256(f'{revision}|{school}|{EXTRACTOR_VERSION}|{words}'
                                    .encode()).hexdigest()
            units.append(Unit(f'page:{kind}:{number}:{revision}:{school}', digest))
        return units

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        _, kind, number, revision, school = unit.key.split(':')
        with ctx.engine.connect() as conn:
            blocks = conn.execute(text(
                "SELECT id, ordinal, start_offset, text, speaker_layer FROM blocks"
                " WHERE page_revision_id = :r AND kind = 'paragraph'"
                " AND NOT (attributes ? 'role') AND NOT coalesce((attributes->>'chart_row')::boolean,"
                ' false) ORDER BY ordinal'), {'r': revision}).mappings().all()
        vocabulary = ctx.state['candidate_vocab'][school]
        proposals = []
        for block in blocks:
            for candidate in propose(block['text'], vocabulary):
                proposals.append({**asdict(candidate), 'block_id': str(block['id']),
                                  'offset': block['start_offset'],
                                  'speaker': block['speaker_layer']})
        proposals.sort(key=lambda p: -p['score'])
        return {'revision_id': revision, 'school_id': school, 'page': int(number),
                'candidates': proposals[:MAX_PER_PAGE]}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        author = conn.execute(text('SELECT requested_by FROM ingestion_jobs WHERE id = :j'),
                              {'j': ctx.job_id}).scalar_one()
        created = 0
        for cand in result['candidates']:
            assertion = conn.execute(text(
                'INSERT INTO assertions (assertion_key, revision, school_id, statement, origin,'
                " author_id) VALUES (:k, 1, :s, :st, 'source_explicit', :a)"
                ' ON CONFLICT (assertion_key, revision) DO NOTHING RETURNING id'),
                {'k': _key(ctx.book_version_id, cand['statement']), 's': result['school_id'],
                 'st': cand['statement'], 'a': author}).scalar()
            if assertion is None:
                continue                      # proposed before (other run, page or revision)
            start, end = cand['offset'] + cand['start'], cand['offset'] + cand['end']
            evidence = conn.execute(text(
                'INSERT INTO evidence_spans (book_version_id, page_revision_id, block_id,'
                ' start_offset, end_offset, quote_hash, speaker_layer, origin)'
                ' SELECT :v, :r, :b, :s, :e, bazi_sha256_text(substr(normalized_text, :s + 1,'
                " :e - :s)), :sp, 'source_explicit' FROM page_revisions WHERE id = :r RETURNING id"),
                {'v': ctx.book_version_id, 'r': result['revision_id'], 'b': cand['block_id'],
                 's': start, 'e': end, 'sp': cand['speaker']}).scalar_one()
            conn.execute(text("INSERT INTO assertion_sources (assertion_id, evidence_id, relation)"
                              " VALUES (:a, :e, 'states')"), {'a': assertion, 'e': evidence})
            conn.execute(text(
                'INSERT INTO review_items (generation_id, page_revision_id, entity_kind, entity_id,'
                " reason_code, severity, resolution) VALUES (:g, :r, 'assertion', :a,"
                " 'CANDIDATE_ASSERTION', 'info', CAST(:d AS jsonb))"),
                {'g': ctx.generation_id, 'r': result['revision_id'], 'a': assertion,
                 'd': json.dumps({'kind': cand['kind'], 'mentions': cand['mentions'],
                                  'score': cand['score'], 'extractor': EXTRACTOR_VERSION,
                                  'page': result['page']})})
            created += 1
        conn.execute(text(
            'UPDATE ingestion_jobs SET counters = counters || jsonb_build_object('
            " 'candidates', coalesce((counters->>'candidates')::int, 0) + :n) WHERE id = :j"),
            {'j': ctx.job_id, 'n': created})
        return {'created': created, 'proposed': len(result['candidates'])}
