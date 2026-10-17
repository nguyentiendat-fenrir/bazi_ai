"""M001–M003 schema integrity against a real PostgreSQL (raw SQL, no ORM).

Needs ``BAZI_TEST_DATABASE_URL``: libpq conninfo for a server where the user may
create databases, e.g. the dev override of infra/compose.dev.yaml:
    host=127.0.0.1 port=55432 dbname=postgres user=bazi password=<POSTGRES_PASSWORD>
Each run creates throwaway ``bazi_test_*`` databases and drops them.
"""
import hashlib
import os
from pathlib import Path
import unittest
import uuid

try:
    import psycopg
    from psycopg import errors, sql
except ImportError:  # pragma: no cover - psycopg is a locked runtime dependency
    psycopg = None

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get('BAZI_TEST_DATABASE_URL')
TABLES = {
    'users', 'sessions', 'settings', 'model_profiles', 'objects', 'authors', 'books',
    'book_authors', 'book_versions', 'book_access', 'pipeline_profiles', 'generations',
    'pages', 'page_revisions', 'generation_pages', 'blocks', 'sections', 'chunks',
    'chunk_spans', 'generation_chunks', 'search_entries', 'embedding_collections',
    'corpus_releases', 'corpus_members', 'active_corpus',
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def database_url(name: str) -> str:
    return psycopg.conninfo.make_conninfo(ADMIN_URL, dbname=name)


def create_database() -> str:
    name = f'bazi_test_{uuid.uuid4().hex[:12]}'
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    return name


def drop_database(name: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)')
                      .format(sql.Identifier(name)))


def alembic(name: str, action: str, target: str) -> None:
    config = Config(str(ROOT / 'backend' / 'alembic.ini'))
    engine = create_engine('postgresql+psycopg://', poolclass=pool.NullPool,
                           creator=lambda: psycopg.connect(database_url(name)))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        getattr(command, action)(config, target)
    engine.dispose()


DB_NAME = None


def setUpModule():
    global DB_NAME
    if psycopg is None or not ADMIN_URL:
        raise unittest.SkipTest('BAZI_TEST_DATABASE_URL is not set; schema tests need PostgreSQL')
    DB_NAME = create_database()
    try:
        alembic(DB_NAME, 'upgrade', 'head')
    except BaseException:
        # tearDownModule does not run when setUpModule fails.
        drop_database(DB_NAME)
        raise


def tearDownModule():
    if DB_NAME:
        drop_database(DB_NAME)


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


class SchemaTestCase(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(database_url(DB_NAME))
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.f = Factory(self.conn)

    def rejects(self, error, query, *params):
        """Statement must fail with ``error``; a savepoint keeps the test transaction usable."""
        with self.assertRaises(error):
            with self.conn.transaction():
                self.conn.execute(query, params)


class MigrationTests(unittest.TestCase):
    def test_head_creates_contract_tables_and_extensions(self):
        with psycopg.connect(database_url(DB_NAME)) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
            extensions = {r[0] for r in conn.execute('SELECT extname FROM pg_extension')}
            version = conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        self.assertEqual(TABLES, tables - {'alembic_version'})
        self.assertLessEqual({'vector', 'pg_trgm', 'unaccent', 'citext'}, extensions)
        head = ScriptDirectory.from_config(Config(str(ROOT / 'backend' / 'alembic.ini')))
        self.assertEqual(version, head.get_current_head())

    def test_every_foreign_key_is_indexed(self):
        # docs/04: a btree whose leading column is the FK's leading column is enough;
        # composite FKs lead with a uuid that is already selective.
        query = """
        SELECT c.conrelid::regclass::text, c.conname FROM pg_constraint c
        WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace AND NOT EXISTS (
            SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid
              AND (i.indkey::int2[])[0] = c.conkey[1])
        """
        with psycopg.connect(database_url(DB_NAME)) as conn:
            self.assertEqual(conn.execute(query).fetchall(), [])

    def test_downgrade_to_base_and_upgrade_again(self):
        name = create_database()
        try:
            alembic(name, 'upgrade', 'head')
            alembic(name, 'downgrade', 'base')
            with psycopg.connect(database_url(name)) as conn:
                left = conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
                                    " AND tablename <> 'alembic_version'").fetchone()[0]
            self.assertEqual(left, 0)
            alembic(name, 'upgrade', 'head')
        finally:
            drop_database(name)


