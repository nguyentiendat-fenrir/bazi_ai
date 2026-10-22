"""Definition curation: an outside model drafts concept definitions from published pages.

Steps (each resumable; a model answer is stored by a key over step, model, prompt version and
input, so a rerun never pays twice):

1. **discover** — every parent section of the active release that the curator may read is
   sent once; the model names the concepts it explains, mentions or illustrates, each with a
   verbatim quote. The code finds the quote in the section's pages (exact, else without
   diacritics) and stores an ``ai_inferred`` evidence span; offsets never come from the model.
2. **compose** — candidates are grouped by school and normalised name; the evidence file is
   the located quotes ("explains" first, one per near-identical text, so two editions of a
   book do not count twice) widened to their whole block. One call writes one definition with
   claims citing ``[E#]``; the code checks every cited label. The result is a draft revision of
   the concept (an existing concept of that school and name, else a new one), with its sources.
3. **review** — a second call (``CURATOR_REVIEW_MODEL`` or the same model) judges the
   definition against the cited evidence: pass / fix / fail with problems. It never approves;
   a review item waits for a person in Tri thức → Biên soạn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import logging
import re
import unicodedata

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..answering.glossary_index import _key as spelling_key
from ..auth.service import Principal
from ..core.db import transaction
from ..documents import catalog
from ..documents.text import fold, nfc
from ..rag.llm import LLMConfig, LLMError, SyncLLM
from . import curation_prompts as prompts
from . import ontology
from .sources import find

log = logging.getLogger('bazi.curation')
EVIDENCE_LIMIT = 8                 # quotes per definition
EVIDENCE_CHARS = 18_000            # ~5k tokens of evidence per compose call
UNIT_CHARS = 12_000                # a parent longer than this is read in slices
SCHOOL_LABELS = {'tu_binh': 'Tử Bình', 'manh_phai': 'Manh phái', 'tu_tru': 'Tứ Trụ (chung)'}
KIND_ORDER = {'explains': 0, 'example': 1, 'mentions': 2}


class BudgetExhausted(Exception):
    pass


def name_key(name: str) -> str:
    return spelling_key(name)


def slug(name: str) -> str:
    """ASCII key part for a new concept (ontology.KEY)."""
    ascii_ = unicodedata.normalize('NFKD', fold(name)).encode('ascii', 'ignore').decode()
    return (re.sub(r'[^a-z0-9]+', '_', ascii_.lower()).strip('_') or 'khai_niem')[:60]


def _hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()


def config_from(settings, review: bool = False) -> LLMConfig | None:
    if not settings.curator_llm_base_url or not settings.curator_llm_model:
        return None
    key = settings.curator_llm_api_key.get_secret_value() if settings.curator_llm_api_key else None
    model = (settings.curator_review_model or settings.curator_llm_model) if review \
        else settings.curator_llm_model
    return LLMConfig(settings.curator_llm_base_url.rstrip('/'), model, settings.curator_timeout,
                     key, vllm=False, reasoning_effort=settings.curator_reasoning_effort or None)


@dataclass
class Stats:
    units: int = 0
    calls: int = 0
    cached: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    candidates: int = 0
    not_located: int = 0
    composed: int = 0
    reviewed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class Calls:
    """Model calls through the ``curation_calls`` cache, within a call budget."""

    def __init__(self, engine: Engine, compose_llm, review_llm, max_calls: int, stats: Stats):
        self.engine, self.llms = engine, {'compose': compose_llm, 'review': review_llm}
        self.max_calls, self.stats = max_calls, stats

    def run(self, step: str, messages: list[dict], schema: type[BaseModel], max_tokens: int):
        llm = self.llms['review' if step == 'review' else 'compose']
        key = _hash(step, llm.config.model, prompts.PROMPT_VERSION, messages)
        with self.engine.begin() as conn:
            cached = conn.execute(text('SELECT output FROM curation_calls WHERE call_key = :k'),
                                  {'k': key}).scalar()
        if cached is not None:
            self.stats.cached += 1
            return schema.model_validate(cached)
        if self.stats.calls >= self.max_calls:
            raise BudgetExhausted(f'{self.max_calls} model calls used')
        self.stats.calls += 1
        result, completion = self._structured(llm, messages, schema, max_tokens)
        self.stats.prompt_tokens += completion.prompt_tokens
        self.stats.completion_tokens += completion.completion_tokens
        with self.engine.begin() as conn:
            conn.execute(text(
                'INSERT INTO curation_calls (call_key, step, model, prompt_version, output,'
                ' prompt_tokens, completion_tokens, latency_ms) VALUES (:k, :s, :m, :v,'
                ' CAST(:o AS jsonb), :p, :c, :l) ON CONFLICT (call_key) DO NOTHING'),
                {'k': key, 's': step, 'm': llm.config.model, 'v': prompts.PROMPT_VERSION,
                 'o': result.model_dump_json(), 'p': completion.prompt_tokens,
                 'c': completion.completion_tokens, 'l': completion.latency_ms})
        return result

    def _structured(self, llm, messages, schema, max_tokens):
        """JSON schema through the API; a provider that rejects the schema keywords (400) gets
        the schema in the prompt instead, and the answer is validated here the same way."""
        if not getattr(self, 'plain_json', False):
            try:
                return llm.structured(messages, schema, max_tokens)
            except LLMError as exc:
                if exc.code != 'PROVIDER_REJECTED':
                    raise
                log.warning('schema rejected by the provider; using the prompt instead',
                            extra={'event': 'curation_plain_json'})
                self.plain_json = True
        from pydantic import ValidationError
        from ..rag.llm import _parse, _repair
        shown = messages + [{'role': 'user', 'content': 'Trả về DUY NHẤT một đối tượng JSON hợp lệ theo'
                             ' JSON Schema sau, không thêm chữ nào khác:\n'
                             + json.dumps(schema.model_json_schema(), ensure_ascii=False)}]
        completion = llm.complete(shown, max_tokens, 0.0, False, None)
        try:
            return _parse(schema, completion), completion
        except ValidationError as error:
            retry = llm.complete(_repair(shown, completion, error), max_tokens, 0.0, False, None)
            try:
                return _parse(schema, retry), retry
            except ValidationError:
                raise LLMError('SCHEMA_INVALID', 'model output failed validation twice') from None


# ---- 1. discover -----------------------------------------------------------------------------

def units(conn: Connection, principal: Principal, school: str | None = None,
          book: str | None = None, limit: int | None = None) -> list[dict]:
    """Parent sections of the active release the principal may read, with their school
    (the reviewed classification most of the section's children carry)."""
    clause, params = catalog.visibility_clause(principal)
    rows = conn.execute(text(
        'SELECT cp.id, cp.generation_id, cp.ordinal, cp.text, cp.meta, m.book_version_id,'
        ' b.title, s.key AS school_key, s.id AS school_id FROM active_corpus a'
        ' JOIN corpus_members m ON m.release_id = a.release_id'
        ' JOIN book_versions v ON v.id = m.book_version_id JOIN books b ON b.id = v.book_id'
        ' JOIN chunk_parents cp ON cp.generation_id = m.generation_id'
        ' JOIN LATERAL (SELECT cc.school_id FROM generation_chunks gc JOIN chunk_classifications cc'
        "   ON cc.generation_id = gc.generation_id AND cc.chunk_id = gc.chunk_id AND cc.status = 'reviewed'"
        '   AND cc.school_id IS NOT NULL WHERE gc.generation_id = cp.generation_id AND gc.parent_id = cp.id'
        '   GROUP BY cc.school_id ORDER BY count(*) DESC LIMIT 1) top ON true'
        ' JOIN schools s ON s.id = top.school_id'
        f" WHERE a.slot = 'default' AND v.status = 'active' AND b.deleted_at IS NULL AND {clause}"
        ' ORDER BY b.title, cp.ordinal'), params).mappings().all()
    out = [dict(r) for r in rows
           if (not school or r['school_key'] == school)
           and (not book or fold(book) in fold(r['title']))]
    return out[:limit] if limit else out


def _pages(conn: Connection, parent: dict) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        'SELECT DISTINCT r.id, r.normalized_text, p.physical_page_number AS page'
        ' FROM generation_chunks gc JOIN chunk_spans sp ON sp.chunk_id = gc.chunk_id'
        ' JOIN page_revisions r ON r.id = sp.page_revision_id JOIN pages p ON p.id = r.page_id'
        ' WHERE gc.generation_id = :g AND gc.parent_id = :p ORDER BY p.physical_page_number'),
        {'g': parent['generation_id'], 'p': parent['id']}).mappings()]


