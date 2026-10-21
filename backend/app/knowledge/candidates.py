"""``extract_candidates`` stage: draft assertions and book cases with exact evidence.

Book cases (T023): every chart :func:`cases.parse_charts` finds on the page
becomes a draft ``book_case`` revision (school from the scope), citing the chart
rows and the prose after it, with a ``CANDIDATE_CASE`` review item.

Assertions (T021, docs/05, docs/06):

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
corrected pages never duplicate a candidate.

Model proposals (``qwen-1``, RAG pilot): with a model configured, each parent
chunk is also read by Qwen, which returns up to four rule/definition sentences
*quoted verbatim*. A proposal is kept only if its sentence is found exactly
(whitespace-normalised) inside one source block of that parent; the found text
becomes the evidence span and the assertion statement — Qwen's paraphrase goes
only into the review item. Everything stays a draft for an expert to approve.
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
from .cases import book_case_key, parse_charts

EXTRACTOR_VERSION = 'heuristic-3'
MODEL_EXTRACTOR_VERSION = 'qwen-1'
PARENT_BATCH = 16
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


def locate(sentence: str, blocks: list[dict]) -> tuple[dict, int, int] | None:
    """(block, start, end) of ``sentence`` inside one block, whitespace-insensitive."""
    words = sentence.split()
    if len(words) < 4:
        return None
    pattern = re.compile(r'\s+'.join(re.escape(w) for w in words))
    for block in blocks:
        match = pattern.search(block['text'])
        if match:
            return block, match.start(), match.end()
    return None


class ExtractCandidatesStage:
    name = 'extract_candidates'

    def __init__(self, settings=None, client=None):
        self.settings = settings
        self._client = client

    def _llm(self):
        if self._client is None and self.settings is not None:
            from ..rag.llm import SyncLLM, config_from
            config = config_from(self.settings)
            self._client = SyncLLM(config) if config else None
        return self._client

    def units(self, ctx: JobContext) -> list[Unit]:
        return self._page_units(ctx) + self._parent_units(ctx)

    def _parent_units(self, ctx: JobContext) -> list[Unit]:
        """Batches of parents (Qwen calls run in parallel inside a unit, like summaries)."""
        llm = self._llm()
        if llm is None or not (ctx.pipeline_config.get('candidates') or {}).get('model', True):
            return []
        from ..rag.prompts import PROPOSER_PROMPT_VERSION
        with ctx.engine.connect() as conn:
            parents = conn.execute(text(
                "SELECT p.ordinal, p.content_hash FROM chunk_parents p"
                " JOIN schools s ON s.key = p.meta->>'school_key'"
                ' WHERE p.generation_id = :g ORDER BY p.ordinal'), {'g': ctx.generation_id}).all()
        units = []
        for start in range(0, len(parents), PARENT_BATCH):
            batch = parents[start:start + PARENT_BATCH]
            material = '|'.join(f'{o}:{h.strip()}' for o, h in batch)
            units.append(Unit(f'parents:{batch[0][0]}-{batch[-1][0]}', hashlib.sha256(
                f'{material}|{MODEL_EXTRACTOR_VERSION}|{PROPOSER_PROMPT_VERSION}|'
                f'{llm.config.model}'.encode()).hexdigest()))
        return units

    def _page_units(self, ctx: JobContext) -> list[Unit]:
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
        if unit.key.startswith('parents:'):
            return self._compute_parent(ctx, unit)
        _, kind, number, revision, school = unit.key.split(':')
        with ctx.engine.connect() as conn:
            page_blocks = conn.execute(text(
                "SELECT id, ordinal, kind, start_offset, end_offset, text, speaker_layer,"
                " coalesce((attributes->>'chart_row')::boolean, false) AS chart_row FROM blocks"
                " WHERE page_revision_id = :r AND NOT (attributes ? 'role') ORDER BY ordinal"),
                {'r': revision}).mappings().all()
        blocks = [b for b in page_blocks if b['kind'] == 'paragraph' and not b['chart_row']]
        by_ordinal = {b['ordinal']: b for b in page_blocks}
        charts = []
        for chart in parse_charts([dict(b) for b in page_blocks]):
            cited = chart.block_ordinals + chart.narrative_ordinals
            charts.append({'key': book_case_key(ctx.book_version_id, chart),
                           'payload': chart.payload(),
                           'narrative': ' '.join(chart.narrative_lines)[:4000],
                           'blocks': [{'id': str(by_ordinal[o]['id']),
                                       'start': by_ordinal[o]['start_offset'],
                                       'end': by_ordinal[o]['end_offset'],
                                       'speaker': by_ordinal[o]['speaker_layer']}
                                      for o in cited]})
        vocabulary = ctx.state['candidate_vocab'][school]
        proposals = []
        for block in blocks:
            for candidate in propose(block['text'], vocabulary):
                proposals.append({**asdict(candidate), 'block_id': str(block['id']),
                                  'offset': block['start_offset'],
                                  'speaker': block['speaker_layer']})
        proposals.sort(key=lambda p: -p['score'])
        return {'revision_id': revision, 'school_id': school, 'page': int(number),
                'candidates': proposals[:MAX_PER_PAGE], 'cases': charts}

    def _compute_parent(self, ctx: JobContext, unit: Unit) -> dict:
        from concurrent.futures import ThreadPoolExecutor

        from ..rag.llm import LLMError
        from ..rag.prompts import ProposedRules, proposer_messages
        first, last = map(int, unit.key.split(':', 1)[1].split('-'))
        with ctx.engine.connect() as conn:
            parents = conn.execute(text(
                "SELECT p.id, p.text, p.meta->>'header' AS header, s.id AS school"
                " FROM chunk_parents p JOIN schools s ON s.key = p.meta->>'school_key'"
                ' WHERE p.generation_id = :g AND p.ordinal BETWEEN :a AND :b ORDER BY p.ordinal'),
                {'g': ctx.generation_id, 'a': first, 'b': last}).mappings().all()
            blocks: dict[str, list[dict]] = {}
            for r in conn.execute(text(
                    'SELECT DISTINCT gc.parent_id, b.id, b.text, b.start_offset, b.speaker_layer,'
                    ' b.page_revision_id, pg.physical_page_number AS page FROM generation_chunks gc'
                    ' JOIN chunk_spans sp ON sp.chunk_id = gc.chunk_id'
                    ' JOIN blocks b ON b.id = sp.block_id'
                    ' JOIN page_revisions pr ON pr.id = b.page_revision_id'
                    ' JOIN pages pg ON pg.id = pr.page_id'
                    ' WHERE gc.generation_id = :g AND gc.parent_id = ANY(CAST(:p AS uuid[]))'),
                    {'g': ctx.generation_id, 'p': [str(p['id']) for p in parents]}).mappings():
                blocks.setdefault(str(r['parent_id']), []).append(dict(r))

        def propose_for(parent) -> list[dict]:
            try:
                proposed, _ = self._llm().structured(
                    proposer_messages(parent['header'] or '', parent['text']), ProposedRules, 900)
            except LLMError:
                return []
            found = []
            for rule in proposed.rules[:MAX_PER_PAGE]:
                hit = locate(rule.sentence, blocks.get(str(parent['id']), []))
                if hit is None:
                    continue                  # not verbatim in the source: dropped
                block, start, end = hit
                found.append({'kind': 'definition' if rule.kind.startswith('def') else 'rule',
                              'start': start, 'end': end,
                              'statement': ' '.join(block['text'][start:end].split()),
                              'mentions': rule.terms[:12], 'score': 0.0,
                              'block_id': str(block['id']), 'offset': block['start_offset'],
                              'speaker': block['speaker_layer'], 'paraphrase': rule.statement[:500],
                              'revision_id': str(block['page_revision_id']), 'page': block['page'],
                              'school_id': str(parent['school'])})
            return found

        workers = getattr(self.settings, 'rag_summary_concurrency', 4)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            candidates = [c for found in pool.map(propose_for, parents) for c in found]
        return {'school_id': None, 'candidates': candidates, 'cases': [], 'model': True}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        author = conn.execute(text('SELECT requested_by FROM ingestion_jobs WHERE id = :j'),
                              {'j': ctx.job_id}).scalar_one()
        created = 0
        for cand in result['candidates']:
            assertion = conn.execute(text(
                'INSERT INTO assertions (assertion_key, revision, school_id, statement, origin,'
                " author_id) VALUES (:k, 1, :s, :st, 'source_explicit', :a)"
                ' ON CONFLICT (assertion_key, revision) DO NOTHING RETURNING id'),
                {'k': _key(ctx.book_version_id, cand['statement']),
                 's': cand.get('school_id') or result['school_id'],
                 'st': cand['statement'], 'a': author}).scalar()
            if assertion is None:
                continue                      # proposed before (other run, page or revision)
            start, end = cand['offset'] + cand['start'], cand['offset'] + cand['end']
            revision_id = cand.get('revision_id') or result['revision_id']
            page = cand.get('page') or result['page']
            evidence = conn.execute(text(
                'INSERT INTO evidence_spans (book_version_id, page_revision_id, block_id,'
                ' start_offset, end_offset, quote_hash, speaker_layer, origin)'
                ' SELECT :v, :r, :b, :s, :e, bazi_sha256_text(substr(normalized_text, :s + 1,'
                " :e - :s)), :sp, 'source_explicit' FROM page_revisions WHERE id = :r RETURNING id"),
                {'v': ctx.book_version_id, 'r': revision_id, 'b': cand['block_id'],
                 's': start, 'e': end, 'sp': cand['speaker']}).scalar_one()
            conn.execute(text("INSERT INTO assertion_sources (assertion_id, evidence_id, relation)"
                              " VALUES (:a, :e, 'states')"), {'a': assertion, 'e': evidence})
            conn.execute(text(
                'INSERT INTO review_items (generation_id, page_revision_id, entity_kind, entity_id,'
                " reason_code, severity, resolution) VALUES (:g, :r, 'assertion', :a,"
                " 'CANDIDATE_ASSERTION', 'info', CAST(:d AS jsonb))"),
                {'g': ctx.generation_id, 'r': revision_id, 'a': assertion,
                 'd': json.dumps({'kind': cand['kind'], 'mentions': cand['mentions'],
                                  'score': cand['score'], 'page': page,
                                  'extractor': MODEL_EXTRACTOR_VERSION if result.get('model')
                                  else EXTRACTOR_VERSION,
                                  'ai_paraphrase': cand.get('paraphrase')}, ensure_ascii=False)})
            created += 1
        cases = sum(self._case(conn, ctx, result, case, author) for case in result['cases'])
        conn.execute(text(
            'UPDATE ingestion_jobs SET counters = counters || jsonb_build_object('
            " 'candidates', coalesce((counters->>'candidates')::int, 0) + :n,"
            " 'case_candidates', coalesce((counters->>'case_candidates')::int, 0) + :c)"
            ' WHERE id = :j'), {'j': ctx.job_id, 'n': created, 'c': cases})
        return {'created': created, 'proposed': len(result['candidates']), 'cases': cases}

    def _case(self, conn: Connection, ctx: JobContext, result: dict, case: dict, author) -> int:
        case_id = conn.execute(text(
            "INSERT INTO cases (case_key, origin, visibility) VALUES (:k, 'book_case', 'library')"
            ' ON CONFLICT (case_key) DO NOTHING RETURNING id'), {'k': case['key']}).scalar()
        if case_id is None:
            return 0                          # found before (rerun, rebuild, same page)
        revision = conn.execute(text(
            'INSERT INTO case_revisions (case_id, revision, school_id, chart_payload, narrative,'
            ' quality) VALUES (:c, 1, :s, CAST(:p AS jsonb), :n, CAST(:q AS jsonb)) RETURNING id'),
            {'c': case_id, 's': result['school_id'],
             'p': json.dumps(case['payload'], ensure_ascii=False), 'n': case['narrative'],
             'q': json.dumps({'parser': EXTRACTOR_VERSION, 'page': result['page'],
                              'narrative_blocks': len(case['blocks']) - 1})}).scalar_one()
        for block in case['blocks']:
            evidence = conn.execute(text(
                'INSERT INTO evidence_spans (book_version_id, page_revision_id, block_id,'
                ' start_offset, end_offset, quote_hash, speaker_layer, origin)'
                ' SELECT :v, :r, :b, :s, :e, bazi_sha256_text(substr(normalized_text, :s + 1,'
                " :e - :s)), :sp, 'source_explicit' FROM page_revisions WHERE id = :r"
                ' RETURNING id'),
                {'v': ctx.book_version_id, 'r': result['revision_id'], 'b': block['id'],
                 's': block['start'], 'e': block['end'], 'sp': block['speaker']}).scalar_one()
            conn.execute(text('INSERT INTO case_sources (case_revision_id, evidence_id)'
                              ' VALUES (:c, :e) ON CONFLICT DO NOTHING'),
                         {'c': revision, 'e': evidence})
        conn.execute(text(
            'INSERT INTO review_items (generation_id, page_revision_id, entity_kind, entity_id,'
            " reason_code, severity, resolution) VALUES (:g, :r, 'case_revision', :c,"
            " 'CANDIDATE_CASE', 'info', CAST(:d AS jsonb))"),
            {'g': ctx.generation_id, 'r': result['revision_id'], 'c': revision,
             'd': json.dumps({'page': result['page'], 'extractor': EXTRACTOR_VERSION,
                              'pillars': case['payload']['source_text']}, ensure_ascii=False)})
        return 1