class LibraryConstraintTests(SchemaTestCase):
    def test_object_sha_is_unique_and_hex(self):
        version = self.f.book_version()
        digest = self.f.one('SELECT o.sha256 FROM objects o JOIN book_versions v'
                            ' ON v.object_id = o.id WHERE v.id = %s', version)
        self.rejects(errors.UniqueViolation, "INSERT INTO objects (sha256, storage_backend,"
                     " object_key, size_bytes, detected_mime, state) VALUES (%s, 'local', 'k2', 1,"
                     " 'x', 'ready')", digest)
        self.rejects(errors.CheckViolation, "INSERT INTO objects (sha256, storage_backend,"
                     " object_key, size_bytes, detected_mime, state) VALUES (%s, 'local', 'k3', 1,"
                     " 'x', 'ready')", 'Z' * 64)

    def test_book_access_needs_exactly_one_grantee(self):
        version = self.f.book_version()
        book = self.f.one('SELECT book_id FROM book_versions WHERE id = %s', version)
        user = self.f.user()
        self.rejects(errors.CheckViolation, "INSERT INTO book_access (book_id, user_id, role_scope,"
                     " permission) VALUES (%s, %s, 'reader', 'read')", book, user)
        self.conn.execute("INSERT INTO book_access (book_id, role_scope, permission)"
                          " VALUES (%s, 'reader', 'read')", (book,))
        self.rejects(errors.UniqueViolation, "INSERT INTO book_access (book_id, role_scope,"
                     " permission) VALUES (%s, 'reader', 'read')", book)

    def test_settings_scope_and_owner_agree(self):
        self.rejects(errors.CheckViolation, "INSERT INTO settings (scope, key, value)"
                     " VALUES ('user', 'k', '1')")
        self.conn.execute("INSERT INTO settings (scope, key, value) VALUES ('system', 'k', '1')")
        self.rejects(errors.UniqueViolation, "INSERT INTO settings (scope, key, value)"
                     " VALUES ('system', 'k', '2')")

    def test_withdrawn_version_requires_timestamp(self):
        version = self.f.book_version()
        self.rejects(errors.CheckViolation,
                     "UPDATE book_versions SET status = 'withdrawn' WHERE id = %s", version)
        self.conn.execute("UPDATE book_versions SET status = 'withdrawn', withdrawn_at = now()"
                          ' WHERE id = %s', (version,))

    def test_updated_at_is_touched(self):
        version = self.f.book_version()
        self.conn.commit()  # now() is per transaction; commit to get a later timestamp
        self.conn.execute("UPDATE book_versions SET edition_label = 'v2' WHERE id = %s", (version,))
        created, updated = self.conn.execute(
            'SELECT created_at, updated_at FROM book_versions WHERE id = %s', (version,)).fetchone()
        self.assertGreater(updated, created)