def locate(conn: Connection, principal: Principal, pages: list[dict], quote: str):
    """Evidence span id and how it was found (exact / fuzzy), or (None, 'not_found').
    The span is clipped to the block holding the quote's start (spans live in one block)."""
    for page in pages:
        span = find(page['normalized_text'], quote)
        if span is None:
            continue
        start, end = span
        exact = page['normalized_text'][start:end].lower() == nfc(quote).lower()
        block = conn.execute(text(
            'SELECT id, end_offset FROM blocks WHERE page_revision_id = :r AND start_offset <= :s'
            ' AND end_offset > :s ORDER BY ordinal LIMIT 1'),
            {'r': page['id'], 's': start}).mappings().first()
        if block is None:
            continue
        end = min(end, block['end_offset'])
        existing = conn.execute(text(
            'SELECT id FROM evidence_spans WHERE page_revision_id = :r AND start_offset = :s'
            ' AND end_offset = :e LIMIT 1'), {'r': page['id'], 's': start, 'e': end}).scalar()
        if existing is None:
            from .evidence import create_evidence
            existing = create_evidence(conn, principal, page['id'], start, end, 'ai_inferred')['id']
        return str(existing), 'exact' if exact else 'fuzzy'
    return None, 'not_found'


def _slices(body: str) -> list[str]:
    """A long section read in slices at paragraph breaks (never mid-paragraph if avoidable)."""
    if len(body) <= UNIT_CHARS:
        return [body]
    out, current = [], ''
    for paragraph in body.split('\n\n'):
        if current and len(current) + len(paragraph) > UNIT_CHARS:
            out.append(current)
            current = ''
        current = f'{current}\n\n{paragraph}' if current else paragraph
    return out + ([current] if current else [])


