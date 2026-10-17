"""Context packing into an evidence bundle (docs/07 · steps 7–8).

Ranked chunks become at most ``max_groups`` evidence groups within a token
budget: a chunk next to one already chosen (same generation, section and
speaker) joins its group, and pieces the two share through overlap appear once,
so a group's excerpt is exactly its spans' text in reading order. At most
``per_book`` groups come from one book unless the caller filtered by book.
Chunks are never cut — a table or a case is whole or absent — and anything
left out is counted in ``omitted`` with ``truncated`` set. Groups get short
opaque handles (``E1``…) that a model cites; only the backend maps them back to
revisions, offsets and pages.
"""
from __future__ import annotations

from ..ingestion.chunker import count_tokens

MAX_GROUPS = 8
MAX_TOKENS = 6000
PER_BOOK = 3


def _span_key(span: dict) -> tuple:
    return (span['page_revision_id'], span['block_id'], span['start_offset'], span['end_offset'])


def pack(hits: list[dict], max_groups: int = MAX_GROUPS, max_tokens: int = MAX_TOKENS,
         per_book: int = PER_BOOK, book_filtered: bool = False) -> dict:
    groups: list[dict] = []
    used, omitted = 0, 0
    for hit in hits:
        scope = (hit['generation_id'], hit['section_path'], hit['speaker_layer'])
        group = next((g for g in groups if g['scope'] == scope and (
            hit['ordinal'] - 1 in g['ordinals'] or hit['ordinal'] + 1 in g['ordinals'])), None)
        if group is None:
            books = sum(1 for g in groups if g['book_version_id'] == hit['book_version_id'])
            if len(groups) >= max_groups or (not book_filtered and books >= per_book):
                omitted += 1
                continue
            group = {'scope': scope, 'ordinals': set(), 'pieces': {}, 'hits': [],
                     'book_version_id': hit['book_version_id']}
            new_group = True
        else:
            new_group = False
        pieces = {}
        for span in hit['spans']:
            key = _span_key(span)
            if key not in group['pieces']:
                pieces[key] = {**span, 'text': hit['text'][span['chunk_start']:span['chunk_end']]}
        cost = sum(count_tokens(p['text']) for p in pieces.values())
        if used + cost > max_tokens:
            omitted += 1
            continue
        used += cost
        group['pieces'].update(pieces)
        group['ordinals'].add(hit['ordinal'])
        group['hits'].append(hit)
        if new_group:
            groups.append(group)
    bundle = []
    for number, group in enumerate(groups, start=1):
        first = group['hits'][0]
        ordered = sorted(group['pieces'].values(), key=lambda p: (
            p['physical_page_number'], p['start_offset']))
        bundle.append({
            'evidence_id': f'E{number}',
            'chunk_ids': [h['chunk_id'] for h in sorted(group['hits'], key=lambda h: h['ordinal'])],
            'book_id': first['book_id'], 'book_title': first['book_title'],
            'book_version_id': first['book_version_id'], 'edition_label': first['edition_label'],
            'school_key': first['school_key'], 'speaker_layer': first['speaker_layer'],
            'section_title': first['section_title'], 'section_path': first['section_path'],
            'pages': sorted({p['physical_page_number'] for p in ordered}),
            'printed_pages': sorted({p['printed_page_label'] for p in ordered
                                     if p['printed_page_label']}),
            'spans': [{k: p[k] for k in ('page_revision_id', 'block_id', 'start_offset',
                                         'end_offset', 'physical_page_number')} for p in ordered],
            'excerpt': '\n\n'.join(p['text'] for p in ordered),
            'tokens': sum(count_tokens(p['text']) for p in ordered),
            'score': max(h['score'] for h in group['hits']),
            'rerank_score': max((h['rerank_score'] for h in group['hits'] if 'rerank_score' in h),
                                default=None),
            'kinds': sorted({h['kind'] for h in group['hits']}),
            'merged': len(group['hits']) > 1})
    return {'groups': bundle, 'tokens': used, 'omitted': omitted, 'truncated': omitted > 0}