class SourceTextTests(SchemaTestCase):
    def test_revision_hash_and_lineage(self):
        page = self.f.page(self.f.book_version())
        self.rejects(errors.CheckViolation, 'INSERT INTO page_revisions (page_id, revision_no,'
                     " raw_text, normalized_text, offset_map, layout, text_hash, state)"
                     " VALUES (%s, 1, 'a', 'a', '[]', '{}', %s, 'accepted')", page, sha('b'))
        first = self.f.revision(page)
        self.rejects(errors.CheckViolation, 'INSERT INTO page_revisions (page_id, revision_no,'
                     " raw_text, normalized_text, offset_map, layout, text_hash, state)"
                     " VALUES (%s, 2, 'a', 'a', '[]', '{}', %s, 'accepted')", page, sha('a'))
        other_page = self.f.page(self.f.book_version())
        other = self.f.revision(other_page)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO page_revisions (page_id, revision_no,'
                     " base_revision_id, raw_text, normalized_text, offset_map, layout, text_hash,"
                     " state) VALUES (%s, 2, %s, 'a', 'a', '[]', '{}', %s, 'accepted')",
                     page, other, sha('a'))
        self.f.revision(page, text='sửa OCR', number=2, base=first)

    def test_revision_content_is_immutable_but_state_is_not(self):
        revision = self.f.revision(self.f.page(self.f.book_version()))
        self.rejects(errors.RestrictViolation,
                     "UPDATE page_revisions SET normalized_text = 'khác' WHERE id = %s", revision)
        self.conn.execute("UPDATE page_revisions SET state = 'review_required' WHERE id = %s",
                          (revision,))

    def test_block_offsets_and_bbox(self):
        revision = self.f.revision(self.f.page(self.f.book_version()), text='0123456789')
        self.rejects(errors.CheckViolation, 'INSERT INTO blocks (page_revision_id, ordinal, kind,'
                     " bbox, start_offset, end_offset, text, speaker_layer) VALUES (%s, 0,"
                     " 'paragraph', '[0,0,1,1]', 5, 11, 'x', 'unknown')", revision)
        self.rejects(errors.CheckViolation, 'INSERT INTO blocks (page_revision_id, ordinal, kind,'
                     " bbox, start_offset, end_offset, text, speaker_layer) VALUES (%s, 0,"
                     " 'paragraph', '[0,0,1,1]', 6, 5, 'x', 'unknown')", revision)
        for bad_box in ('[0.5, 0, 0.4, 1]', '[0, 0, 1.2, 1]', '[0, 0, 1]', '{"x": 0}'):
            self.rejects(errors.CheckViolation, 'INSERT INTO blocks (page_revision_id, ordinal,'
                         " kind, bbox, start_offset, end_offset, text, speaker_layer) VALUES (%s,"
                         " 0, 'paragraph', %s, 0, 5, 'x', 'unknown')", revision, bad_box)
        self.f.block(revision, start=0, end=10)


class ChunkSpanTests(SchemaTestCase):
    def setUp(self):
        super().setUp()
        self.revision = self.f.revision(self.f.page(self.f.book_version()))
        self.block = self.f.block(self.revision, start=0, end=10)
        self.chunk = self.f.chunk()

    def test_chunk_hash_must_match_text(self):
        self.rejects(errors.CheckViolation, 'INSERT INTO chunks (content_hash, text, token_count,'
                     " language, kind, speaker_layer, quality_state) VALUES (%s, 'a', 1, 'vi',"
                     " 'text', 'unknown', 'accepted')", sha('b'))

    def test_empty_or_reversed_span_rejected(self):
        self.rejects(errors.CheckViolation, *self.span_sql(start=4, end=4))
        self.rejects(errors.CheckViolation, *self.span_sql(chunk_start=5, chunk_end=2))

    def test_span_outside_block_rejected(self):
        self.rejects(errors.CheckViolation, *self.span_sql(start=5, end=12))

    def test_span_beyond_chunk_text_rejected(self):
        self.rejects(errors.CheckViolation, *self.span_sql(chunk_end=50))

    def test_block_of_another_revision_rejected(self):
        other = self.f.revision(self.f.page(self.f.book_version()))
        self.rejects(errors.ForeignKeyViolation, *self.span_sql(revision=other))

    def test_speaker_change_rejected(self):
        commentary = self.f.block(self.revision, speaker='commentator', ordinal=1)
        self.rejects(errors.CheckViolation, *self.span_sql(block=commentary))

    def test_duplicate_span_ordinal_rejected(self):
        self.f.span(self.chunk, self.revision, self.block)
        self.rejects(errors.UniqueViolation, *self.span_sql())

    def span_sql(self, revision=None, block=None, start=0, end=9, chunk_start=0, chunk_end=9):
        return ('INSERT INTO chunk_spans (chunk_id, page_revision_id, block_id, ordinal,'
                ' start_offset, end_offset, chunk_start, chunk_end)'
                ' VALUES (%s, %s, %s, 0, %s, %s, %s, %s)',
                self.chunk, revision or self.revision, block or self.block,
                start, end, chunk_start, chunk_end)