def discover(engine: Engine, principal: Principal, calls: Calls, parent: dict, stats: Stats) -> None:
    header = (parent['meta'] or {}).get('header') or parent['title']
    found: list[prompts.Mention] = []
    for piece in _slices(parent['text']):
        result = calls.run('discover', prompts.discover(
            parent['title'], SCHOOL_LABELS.get(parent['school_key'], parent['school_key']), header,
            piece), prompts.Discovery, 8000)
        found.extend(result.concepts)
    stats.units += 1
    with transaction(engine, principal.user_id) as conn:
        pages = _pages(conn, parent)
        for mention in found:
            evidence_id, located = locate(conn, principal, pages, mention.quote)
            stats.candidates += 1
            stats.not_located += located == 'not_found'
            conn.execute(text(
                'INSERT INTO curation_candidates (book_version_id, parent_id, school_id, name, name_key,'
                ' kind, quote, quote_hash, located, evidence_id, context_missing) VALUES (:v, :p, :s,'
                ' :n, :k, :kind, :q, bazi_sha256_text(:q), :l, :e, :cm)'
                ' ON CONFLICT (parent_id, name_key, quote_hash) DO NOTHING'),
                {'v': parent['book_version_id'], 'p': parent['id'], 's': parent['school_id'],
                 'n': nfc(mention.name).strip(), 'k': name_key(mention.name), 'kind': mention.kind,
                 'q': nfc(mention.quote), 'l': located, 'e': evidence_id,
                 'cm': mention.context_missing})


# ---- 2. compose ------------------------------------------------------------------------------

def groups(conn: Connection, school: str | None = None, names: list[str] | None = None) -> list[dict]:
    """(school, name) groups that have at least one located "explains" quote."""
    rows = conn.execute(text(
        'SELECT c.school_id, s.key AS school_key, c.name_key, min(c.name) AS name'
        ' FROM curation_candidates c JOIN schools s ON s.id = c.school_id'
        " WHERE c.located <> 'not_found' GROUP BY c.school_id, s.key, c.name_key"
        " HAVING bool_or(c.kind = 'explains') ORDER BY s.key, c.name_key")).mappings().all()
    wanted = {name_key(n) for n in names} if names else None
    return [dict(r) for r in rows if (not school or r['school_key'] == school)
            and (wanted is None or r['name_key'] in wanted)]


def _simhash_key(value: str) -> str:
    return ' '.join(re.findall(r'\w+', fold(value)))[:160]


