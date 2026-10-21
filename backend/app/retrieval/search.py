"""Hybrid candidate retrieval over the active corpus release (docs/07 · Luồng tìm kiếm, T035).

The server, not the caller, decides what may be searched: the release the
active pointer names, its published generations, versions that are active and
not ``restricted``, books the principal may read, and only ``accepted`` chunks.
Filters narrow that scope by intersection (school from reviewed
classifications, books/versions, topics, physical page range) and are applied
inside both the lexical and the vector query, never after a top-k cut.

Query: NFC for display; the accent-folded form drives FTS ``simple`` (no claim
of Vietnamese word segmentation). Approved aliases from the ontology release the
corpus pins add up to five variants of a concept named in the query, and every
matched alias phrase boosts chunks containing it exactly. Lexical (ts_rank_cd on
folded text, plus accented matches) and vector (cosine in the release's
collection) candidate lists are fused by weighted reciprocal rank,
``Σ wᵢ / (60 + rankᵢ)`` — scores of different kinds are never added. A vector
side that cannot run (no collection, provider down) degrades to lexical with a
flag instead of failing. Vector neighbours always exist, so a profile's
``max_distance`` (calibrated per model, T036; 0.6 for the offline fixture) drops
the ones too far to be evidence — otherwise a nonsense query would never be
``no_match``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import time

from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..documents.catalog import visibility_clause
from ..documents.text import fold, nfc
from .embedding import EmbeddingError, build_embedder, checked
from .indexer import LEXICAL_VERSION, _vector_literal
from .models import load_profile
from .packing import pack
from .rerank import MAX_CANDIDATES as RERANK_CANDIDATES, rerank_hits

CANDIDATES = 80
FIXTURE_MAX_DISTANCE = 0.6
RRF_K = 60
WEIGHTS = {'lexical': 1.0, 'vector': 1.0, 'section': 1.0}
MAX_EXPANSIONS = 5
PHRASE_BONUS = 1.0
# Function words dropped from the OR query (folded); kept for exact phrases.
# Ambiguous folds such as "the" (thể/thế) and "chu" (chủ/chú) stay searchable.
STOPWORDS = {'la', 'gi', 'cua', 'va', 'co', 'khong', 'nao', 'sao', 'nhu', 'trong', 'theo', 'mot',
             'cac', 'nhung', 'duoc', 'cho', 'voi', 've', 'o', 'tai', 'thi', 'ma', 'neu', 'de',
             'do', 'nay', 'day', 'hay', 'hoac', 'bao', 'nhieu', 'ra', 'vi', 'phai', 'den', 'ai',
             'gi', 'the nao', 'tu', 'cung', 'nhat', 'rat', 'hon', 'qua', 'se', 'da', 'dang'}
_WORD = re.compile(r'\w+', re.UNICODE)


@dataclass
class Spec:
    query: str
    top_k: int = 8
    school_ids: list = field(default_factory=list)
    book_ids: list = field(default_factory=list)
    book_version_ids: list = field(default_factory=list)
    topic_ids: list = field(default_factory=list)
    page_range: tuple[int, int] | None = None
    rerank: bool = True
    pack: bool = False
    # Evaluation compares lexical-only / vector-only / hybrid on one release (docs/07);
    # None is every channel, which is all /search ever uses.
    channels: tuple[str, ...] | None = None

    @property
    def filtered(self) -> bool:
        return bool(self.school_ids or self.book_ids or self.book_version_ids or self.topic_ids
                    or self.page_range)


def _active(conn: Connection):
    return conn.execute(text(
        'SELECT a.release_id, a.visibility_epoch, r.ontology_release_id, c.physical_table,'
        ' c.profile_id FROM active_corpus a JOIN corpus_releases r ON r.id = a.release_id'
        " JOIN embedding_collections c ON c.id = r.embedding_collection_id WHERE a.slot = 'default'")
    ).mappings().first()


def _accented(query: str) -> bool:
    return fold(query) != query.lower()


def expansions(conn: Connection, ontology_release_id, query: str, school_ids: list) -> list[dict]:
    """Approved aliases named in the query, and other approved forms of those concepts.

    A query typed with diacritics is matched with them ("Dụng Thần" is not the branch
    "Thân"); an accent-free query is matched folded. One-syllable aliases (Can, Chi…)
    are too ambiguous to expand from inside a sentence ("ở đâu" is not "Dậu").
    """
    accented = _accented(query)
    target = query.lower() if accented else fold(query)
    rows = conn.execute(text(
        'SELECT c.id AS concept_id, c.school_id, s.key AS school_key, c.canonical_key,'
        ' t.form_nfc, t.form_folded FROM ontology_members m JOIN concepts c ON c.id = m.concept_id'
        ' JOIN schools s ON s.id = c.school_id JOIN terms t ON t.id = m.term_id'
        ' WHERE m.release_id = :r AND (CAST(:schools AS uuid[]) IS NULL'
        ' OR c.school_id = ANY(CAST(:schools AS uuid[])))'),
        {'r': ontology_release_id,
         'schools': [str(s) for s in school_ids] or None}).mappings().all()
    taken: list[tuple[int, int]] = []
    matched: dict = {}
    for row in sorted(rows, key=lambda r: -len(r['form_folded'])):
        form = row['form_nfc'].lower() if accented else row['form_folded']
        if len(form) < 2 or (' ' not in form and form != target.strip()):
            continue
        for hit in re.finditer(rf'(?<!\w){re.escape(form)}(?!\w)', target):
            span = hit.span()
            if any(span[0] < end and start < span[1] for start, end in taken):
                continue                    # a longer alias already covers these words
            taken.append(span)
            matched.setdefault(row['concept_id'], {'concept': row['canonical_key'],
                                                   'school_key': row['school_key'],
                                                   'matched': row['form_nfc'], 'variants': []})
    out = []
    for concept_id, item in matched.items():
        for row in rows:
            if (row['concept_id'] == concept_id and row['form_folded'] != fold(item['matched'])
                    and row['form_nfc'] not in item['variants']):
                item['variants'].append(row['form_nfc'])
        out.append(item)
    budget = MAX_EXPANSIONS
    for item in out:
        item['variants'] = item['variants'][:budget]
        budget -= len(item['variants'])
    return out


def _scope(principal: Principal, spec: Spec, release_id) -> tuple[str, dict]:
    visible, params = visibility_clause(principal)
    params = {**params, 'release': release_id}
    member = [f'm.release_id = :release', "v.status = 'active'",
              "v.rights_status <> 'restricted'", 'b.deleted_at IS NULL', visible]
    if spec.book_version_ids:
        member.append('m.book_version_id = ANY(CAST(:versions AS uuid[]))')
        params['versions'] = [str(v) for v in spec.book_version_ids]
    if spec.book_ids:
        member.append('v.book_id = ANY(CAST(:books AS uuid[]))')
        params['books'] = [str(b) for b in spec.book_ids]
    chunk = ["c.quality_state = 'accepted'"]
    if spec.school_ids:
        chunk.append('EXISTS (SELECT 1 FROM chunk_classifications cc WHERE cc.generation_id ='
                     ' gc.generation_id AND cc.chunk_id = gc.chunk_id AND cc.status = \'reviewed\''
                     ' AND cc.school_id = ANY(CAST(:schools AS uuid[])))')
        params['schools'] = [str(s) for s in spec.school_ids]
    if spec.topic_ids:
        chunk.append('EXISTS (SELECT 1 FROM chunk_classifications cc WHERE cc.generation_id ='
                     " gc.generation_id AND cc.chunk_id = gc.chunk_id AND cc.status <> 'rejected'"
                     ' AND cc.topic_id = ANY(CAST(:topics AS uuid[])))')
        params['topics'] = [str(t) for t in spec.topic_ids]
    if spec.page_range:
        chunk.append('EXISTS (SELECT 1 FROM chunk_spans sp JOIN page_revisions pr'
                     ' ON pr.id = sp.page_revision_id JOIN pages pg ON pg.id = pr.page_id'
                     ' WHERE sp.chunk_id = gc.chunk_id'
                     ' AND pg.physical_page_number BETWEEN :page_from AND :page_to)')
        params.update(page_from=spec.page_range[0], page_to=spec.page_range[1])
    cte = ('WITH members AS (SELECT m.generation_id, m.book_version_id FROM corpus_members m'
           ' JOIN book_versions v ON v.id = m.book_version_id JOIN books b ON b.id = v.book_id'
           f" WHERE {' AND '.join(member)}),"
           ' scope AS (SELECT gc.chunk_id, gc.generation_id, gc.section_id, gc.ordinal,'
           ' mm.book_version_id'
           ' FROM generation_chunks gc JOIN members mm ON mm.generation_id = gc.generation_id'
           f" JOIN chunks c ON c.id = gc.chunk_id WHERE {' AND '.join(chunk)})")
    return cte, params


def _tsquery(words: list[str]) -> str:
    return ' | '.join(dict.fromkeys(words))


def _lexical(conn: Connection, cte: str, params: dict, folded: str, accented: str,
             phrases: list[str]) -> list[tuple]:
    words = [w for w in _WORD.findall(folded) if w not in STOPWORDS] or _WORD.findall(folded)
    for phrase in phrases:
        words += _WORD.findall(phrase)
    if not words:
        return []
    accented_words = [w for w in _WORD.findall(accented.lower()) if fold(w) not in STOPWORDS]
    boosters, extra = [], {}
    for i, phrase in enumerate(dict.fromkeys(phrases)):
        boosters.append(f" + {PHRASE_BONUS} * (se.ts_folded @@ phraseto_tsquery('simple',"
                        f' :phrase{i}))::int')
        extra[f'phrase{i}'] = phrase
    rows = conn.execute(text(
        f'{cte} SELECT s.chunk_id, ts_rank_cd(se.ts_folded, to_tsquery(\'simple\', :orq), 32)'
        " + 0.5 * ts_rank_cd(se.ts_nfc, to_tsquery('simple', :nfcq), 32)"
        f"{''.join(boosters)} AS score FROM scope s JOIN search_entries se"
        ' ON se.chunk_id = s.chunk_id AND se.lexical_profile_version = :lv'
        " WHERE se.ts_folded @@ to_tsquery('simple', :orq)"
        ' ORDER BY score DESC, s.chunk_id LIMIT :limit'),
        {**params, **extra, 'orq': _tsquery(words), 'lv': LEXICAL_VERSION, 'limit': CANDIDATES,
         'nfcq': _tsquery(accented_words) or _tsquery(words)}).all()
    return [(str(r[0]), float(r[1])) for r in rows]


def _sections(conn: Connection, cte: str, params: dict, folded: str) -> list[tuple]:
    """First chunk of each section whose title matches: titles are not chunk text
    ("Chương Luận Dụng Thần" lives in the section tree), yet people ask by them."""
    words = [w for w in _WORD.findall(folded) if w not in STOPWORDS]
    if not words:
        return []
    title = "lower(unaccent(replace(replace(sec.title, 'Đ', 'D'), 'đ', 'd')))"
    rows = conn.execute(text(
        f'{cte}, firsts AS (SELECT DISTINCT ON (s.section_id) s.chunk_id, s.section_id'
        ' FROM scope s JOIN generation_chunks gc ON gc.chunk_id = s.chunk_id'
        ' AND gc.generation_id = s.generation_id ORDER BY s.section_id, gc.ordinal)'
        f" SELECT f.chunk_id, ts_rank_cd(to_tsvector('simple', {title}),"
        " to_tsquery('simple', :orq), 32) AS score FROM firsts f"
        ' JOIN sections sec ON sec.id = f.section_id'
        f" WHERE to_tsvector('simple', {title}) @@ to_tsquery('simple', :orq)"
        ' ORDER BY score DESC, f.chunk_id LIMIT :limit'),
        {**params, 'orq': _tsquery(words), 'limit': CANDIDATES}).all()
    return [(str(r[0]), float(r[1])) for r in rows]


def _vector(conn: Connection, cte: str, params: dict, active, query: str,
            app_env: str, transport=None) -> tuple[list[tuple], str | None]:
    if not active['physical_table']:
        return [], 'vector_unavailable'
    try:
        profile = load_profile(conn, active['profile_id'])
        embedder = build_embedder(profile, app_env, transport)
        embed = getattr(embedder, 'embed_query', embedder.embed)   # Jina: query prompt
        vector = checked(embed([profile.config.get('query_prefix', '') + query]), profile)[0]
    except EmbeddingError:
        return [], 'vector_unavailable'
    table = sql.Identifier(active['physical_table']).as_string(conn.connection.dbapi_connection)
    limit = profile.config.get('max_distance', FIXTURE_MAX_DISTANCE if profile.is_fixture else 2.0)
    conn.execute(text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)"))
    rows = conn.execute(text(
        f'{cte} SELECT s.chunk_id, e.vector <=> CAST(:q AS vector) AS distance FROM scope s'
        f' JOIN {table} e ON e.chunk_id = s.chunk_id WHERE e.vector <=> CAST(:q AS vector) <= :max'
        ' ORDER BY distance, s.chunk_id LIMIT :limit'),
        {**params, 'q': _vector_literal(vector), 'limit': CANDIDATES, 'max': limit}).all()
    return [(str(r[0]), float(r[1])) for r in rows], None


def fuse(lists: dict[str, list[tuple]], weights: dict[str, float] = WEIGHTS) -> list[dict]:
    """Weighted reciprocal rank fusion; ranks start at 1, raw scores never mix."""
    fused: dict[str, dict] = {}
    for name, items in lists.items():
        for rank, (chunk_id, raw) in enumerate(items, start=1):
            hit = fused.setdefault(chunk_id, {'chunk_id': chunk_id, 'score': 0.0, 'ranks': {}})
            hit['score'] += weights.get(name, 1.0) / (RRF_K + rank)
            hit['ranks'][name] = rank
    return sorted(fused.values(), key=lambda h: (-h['score'], h['chunk_id']))


def _details(conn: Connection, hits: list[dict]) -> list[dict]:
    if not hits:
        return []
    ids = [h['chunk_id'] for h in hits]
    rows = {str(r['id']): r for r in conn.execute(text(
        'SELECT c.id, c.text, c.content_hash, c.kind, c.speaker_layer FROM chunks c'
        ' WHERE c.id = ANY(CAST(:ids AS uuid[]))'), {'ids': ids}).mappings()}
    spans: dict[str, list] = {}
    for r in conn.execute(text(
            'SELECT sp.chunk_id, sp.page_revision_id, sp.block_id, sp.start_offset, sp.end_offset,'
            ' sp.chunk_start, sp.chunk_end, pg.physical_page_number, pr.printed_page_label'
            ' FROM chunk_spans sp JOIN page_revisions pr ON pr.id = sp.page_revision_id'
            ' JOIN pages pg ON pg.id = pr.page_id WHERE sp.chunk_id = ANY(CAST(:ids AS uuid[]))'
            ' ORDER BY sp.chunk_id, sp.ordinal'), {'ids': ids}).mappings():
        spans.setdefault(str(r['chunk_id']), []).append(
            {'page_revision_id': str(r['page_revision_id']), 'block_id': str(r['block_id']),
             'start_offset': r['start_offset'], 'end_offset': r['end_offset'],
             'chunk_start': r['chunk_start'], 'chunk_end': r['chunk_end'],
             'physical_page_number': r['physical_page_number'],
             'printed_page_label': r['printed_page_label']})
    out = []
    for hit in hits:
        row, meta = rows[hit['chunk_id']], hit['meta']
        out.append({**hit, 'text': row['text'], 'content_hash': row['content_hash'].strip(),
                    'kind': row['kind'], 'speaker_layer': row['speaker_layer'], **meta,
                    'spans': spans.get(hit['chunk_id'], []),
                    'pages': sorted({s['physical_page_number'] for s in
                                     spans.get(hit['chunk_id'], [])})})
    return out


def _meta(conn: Connection, cte: str, params: dict, ids: list[str]) -> dict[str, dict]:
    rows = conn.execute(text(
        f'{cte} SELECT s.chunk_id, s.book_version_id, s.generation_id, s.ordinal,'
        ' b.id AS book_id, b.title,'
        ' v.edition_label, sec.title AS section_title, sec.path AS section_path,'
        ' (SELECT sch.key FROM chunk_classifications cc JOIN schools sch ON sch.id = cc.school_id'
        "  WHERE cc.generation_id = s.generation_id AND cc.chunk_id = s.chunk_id"
        "  AND cc.status = 'reviewed' LIMIT 1) AS school_key"
        ' FROM scope s JOIN book_versions v ON v.id = s.book_version_id'
        ' JOIN books b ON b.id = v.book_id JOIN sections sec ON sec.id = s.section_id'
        ' WHERE s.chunk_id = ANY(CAST(:ids AS uuid[]))'), {**params, 'ids': ids}).mappings()
    return {str(r['chunk_id']): {'book_id': str(r['book_id']), 'book_title': r['title'],
                                 'book_version_id': str(r['book_version_id']),
                                 'edition_label': r['edition_label'],
                                 'generation_id': str(r['generation_id']),
                                 'ordinal': r['ordinal'],
                                 'section_title': r['section_title'],
                                 'section_path': r['section_path'],
                                 'school_key': r['school_key']} for r in rows}


def search(conn: Connection, principal: Principal, spec: Spec, app_env: str = 'dev',
           transport=None, rerank_transport=None) -> dict:
    started = time.perf_counter()
    normalized = ' '.join(nfc(spec.query).split())
    folded = fold(normalized)
    active = _active(conn)
    base = {'query': {'normalized': normalized, 'folded': folded, 'expansions': []}, 'hits': [],
            'degraded': [], 'release_id': None, 'visibility_epoch': None}
    if active is None:
        return {**base, 'status': 'empty_corpus'}
    base.update(release_id=str(active['release_id']), visibility_epoch=active['visibility_epoch'])
    cte, params = _scope(principal, spec, active['release_id'])
    in_scope = conn.execute(text(f'{cte} SELECT count(*) FROM scope'), params).scalar_one()
    if in_scope == 0:
        return {**base, 'status': 'empty_filters' if spec.filtered else 'empty_corpus'}
    found = expansions(conn, active['ontology_release_id'], normalized, spec.school_ids)
    phrases = [fold(e['matched']) for e in found] + [fold(v) for e in found for v in e['variants']]
    use = set(spec.channels or ('lexical', 'section', 'vector'))
    lists = {}
    if 'lexical' in use:
        lists['lexical'] = _lexical(conn, cte, params, folded, normalized, phrases)
    sections = _sections(conn, cte, params, folded) if 'section' in use else []
    if sections:
        lists['section'] = sections
    if 'vector' in use:
        vector, problem = _vector(conn, cte, params, active, normalized, app_env, transport)
        if problem:
            base['degraded'].append(problem)
        else:
            lists['vector'] = vector
    fused = fuse(lists)[:max(spec.top_k, RERANK_CANDIDATES if spec.rerank or spec.pack else 0)]
    meta = _meta(conn, cte, params, [h['chunk_id'] for h in fused])
    for hit in fused:
        hit['meta'] = meta[hit['chunk_id']]
    candidates = _details(conn, fused)
    for hit in candidates:
        hit.pop('meta', None)
    if spec.rerank:
        candidates, problem = rerank_hits(conn, normalized, candidates, app_env, rerank_transport)
        if problem:
            base['degraded'].append(problem)
    hits = candidates[:spec.top_k]
    result = {**base, 'status': 'ok' if hits else 'no_match', 'hits': hits,
              'query': {**base['query'], 'expansions': found},
              'counts': {'scope': in_scope, **{k: len(v) for k, v in lists.items()}}}
    if spec.pack:
        from .citations import save_bundle
        bundle = pack(candidates, book_filtered=bool(spec.book_ids or spec.book_version_ids))
        bundle['bundle_id'] = save_bundle(conn, principal, active['release_id'],
                                          active['visibility_epoch'], normalized, bundle)
        result['bundle'] = bundle
    result['took_ms'] = round((time.perf_counter() - started) * 1000, 1)
    from ..ops.metrics import record_search
    record_search(result['took_ms'])
    return result
