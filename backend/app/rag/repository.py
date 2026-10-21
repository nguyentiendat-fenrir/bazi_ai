"""All SQL of the RAG pilot (repository layer: data access, no business rules).

Scope rules are the existing ones (``retrieval/search.py``): the active corpus
release, published generations, versions active and not ``restricted``, books
the principal may read, accepted chunks, plus optional school/book filters —
applied inside the dense query; the sparse (BM25) side is filtered by the same
scope's chunk-id set.
"""
from __future__ import annotations

from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..retrieval.indexer import _vector_literal
from ..retrieval.search import Spec, _active, _scope


class RagRepository:
    def __init__(self, conn: Connection):
        self.conn = conn

    def active(self):
        return _active(self.conn)

    def scope(self, principal: Principal, spec: Spec, release_id) -> tuple[str, dict]:
        return _scope(principal, spec, release_id)

    def scope_ids(self, cte: str, params: dict) -> set[str]:
        return {str(r[0]) for r in self.conn.execute(text(f'{cte} SELECT chunk_id FROM scope'),
                                                       params)}

    def bm25_documents(self, release_id) -> list[tuple[str, str]]:
        """(chunk_id, header + text) of every accepted child published in the release."""
        rows = self.conn.execute(text(
            "SELECT gc.chunk_id, coalesce(cm.meta->>'header', '') || E'\\n' || c.text"
            ' FROM corpus_members m JOIN generation_chunks gc ON gc.generation_id = m.generation_id'
            " JOIN chunks c ON c.id = gc.chunk_id AND c.quality_state = 'accepted'"
            ' LEFT JOIN chunk_meta cm ON cm.generation_id = gc.generation_id'
            ' AND cm.chunk_id = gc.chunk_id WHERE m.release_id = :r'), {'r': release_id}).all()
        return [(str(r[0]), r[1]) for r in rows]

    def dense(self, cte: str, params: dict, table: str, vector: list[float],
              limit: int) -> list[tuple[str, float]]:
        """Top children by cosine similarity (1 − distance) inside the scope."""
        name = sql.Identifier(table).as_string(self.conn.connection.dbapi_connection)
        self.conn.execute(text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)"))
        rows = self.conn.execute(text(
            f'{cte} SELECT s.chunk_id, 1 - (e.vector <=> CAST(:q AS vector)) AS similarity'
            f' FROM scope s JOIN {name} e ON e.chunk_id = s.chunk_id'
            ' ORDER BY e.vector <=> CAST(:q AS vector), s.chunk_id LIMIT :limit'),
            {**params, 'q': _vector_literal(vector), 'limit': limit}).all()
        return [(str(r[0]), float(r[1])) for r in rows]

    def children(self, cte: str, params: dict, ids: list[str]) -> dict[str, dict]:
        """Child rows with metadata, parent, book and source spans."""
        if not ids:
            return {}
        rows = self.conn.execute(text(
            f'{cte} SELECT s.chunk_id, s.generation_id, s.book_version_id, gc.parent_id,'
            ' c.text, c.kind, c.speaker_layer, c.token_count, cm.meta, b.id AS book_id,'
            ' b.title AS book_title, v.edition_label, sec.title AS section_title,'
            ' sec.path AS section_path FROM scope s'
            ' JOIN generation_chunks gc ON gc.chunk_id = s.chunk_id'
            ' AND gc.generation_id = s.generation_id JOIN chunks c ON c.id = s.chunk_id'
            ' LEFT JOIN chunk_meta cm ON cm.generation_id = s.generation_id'
            ' AND cm.chunk_id = s.chunk_id JOIN book_versions v ON v.id = s.book_version_id'
            ' JOIN books b ON b.id = v.book_id JOIN sections sec ON sec.id = s.section_id'
            ' WHERE s.chunk_id = ANY(CAST(:ids AS uuid[]))'), {**params, 'ids': ids}).mappings()
        out = {str(r['chunk_id']): dict(r) for r in rows}
        for r in self.conn.execute(text(
                'SELECT sp.chunk_id, sp.page_revision_id, sp.start_offset, sp.end_offset,'
                ' pg.physical_page_number, pr.printed_page_label FROM chunk_spans sp'
                ' JOIN page_revisions pr ON pr.id = sp.page_revision_id'
                ' JOIN pages pg ON pg.id = pr.page_id WHERE sp.chunk_id = ANY(CAST(:ids AS uuid[]))'
                ' ORDER BY sp.chunk_id, sp.ordinal'), {'ids': ids}).mappings():
            row = out.get(str(r['chunk_id']))
            if row is not None:
                row.setdefault('spans', []).append(dict(r))
        return out

    def parents(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        rows = self.conn.execute(text(
            'SELECT id, generation_id, ordinal, text, token_count, meta, summary, summary_status'
            ' FROM chunk_parents WHERE id = ANY(CAST(:ids AS uuid[]))'), {'ids': ids}).mappings()
        return {str(r['id']): dict(r) for r in rows}

    def reviewed_rules(self, chunk_ids: list[str]) -> dict[str, list[dict]]:
        """Approved assertions whose evidence overlaps each child's source spans."""
        if not chunk_ids:
            return {}
        rows = self.conn.execute(text(
            'SELECT DISTINCT sp.chunk_id, a.id, a.assertion_key, a.revision, a.statement'
            ' FROM chunk_spans sp JOIN evidence_spans e ON e.page_revision_id = sp.page_revision_id'
            ' AND e.start_offset < sp.end_offset AND sp.start_offset < e.end_offset'
            ' JOIN assertion_sources src ON src.evidence_id = e.id'
            " JOIN assertions a ON a.id = src.assertion_id AND a.state = 'approved'"
            ' WHERE sp.chunk_id = ANY(CAST(:ids AS uuid[]))'), {'ids': chunk_ids}).mappings()
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(str(r['chunk_id']), []).append(
                {'assertion_id': str(r['id']), 'key': r['assertion_key'],
                 'revision': r['revision'], 'text': r['statement']})
        return out

    def parent_children(self, parent_ids: list[str]) -> dict[str, list[str]]:
        rows = self.conn.execute(text(
            'SELECT parent_id, chunk_id FROM generation_chunks'
            ' WHERE parent_id = ANY(CAST(:ids AS uuid[])) ORDER BY ordinal'),
            {'ids': parent_ids}).all()
        out: dict[str, list[str]] = {}
        for parent_id, chunk_id in rows:
            out.setdefault(str(parent_id), []).append(str(chunk_id))
        return out