def dossier(conn: Connection, group: dict) -> tuple[list[dict], str, int]:
    """Evidence items (handle, id, quote, block text, book, page, speaker), the prompt text,
    and how many distinct books back it. Near-identical quotes (other editions) count once."""
    rows = conn.execute(text(
        'SELECT c.kind, c.context_missing, e.id AS evidence_id, b.title, b.id AS book_id,'
        ' p.physical_page_number AS page, e.speaker_layer, bl.text AS block_text, bl.ordinal,'
        ' bl.page_revision_id, substr(r.normalized_text, e.start_offset + 1,'
        ' e.end_offset - e.start_offset) AS quote'
        ' FROM curation_candidates c JOIN evidence_spans e ON e.id = c.evidence_id'
        ' JOIN blocks bl ON bl.id = e.block_id JOIN page_revisions r ON r.id = e.page_revision_id'
        ' JOIN pages p ON p.id = r.page_id JOIN book_versions v ON v.id = c.book_version_id'
        ' JOIN books b ON b.id = v.book_id WHERE c.school_id = :s AND c.name_key = :k'
        ' ORDER BY b.title, p.physical_page_number'), {'s': group['school_id'], 'k': group['name_key']}
    ).mappings().all()
    rows = sorted(rows, key=lambda r: (KIND_ORDER[r['kind']], r['title'], r['page']))
    items, seen, size = [], set(), 0
    for row in rows:
        key = _simhash_key(row['quote'])
        if key in seen:
            continue
        seen.add(key)
        context = row['block_text']
        if row['context_missing'] or len(context) < 300:
            near = conn.execute(text(
                'SELECT string_agg(text, E\'\\n\' ORDER BY ordinal) FROM blocks'
                ' WHERE page_revision_id = :r AND ordinal BETWEEN :a AND :b'),
                {'r': row['page_revision_id'], 'a': row['ordinal'] - 1, 'b': row['ordinal'] + 1}).scalar()
            context = near or context
        if size + len(context) > EVIDENCE_CHARS and items:
            break
        size += len(context)
        items.append({'handle': f'E{len(items) + 1}', 'id': str(row['evidence_id']),
                      'quote': row['quote'], 'context': context, 'title': row['title'],
                      'book_id': str(row['book_id']), 'page': row['page'], 'kind': row['kind'],
                      'speaker': row['speaker_layer']})
        if len(items) >= EVIDENCE_LIMIT:
            break
    body = '\n\n'.join(
        f"[{i['handle']}] {i['title']} · tr.{i['page']} · người nói: {i['speaker']} · {i['kind']}\n"
        f"Câu trích: {i['quote']}\nNgữ cảnh: {i['context']}" for i in items)
    return items, body, len({i['book_id'] for i in items})


def _target(conn: Connection, group: dict) -> dict | None:
    """Latest revision of the concept of this school whose label or alias is this name."""
    row = conn.execute(text(
        'SELECT c.id, c.revision, c.state, c.canonical_key FROM concepts c'
        ' JOIN terms t ON t.concept_id = c.id WHERE c.school_id = :s AND t.form_folded = :f'
        ' ORDER BY c.revision DESC LIMIT 1'),
        {'s': group['school_id'], 'f': fold(group['name'])}).mappings().first()
    if row is None:
        return None
    latest = conn.execute(text(
        'SELECT id, revision, state FROM concepts WHERE school_id = :s AND canonical_key = :k'
        ' ORDER BY revision DESC LIMIT 1'), {'s': group['school_id'], 'k': row['canonical_key']}
    ).mappings().one()
    return dict(latest)


def _circular(name: str, definition: str) -> bool:
    rest = fold(definition).replace(fold(name), ' ')
    return len(re.findall(r'\w+', rest)) < 8