class GenerationMembershipTests(SchemaTestCase):
    def test_valid_generation_chain_to_active_corpus(self):
        g = self.f.built_generation()
        self.f.generation_chunk(g['generation'], g['chunk'], g['section'])
        self.conn.execute("UPDATE generations SET state = 'ready', manifest_hash = %s"
                          ' WHERE id = %s', (sha('m'), g['generation']))
        release = self.release()
        self.conn.execute('INSERT INTO corpus_members (release_id, book_version_id, generation_id)'
                          ' VALUES (%s, %s, %s)', (release, g['version'], g['generation']))
        self.conn.execute("UPDATE corpus_releases SET state = 'ready', manifest_hash = %s"
                          ' WHERE id = %s', (sha('r'), release))
        self.conn.execute("UPDATE corpus_releases SET state = 'active' WHERE id = %s", (release,))
        self.conn.execute('INSERT INTO active_corpus (release_id) VALUES (%s)', (release,))
        # Frozen once ready: no new members, no retiring the live pointer.
        self.rejects(errors.RestrictViolation, 'DELETE FROM corpus_members WHERE release_id = %s',
                     release)
        self.rejects(errors.RestrictViolation,
                     "UPDATE corpus_releases SET state = 'retired' WHERE id = %s", release)

    def test_duplicate_generation_membership_rejected(self):
        g = self.f.built_generation()
        self.f.generation_chunk(g['generation'], g['chunk'], g['section'])
        self.rejects(errors.UniqueViolation, 'INSERT INTO generation_chunks (generation_id,'
                     ' chunk_id, section_id, ordinal) VALUES (%s, %s, %s, 1)',
                     g['generation'], g['chunk'], g['section'])
        second = self.f.chunk(text='Khách Chủ thứ hai')
        self.f.span(second, g['revision'], g['block'], chunk_end=9)
        self.rejects(errors.UniqueViolation, 'INSERT INTO generation_chunks (generation_id,'
                     ' chunk_id, section_id, ordinal) VALUES (%s, %s, %s, 0)',
                     g['generation'], second, g['section'])
        self.rejects(errors.UniqueViolation, 'INSERT INTO generation_pages (generation_id,'
                     ' page_revision_id, page_id) VALUES (%s, %s, %s)',
                     g['generation'], g['revision'], g['page'])

    def test_generation_page_must_belong_to_version(self):
        g = self.f.built_generation()
        foreign_page = self.f.page(self.f.book_version())
        foreign_revision = self.f.revision(foreign_page)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO generation_pages (generation_id,'
                     ' page_revision_id, page_id) VALUES (%s, %s, %s)',
                     g['generation'], foreign_revision, foreign_page)
        page2 = self.f.page(g['version'], number=2)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO generation_pages (generation_id,'
                     ' page_revision_id, page_id) VALUES (%s, %s, %s)',
                     g['generation'], g['revision'], page2)

    def test_chunk_needs_spans_from_selected_revisions(self):
        g = self.f.built_generation()
        orphan = self.f.chunk(text='không nguồn')
        self.rejects(errors.CheckViolation, 'INSERT INTO generation_chunks (generation_id,'
                     ' chunk_id, section_id, ordinal) VALUES (%s, %s, %s, 1)',
                     g['generation'], orphan, g['section'])
        # A newer revision of the same page that this generation did not select.
        newer = self.f.revision(g['page'], text='Khách Chủ luận đã sửa.', number=2,
                                base=g['revision'])
        newer_block = self.f.block(newer)
        stale = self.f.chunk(text='Khách Chủ sửa')
        self.f.span(stale, newer, newer_block)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO generation_chunks (generation_id,'
                     ' chunk_id, section_id, ordinal) VALUES (%s, %s, %s, 1)',
                     g['generation'], stale, g['section'])

    def test_section_from_other_generation_rejected(self):
        g = self.f.built_generation()
        other = self.f.generation(g['version'])
        foreign_section = self.f.section(other)
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO generation_chunks (generation_id,'
                     ' chunk_id, section_id, ordinal) VALUES (%s, %s, %s, 0)',
                     g['generation'], g['chunk'], foreign_section)
        self.rejects(errors.ForeignKeyViolation, "INSERT INTO sections (generation_id, parent_id,"
                     " title, path, ordinal, speaker_layer) VALUES (%s, %s, 't', '2', 0, 'unknown')",
                     g['generation'], foreign_section)

    def test_ready_generation_is_frozen(self):
        g = self.f.built_generation()
        self.f.generation_chunk(g['generation'], g['chunk'], g['section'])
        self.rejects(errors.CheckViolation,
                     "UPDATE generations SET state = 'ready' WHERE id = %s", g['generation'])
        self.conn.execute("UPDATE generations SET state = 'ready', manifest_hash = %s"
                          ' WHERE id = %s', (sha('m'), g['generation']))
        self.rejects(errors.RestrictViolation, 'DELETE FROM generation_chunks'
                     ' WHERE generation_id = %s', g['generation'])
        self.rejects(errors.RestrictViolation, 'INSERT INTO chunk_spans (chunk_id,'
                     ' page_revision_id, block_id, ordinal, start_offset, end_offset, chunk_start,'
                     ' chunk_end) VALUES (%s, %s, %s, 1, 0, 2, 0, 2)',
                     g['chunk'], g['revision'], g['block'])
        self.rejects(errors.CheckViolation,
                     "UPDATE generations SET state = 'building' WHERE id = %s", g['generation'])

    def test_release_members_need_ready_generation_of_same_version(self):
        g = self.f.built_generation()
        release = self.release()
        self.rejects(errors.CheckViolation, 'INSERT INTO corpus_members (release_id,'
                     ' book_version_id, generation_id) VALUES (%s, %s, %s)',
                     release, g['version'], g['generation'])
        self.f.generation_chunk(g['generation'], g['chunk'], g['section'])
        self.conn.execute("UPDATE generations SET state = 'ready', manifest_hash = %s"
                          ' WHERE id = %s', (sha('m'), g['generation']))
        other_version = self.f.book_version()
        self.rejects(errors.ForeignKeyViolation, 'INSERT INTO corpus_members (release_id,'
                     ' book_version_id, generation_id) VALUES (%s, %s, %s)',
                     release, other_version, g['generation'])
        self.rejects(errors.CheckViolation, 'INSERT INTO active_corpus (release_id) VALUES (%s)',
                     release)

    def test_embedding_collection_matches_profile(self):
        profile = self.f.embedding_profile(dimension=768)
        self.rejects(errors.CheckViolation, 'INSERT INTO embedding_collections (profile_id,'
                     " dimension, distance, physical_table, state) VALUES (%s, 1024, 'cosine',"
                     " 'embeddings_e5', 'provisioning')", profile)
        self.rejects(errors.CheckViolation, 'INSERT INTO embedding_collections (profile_id,'
                     " dimension, distance, physical_table, state) VALUES (%s, 768, 'cosine',"
                     " 'embeddings; DROP TABLE x', 'provisioning')", profile)

    def release(self):
        profile = self.f.embedding_profile()
        collection = self.f.one('INSERT INTO embedding_collections (profile_id, dimension,'
                                " distance, physical_table, state) VALUES (%s, 4, 'cosine', %s,"
                                " 'ready') RETURNING id", profile,
                                f'embeddings_{uuid.uuid4().hex[:8]}')
        return self.f.one('INSERT INTO corpus_releases (embedding_collection_id,'
                          " ontology_release_id, lexical_profile_version) VALUES (%s, %s, 'fts1')"
                          ' RETURNING id', collection, uuid.uuid4())


if __name__ == '__main__':
    unittest.main()
