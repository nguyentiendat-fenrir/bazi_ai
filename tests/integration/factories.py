"""Minimal valid rows for schema tests (raw SQL)."""
import uuid

from tests.integration.db import sha


class Factory:
    """Minimal valid rows; every helper returns the new id."""

    def __init__(self, conn):
        self.conn = conn

    def one(self, query, *params):
        return self.conn.execute(query, params).fetchone()[0]

    def user(self):
        return self.one("INSERT INTO users (email, password_hash, role) VALUES (%s, 'x', 'admin')"
                        ' RETURNING id', f'{uuid.uuid4().hex}@example.test')

    def book_version(self, user=None):
        user = user or self.user()
        digest = sha(uuid.uuid4().hex)
        obj = self.one("INSERT INTO objects (sha256, storage_backend, object_key, size_bytes,"
                       " detected_mime, state) VALUES (%s, 'local', %s, 10, 'application/pdf',"
                       " 'ready') RETURNING id", digest, f'objects/{digest}')
        book = self.one("INSERT INTO books (title, normalized_title, language, created_by)"
                        " VALUES ('Sơ cấp', 'so cap', 'vi', %s) RETURNING id", user)
        return self.one("INSERT INTO book_versions (book_id, object_id, edition_label, version_no,"
                        " rights_status, uploaded_by) VALUES (%s, %s, 'v1', 1, 'private_reference',"
                        ' %s) RETURNING id', book, obj, user)

    def embedding_profile(self, dimension=4):
        return self.one("INSERT INTO model_profiles (kind, provider, model_name, model_revision,"
                        " dimension, profile_hash) VALUES ('embedding', 'local', 'e5', 'r1', %s, %s)"
                        ' RETURNING id', dimension, sha(uuid.uuid4().hex))

    def generation(self, version, state='building'):
        profile = self.one("INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                           " normalizer_version, embedding_profile_id, config_hash)"
                           " VALUES ('p', '1', '1', '1', %s, %s) RETURNING id",
                           self.embedding_profile(), sha(uuid.uuid4().hex))
        manifest = None if state == 'building' else sha('manifest')
        return self.one('INSERT INTO generations (book_version_id, pipeline_profile_id, state,'
                        ' manifest_hash) VALUES (%s, %s, %s, %s) RETURNING id',
                        version, profile, state, manifest)

    def page(self, version, number=1):
        return self.one("INSERT INTO pages (book_version_id, physical_page_number, page_kind)"
                        " VALUES (%s, %s, 'pdf_page') RETURNING id", version, number)

    def revision(self, page, text='Khách Chủ luận theo can ngày.', number=1, base=None):
        return self.one('INSERT INTO page_revisions (page_id, revision_no, base_revision_id,'
                        " raw_text, normalized_text, offset_map, layout, text_hash, state)"
                        " VALUES (%s, %s, %s, %s, %s, '[]', '{}', %s, 'accepted') RETURNING id",
                        page, number, base, text, text, sha(text))

    def block(self, revision, start=0, end=10, speaker='original_author', ordinal=0,
              bbox='[0.1, 0.1, 0.9, 0.2]'):
        return self.one('INSERT INTO blocks (page_revision_id, ordinal, kind, bbox, start_offset,'
                        " end_offset, text, speaker_layer) VALUES (%s, %s, 'paragraph', %s, %s, %s,"
                        " 'x', %s) RETURNING id", revision, ordinal, bbox, start, end, speaker)

    def chunk(self, text='Khách Chủ', speaker='original_author'):
        return self.one('INSERT INTO chunks (content_hash, text, token_count, language, kind,'
                        " speaker_layer, quality_state) VALUES (%s, %s, 3, 'vi', 'text', %s,"
                        " 'accepted') RETURNING id", sha(text), text, speaker)

    def span(self, chunk, revision, block, start=0, end=9, chunk_start=0, chunk_end=9, ordinal=0):
        return self.one('INSERT INTO chunk_spans (chunk_id, page_revision_id, block_id, ordinal,'
                        ' start_offset, end_offset, chunk_start, chunk_end)'
                        ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id',
                        chunk, revision, block, ordinal, start, end, chunk_start, chunk_end)

    def section(self, generation, path='1', parent=None):
        return self.one('INSERT INTO sections (generation_id, parent_id, title, path, ordinal,'
                        " speaker_layer) VALUES (%s, %s, 'Chương 1', %s, 0, 'original_author')"
                        ' RETURNING id', generation, parent, path)

    def generation_page(self, generation, revision, page):
        return self.one('INSERT INTO generation_pages (generation_id, page_revision_id, page_id)'
                        ' VALUES (%s, %s, %s) RETURNING id', generation, revision, page)

    def generation_chunk(self, generation, chunk, section, ordinal=0):
        return self.one('INSERT INTO generation_chunks (generation_id, chunk_id, section_id,'
                        ' ordinal) VALUES (%s, %s, %s, %s) RETURNING id',
                        generation, chunk, section, ordinal)

    def built_generation(self):
        """A building generation with one page, block, chunk with span and section."""
        version = self.book_version()
        generation = self.generation(version)
        page = self.page(version)
        revision = self.revision(page)
        block = self.block(revision)
        chunk = self.chunk()
        self.span(chunk, revision, block)
        self.generation_page(generation, revision, page)
        section = self.section(generation)
        return dict(version=version, generation=generation, page=page, revision=revision,
                    block=block, chunk=chunk, section=section)