def compose(engine: Engine, principal: Principal, calls: Calls, group: dict, stats: Stats,
            refresh: bool = False) -> str | None:
    """Draft revision id for the group's definition, or None when nothing new was written."""
    with transaction(engine, principal.user_id) as conn:
        items, body, books = dossier(conn, group)
        if not items:
            return None
        target = _target(conn, group)
        current = None
        if target is not None:
            current = conn.execute(text(
                'SELECT dossier_hash, status, rewrite_note FROM concept_curation WHERE concept_id = :c'),
                {'c': target['id']}).mappings().first()
    note = current['rewrite_note'] if current and current['status'] == 'rewrite_requested' else ''
    digest = _hash(body, note, prompts.PROMPT_VERSION)
    if target and not refresh and (target['state'] == 'approved' or (
            current and current['dossier_hash'] == digest)):
        stats.skipped += 1
        return None
    school = SCHOOL_LABELS.get(group['school_key'], group['school_key'])
    result = calls.run('compose', prompts.compose(group['name'], school, body, note),
                       prompts.Definition, 10000)
    handles = {i['handle']: i['id'] for i in items}
    issues = list(result.issues)
    claims = []
    for claim in result.claims:
        cited = [h.strip('[] ') for h in claim.evidence]
        unknown = [h for h in cited if h not in handles]
        if unknown:
            issues.append(f'ý "{claim.text[:60]}" dẫn nhãn không có: {", ".join(unknown)}')
        known = [handles[h] for h in cited if h in handles]
        if known:
            claims.append({'text': claim.text, 'evidence_ids': known})
    status = result.status
    if status == 'ready' and (not claims or len(result.definition.strip()) < 40):
        status, issues = 'needs_context', issues + ['định nghĩa trống hoặc không có ý nào có nguồn']
    if status == 'ready' and _circular(group['name'], result.definition):
        issues.append('định nghĩa có thể chỉ lặp lại tên gọi')
    description = result.definition.strip() or f'(Chưa đủ căn cứ: {result.missing or "thiếu bằng chứng"})'
    cited_ids = list(dict.fromkeys(e for c in claims for e in c['evidence_ids']))
    with transaction(engine, principal.user_id) as conn:
        if target is None:
            key = f"bien_soan.{slug(group['name'])}"
            n = 2
            while conn.execute(text('SELECT 1 FROM concepts WHERE school_id = :s AND canonical_key = :k'),
                               {'s': group['school_id'], 'k': key}).first():
                key = f"bien_soan.{slug(group['name'])[:55]}_{n}"
                n += 1
            concept = ontology.create_concept(conn, group['school_id'], key, group['name'], description)
        else:
            concept = ontology.revise_concept(conn, target['id'], target['revision'], None, description,
                                              carry_curation=False)
        for ordinal, evidence_id in enumerate(cited_ids):
            conn.execute(text('INSERT INTO concept_sources (concept_id, evidence_id, ordinal)'
                              ' VALUES (:c, :e, :o) ON CONFLICT DO NOTHING'),
                         {'c': concept['id'], 'e': evidence_id, 'o': ordinal})
        conn.execute(text(
            'INSERT INTO concept_curation (concept_id, name_key, essential_notes, claims, issues, status,'
            ' independent_sources, dossier_hash, compose_model, prompt_version) VALUES (:c, :k, :n,'
            ' CAST(:cl AS jsonb), CAST(:i AS jsonb), :st, :b, :d, :m, :v)'),
            {'c': concept['id'], 'k': group['name_key'], 'n': result.essential_notes.strip(),
             'cl': json.dumps(claims, ensure_ascii=False), 'i': json.dumps(issues, ensure_ascii=False),
             'st': status, 'b': books, 'd': digest, 'm': calls.llms['compose'].config.model,
             'v': prompts.PROMPT_VERSION})
    stats.composed += 1
    return concept['id']


# ---- 3. review -------------------------------------------------------------------------------

SEVERITY = {'pass': 'low', 'fix': 'medium', 'fail': 'high'}


def review(engine: Engine, principal: Principal, calls: Calls, concept_id: str, stats: Stats) -> None:
    with transaction(engine, principal.user_id) as conn:
        row = conn.execute(text(
            'SELECT c.label, c.description, s.key AS school_key, k.essential_notes, k.claims, k.status'
            ' FROM concept_curation k JOIN concepts c ON c.id = k.concept_id'
            ' JOIN schools s ON s.id = c.school_id WHERE k.concept_id = :c'), {'c': concept_id}
        ).mappings().one()
        evidence = conn.execute(text(
            'SELECT e.id, b.title, p.physical_page_number AS page, e.speaker_layer, bl.text'
            ' FROM concept_sources cs JOIN evidence_spans e ON e.id = cs.evidence_id'
            ' JOIN blocks bl ON bl.id = e.block_id JOIN page_revisions r ON r.id = e.page_revision_id'
            ' JOIN pages p ON p.id = r.page_id JOIN book_versions v ON v.id = e.book_version_id'
            ' JOIN books b ON b.id = v.book_id WHERE cs.concept_id = :c ORDER BY cs.ordinal'),
            {'c': concept_id}).mappings().all()
    if row['status'] != 'ready':
        verdict = prompts.Review(verdict='fail', problems=[prompts.Problem(
            kind='unclear', detail=f'Bản soạn ở trạng thái {row["status"]}, chưa phải định nghĩa.')])
    else:
        handle = {str(e['id']): f'E{i + 1}' for i, e in enumerate(evidence)}
        claims = '\n'.join(f"- {c['text']} ← {', '.join(handle.get(x, '?') for x in c['evidence_ids'])}"
                           for c in row['claims'])
        body = '\n\n'.join(f"[{handle[str(e['id'])]}] {e['title']} · tr.{e['page']} ·"
                           f" người nói: {e['speaker_layer']}\n{e['text']}" for e in evidence)
        verdict = calls.run('review', prompts.review(
            row['label'], SCHOOL_LABELS.get(row['school_key'], row['school_key']), row['description'],
            row['essential_notes'], claims, body), prompts.Review, 6000)
    with transaction(engine, principal.user_id) as conn:
        conn.execute(text(
            'UPDATE concept_curation SET llm_verdict = :v, llm_problems = CAST(:p AS jsonb),'
            ' review_model = :m WHERE concept_id = :c'),
            {'v': verdict.verdict, 'p': json.dumps([p.model_dump() for p in verdict.problems],
                                                   ensure_ascii=False),
             'm': calls.llms['review'].config.model, 'c': concept_id})
        conn.execute(text(
            "INSERT INTO review_items (entity_kind, entity_id, reason_code, severity)"
            " SELECT 'concept', :c, 'CANDIDATE_DEFINITION', :s WHERE NOT EXISTS (SELECT 1 FROM"
            " review_items WHERE entity_kind = 'concept' AND entity_id = :c"
            " AND reason_code = 'CANDIDATE_DEFINITION')"),
            {'c': concept_id, 's': SEVERITY[verdict.verdict]})
    stats.reviewed += 1


# ---- run -------------------------------------------------------------------------------------

def run(engine: Engine, principal: Principal, settings, steps: tuple[str, ...] = ('discover', 'compose',
        'review'), school: str | None = None, book: str | None = None, max_units: int | None = None,
        max_calls: int = 200, names: list[str] | None = None, refresh: bool = False,
        dry_run: bool = False, transport=None) -> dict:
    stats = Stats()
    with transaction(engine, principal.user_id) as conn:
        todo = units(conn, principal, school, book, max_units)
    if dry_run:
        chars = sum(len(u['text']) for u in todo)
        return {'dry_run': True, 'units': len(todo), 'chars': chars,
                'estimated_input_tokens': int(chars / 3.2) + 1500 * len(todo),
                'books': sorted({u['title'] for u in todo})}
    compose_cfg, review_cfg = config_from(settings), config_from(settings, review=True)
    if compose_cfg is None:
        raise LLMError('NOT_CONFIGURED', 'set CURATOR_LLM_BASE_URL and CURATOR_LLM_MODEL')
    compose_llm = SyncLLM(compose_cfg, transport)
    review_llm = compose_llm if review_cfg.model == compose_cfg.model else SyncLLM(review_cfg, transport)
    calls = Calls(engine, compose_llm, review_llm, max_calls, stats)
    try:
        if 'discover' in steps:
            for parent in todo:
                discover(engine, principal, calls, parent, stats)
        written = []
        if 'compose' in steps:
            with transaction(engine, principal.user_id) as conn:
                todo_groups = groups(conn, school, names)
            for group in todo_groups:
                try:
                    concept_id = compose(engine, principal, calls, group, stats, refresh)
                except LLMError as exc:
                    stats.errors.append(f"{group['name']}: {exc.code}")
                    continue
                if concept_id:
                    written.append(concept_id)
        if 'review' in steps:
            with transaction(engine, principal.user_id) as conn:
                pending = [str(r) for r in conn.execute(text(
                    'SELECT concept_id FROM concept_curation WHERE llm_verdict IS NULL'
                    ' ORDER BY created_at')).scalars()]
            for concept_id in pending:
                try:
                    review(engine, principal, calls, concept_id, stats)
                except LLMError as exc:
                    stats.errors.append(f'review {concept_id}: {exc.code}')
    except BudgetExhausted as exc:
        stats.errors.append(f'dừng: {exc}')
    finally:
        compose_llm.close()
        if review_llm is not compose_llm:
            review_llm.close()
    return stats.__dict__
