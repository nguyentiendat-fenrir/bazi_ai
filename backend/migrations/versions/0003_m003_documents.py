"""M003 pipeline profiles, pages/revisions/blocks, generations, chunks, search, releases.

Integrity lives in the database (docs/04 · Quan hệ, invariants): composite
foreign keys keep revisions/blocks/sections/generations inside their parent;
triggers check offsets against source text, generation membership against the
generation's book version, and lock memberships once a generation or release
leaves its building state. Content tables are insert-only.

FKs to tables of later migrations are added there: sections.school_id → schools
and corpus_releases.ontology_release_id → ontology_releases (T005).

Revision ID: 0003_m003_documents
Revises: 0002_m002_library
"""
from alembic import op

revision = '0003_m003_documents'
down_revision = '0002_m002_library'
branch_labels = None
depends_on = None

SPEAKER = "('original_author', 'commentator', 'translator', 'editor', 'unknown')"
QUALITY = "('accepted', 'review_required', 'excluded')"


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def create_table(name: str, columns: str) -> None:
    run(f"""
    CREATE TABLE {name} (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        {columns}
    );
    CREATE TRIGGER {name}_touch BEFORE UPDATE ON {name}
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    """)


def immutable(table: str, *columns: str) -> None:
    cols = ', '.join(f"'{c}'" for c in columns)
    run(f"""
    CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table}
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable({cols});
    """)


def upgrade() -> None:
    run("""
    CREATE FUNCTION bazi_valid_bbox(box jsonb) RETURNS boolean
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
        SELECT box IS NULL OR jsonb_typeof(box) = 'null' OR (
            jsonb_typeof(box) = 'array' AND jsonb_array_length(box) = 4
            AND (SELECT bool_and(jsonb_typeof(v) = 'number'
                                 AND (v #>> '{}')::numeric BETWEEN 0 AND 1)
                 FROM jsonb_array_elements(box) AS v)
            AND (box ->> 0)::numeric <= (box ->> 2)::numeric
            AND (box ->> 1)::numeric <= (box ->> 3)::numeric)
    $$;
    """)

    # ---- profiles and generations -------------------------------------------------
    create_table('pipeline_profiles', """
        name text NOT NULL,
        parser_version text NOT NULL,
        chunker_version text NOT NULL,
        normalizer_version text NOT NULL,
        renderer_version text,
        embedding_profile_id uuid NOT NULL REFERENCES model_profiles,
        config jsonb NOT NULL DEFAULT '{}',
        config_hash sha256_hex NOT NULL UNIQUE
    """)
    immutable('pipeline_profiles', 'name', 'parser_version', 'chunker_version',
              'normalizer_version', 'renderer_version', 'embedding_profile_id',
              'config', 'config_hash')
    run("""
    CREATE INDEX pipeline_profiles_embedding_profile_id_idx
        ON pipeline_profiles (embedding_profile_id);

    CREATE FUNCTION bazi_check_embedding_profile() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        profile model_profiles;
        profile_id uuid := to_jsonb(NEW) ->> TG_ARGV[0];
    BEGIN
        SELECT * INTO profile FROM model_profiles WHERE id = profile_id;
        IF profile.kind IS DISTINCT FROM 'embedding' THEN
            RAISE EXCEPTION '%.% must reference an embedding profile', TG_TABLE_NAME, TG_ARGV[0]
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        -- Read via jsonb: pipeline_profiles has no dimension column and PL/pgSQL
        -- does not short-circuit field resolution.
        IF TG_TABLE_NAME = 'embedding_collections'
                AND profile.dimension <> (to_jsonb(NEW) ->> 'dimension')::integer THEN
            RAISE EXCEPTION 'collection dimension % differs from profile dimension %',
                to_jsonb(NEW) ->> 'dimension', profile.dimension USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;

    CREATE TRIGGER pipeline_profiles_embedding_kind BEFORE INSERT ON pipeline_profiles
        FOR EACH ROW EXECUTE FUNCTION bazi_check_embedding_profile('embedding_profile_id');
    """)

    create_table('generations', """
        book_version_id uuid NOT NULL REFERENCES book_versions,
        pipeline_profile_id uuid NOT NULL REFERENCES pipeline_profiles,
        base_generation_id uuid,
        state text NOT NULL DEFAULT 'building' CHECK (state IN
            ('building', 'ready', 'published', 'superseded', 'withdrawn')),
        manifest_hash sha256_hex,
        coverage jsonb NOT NULL DEFAULT '{}',
        UNIQUE (id, book_version_id),
        FOREIGN KEY (base_generation_id, book_version_id)
            REFERENCES generations (id, book_version_id),
        CHECK (base_generation_id <> id),
        CHECK (state IN ('building', 'withdrawn') OR manifest_hash IS NOT NULL)
    """)
    immutable('generations', 'book_version_id', 'pipeline_profile_id', 'base_generation_id')
    run("""
    CREATE INDEX generations_book_version_state_idx ON generations (book_version_id, state);
    CREATE INDEX generations_pipeline_profile_id_idx ON generations (pipeline_profile_id);
    CREATE INDEX generations_base_generation_id_idx ON generations (base_generation_id);

    CREATE FUNCTION bazi_generation_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state IS DISTINCT FROM OLD.state AND (OLD.state, NEW.state) NOT IN (
            ('building', 'ready'), ('building', 'withdrawn'),
            ('ready', 'published'), ('ready', 'superseded'), ('ready', 'withdrawn'),
            ('published', 'superseded'), ('published', 'withdrawn'),
            ('superseded', 'withdrawn')) THEN
            RAISE EXCEPTION 'generation state % -> % is not allowed', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.state <> 'building' AND NEW.manifest_hash IS DISTINCT FROM OLD.manifest_hash THEN
            RAISE EXCEPTION 'generation manifest is frozen after building'
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER generations_transition BEFORE UPDATE ON generations
        FOR EACH ROW EXECUTE FUNCTION bazi_generation_transition();

    -- Membership tables only change while their generation is building.
    CREATE FUNCTION bazi_generation_building() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        target uuid := CASE WHEN TG_OP = 'DELETE' THEN OLD.generation_id
                            ELSE NEW.generation_id END;
        current_state text;
    BEGIN
        SELECT state INTO current_state FROM generations WHERE id = target FOR SHARE;
        IF current_state IS DISTINCT FROM 'building' THEN
            RAISE EXCEPTION '% of generation % is frozen (state %)',
                TG_TABLE_NAME, target, current_state USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END $$;
    """)

    # ---- pages, revisions, blocks -------------------------------------------------
    create_table('pages', """
        book_version_id uuid NOT NULL REFERENCES book_versions,
        physical_page_number integer NOT NULL CHECK (physical_page_number >= 1),
        page_kind text NOT NULL CHECK (page_kind IN
            ('pdf_page', 'docx_rendered_page', 'docx_anchor')),
        source_anchor jsonb,
        UNIQUE (book_version_id, physical_page_number, page_kind),
        UNIQUE (id, book_version_id)
    """)
    immutable('pages', 'book_version_id', 'physical_page_number', 'page_kind', 'source_anchor')

    create_table('page_revisions', f"""
        page_id uuid NOT NULL REFERENCES pages,
        revision_no integer NOT NULL CHECK (revision_no >= 1),
        base_revision_id uuid,
        raw_text text NOT NULL,
        normalized_text text NOT NULL,
        offset_map jsonb NOT NULL,
        layout jsonb NOT NULL,
        printed_page_label text,
        printed_label_verified boolean NOT NULL DEFAULT false,
        text_hash sha256_hex NOT NULL,
        quality jsonb NOT NULL DEFAULT '{{}}',
        state text NOT NULL CHECK (state IN {QUALITY}),
        rendered_object_id uuid REFERENCES objects,
        UNIQUE (page_id, revision_no),
        UNIQUE (id, page_id),
        FOREIGN KEY (base_revision_id, page_id) REFERENCES page_revisions (id, page_id),
        CHECK (base_revision_id <> id),
        CHECK ((revision_no = 1) = (base_revision_id IS NULL)),
        CHECK (text_hash = bazi_sha256_text(normalized_text))
    """)
    immutable('page_revisions', 'page_id', 'revision_no', 'base_revision_id', 'raw_text',
              'normalized_text', 'offset_map', 'layout', 'printed_page_label', 'text_hash',
              'rendered_object_id')
    run("""
    CREATE INDEX page_revisions_base_revision_id_idx ON page_revisions (base_revision_id);
    CREATE INDEX page_revisions_rendered_object_id_idx ON page_revisions (rendered_object_id);
    """)

    create_table('blocks', f"""
        page_revision_id uuid NOT NULL REFERENCES page_revisions,
        ordinal integer NOT NULL CHECK (ordinal >= 0),
        kind text NOT NULL CHECK (kind IN ('paragraph', 'heading', 'table', 'figure', 'caption')),
        bbox jsonb NOT NULL CHECK (bazi_valid_bbox(bbox)),
        start_offset integer NOT NULL,
        end_offset integer NOT NULL,
        text text NOT NULL,
        table_cells jsonb,
        speaker_layer text NOT NULL CHECK (speaker_layer IN {SPEAKER}),
        attributes jsonb NOT NULL DEFAULT '{{}}',
        UNIQUE (page_revision_id, ordinal),
        UNIQUE (id, page_revision_id),
        CHECK (0 <= start_offset AND start_offset <= end_offset)
    """)
    immutable('blocks', 'page_revision_id', 'ordinal', 'kind', 'bbox', 'start_offset',
              'end_offset', 'text', 'table_cells', 'speaker_layer', 'attributes')
    run("""
    CREATE FUNCTION bazi_check_block() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        text_length integer;
    BEGIN
        SELECT char_length(normalized_text) INTO text_length
            FROM page_revisions WHERE id = NEW.page_revision_id;
        IF NEW.end_offset > text_length THEN
            RAISE EXCEPTION 'block offsets [%,%) exceed revision text length %',
                NEW.start_offset, NEW.end_offset, text_length USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER blocks_offsets BEFORE INSERT ON blocks
        FOR EACH ROW EXECUTE FUNCTION bazi_check_block();
    """)

    create_table('generation_pages', """
        generation_id uuid NOT NULL REFERENCES generations,
        page_revision_id uuid NOT NULL,
        page_id uuid NOT NULL REFERENCES pages,
        UNIQUE (generation_id, page_id),
        FOREIGN KEY (page_revision_id, page_id) REFERENCES page_revisions (id, page_id)
    """)
    immutable('generation_pages', 'generation_id', 'page_revision_id', 'page_id')
    run("""
    CREATE INDEX generation_pages_page_revision_id_idx ON generation_pages (page_revision_id);
    CREATE INDEX generation_pages_page_id_idx ON generation_pages (page_id);

    CREATE FUNCTION bazi_check_generation_page() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pages p JOIN generations g
                       ON g.book_version_id = p.book_version_id
                       WHERE p.id = NEW.page_id AND g.id = NEW.generation_id) THEN
            RAISE EXCEPTION 'page % is not in the book version of generation %',
                NEW.page_id, NEW.generation_id USING ERRCODE = 'foreign_key_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER generation_pages_version BEFORE INSERT ON generation_pages
        FOR EACH ROW EXECUTE FUNCTION bazi_check_generation_page();
    CREATE TRIGGER generation_pages_building BEFORE INSERT OR UPDATE OR DELETE ON generation_pages
        FOR EACH ROW EXECUTE FUNCTION bazi_generation_building();
    """)

    # ---- sections and chunks ------------------------------------------------------
    create_table('sections', f"""
        generation_id uuid NOT NULL REFERENCES generations,
        parent_id uuid,
        title text NOT NULL,
        path text NOT NULL,
        ordinal integer NOT NULL CHECK (ordinal >= 0),
        speaker_layer text NOT NULL CHECK (speaker_layer IN {SPEAKER}),
        school_id uuid,
        UNIQUE (generation_id, path),
        UNIQUE (id, generation_id),
        FOREIGN KEY (parent_id, generation_id) REFERENCES sections (id, generation_id),
        CHECK (parent_id <> id)
    """)
    immutable('sections', 'generation_id', 'parent_id', 'title', 'path', 'ordinal',
              'speaker_layer', 'school_id')
    run("""
    CREATE INDEX sections_parent_id_idx ON sections (parent_id);
    CREATE INDEX sections_school_id_idx ON sections (school_id);
    """)

    create_table('chunks', f"""
        content_hash sha256_hex NOT NULL,
        text text NOT NULL,
        token_count integer NOT NULL CHECK (token_count >= 0),
        language text NOT NULL,
        kind text NOT NULL CHECK (kind IN ('text', 'table', 'case')),
        speaker_layer text NOT NULL CHECK (speaker_layer IN {SPEAKER}),
        quality_state text NOT NULL CHECK (quality_state IN {QUALITY}),
        CHECK (content_hash = bazi_sha256_text(text))
    """)
    immutable('chunks', 'content_hash', 'text', 'token_count', 'language', 'kind',
              'speaker_layer', 'quality_state')
    run('CREATE INDEX chunks_content_hash_idx ON chunks (content_hash);')

    create_table('chunk_spans', """
        chunk_id uuid NOT NULL REFERENCES chunks,
        page_revision_id uuid NOT NULL,
        block_id uuid NOT NULL,
        ordinal integer NOT NULL CHECK (ordinal >= 0),
        start_offset integer NOT NULL,
        end_offset integer NOT NULL,
        bbox jsonb CHECK (bazi_valid_bbox(bbox)),
        chunk_start integer NOT NULL,
        chunk_end integer NOT NULL,
        UNIQUE (chunk_id, ordinal),
        FOREIGN KEY (block_id, page_revision_id) REFERENCES blocks (id, page_revision_id),
        CHECK (0 <= start_offset AND start_offset < end_offset),
        CHECK (0 <= chunk_start AND chunk_start < chunk_end)
    """)
    immutable('chunk_spans', 'chunk_id', 'page_revision_id', 'block_id', 'ordinal',
              'start_offset', 'end_offset', 'bbox', 'chunk_start', 'chunk_end')
    run("""
    CREATE INDEX chunk_spans_page_revision_id_idx ON chunk_spans (page_revision_id);
    CREATE INDEX chunk_spans_block_id_idx ON chunk_spans (block_id);

    CREATE FUNCTION bazi_check_chunk_span() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        blk blocks;
        chk chunks;
    BEGIN
        SELECT * INTO blk FROM blocks WHERE id = NEW.block_id;
        SELECT * INTO chk FROM chunks WHERE id = NEW.chunk_id FOR SHARE;
        IF NEW.start_offset < blk.start_offset OR NEW.end_offset > blk.end_offset THEN
            RAISE EXCEPTION 'span [%,%) is outside block [%,%)', NEW.start_offset,
                NEW.end_offset, blk.start_offset, blk.end_offset USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.chunk_end > char_length(chk.text) THEN
            RAISE EXCEPTION 'span chunk range [%,%) exceeds chunk text length %',
                NEW.chunk_start, NEW.chunk_end, char_length(chk.text)
                USING ERRCODE = 'check_violation';
        END IF;
        IF blk.speaker_layer <> chk.speaker_layer THEN
            RAISE EXCEPTION 'span speaker % differs from chunk speaker %',
                blk.speaker_layer, chk.speaker_layer USING ERRCODE = 'check_violation';
        END IF;
        IF EXISTS (SELECT 1 FROM generation_chunks WHERE chunk_id = NEW.chunk_id) THEN
            RAISE EXCEPTION 'chunk % already belongs to a generation; spans are frozen',
                NEW.chunk_id USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
    END $$;
    """)

    create_table('generation_chunks', """
        generation_id uuid NOT NULL REFERENCES generations,
        chunk_id uuid NOT NULL REFERENCES chunks,
        section_id uuid NOT NULL,
        ordinal integer NOT NULL CHECK (ordinal >= 0),
        UNIQUE (generation_id, ordinal),
        UNIQUE (generation_id, chunk_id),
        FOREIGN KEY (section_id, generation_id) REFERENCES sections (id, generation_id)
    """)
    immutable('generation_chunks', 'generation_id', 'chunk_id', 'section_id', 'ordinal')
    run("""
    CREATE INDEX generation_chunks_chunk_id_idx ON generation_chunks (chunk_id);
    CREATE INDEX generation_chunks_section_id_idx ON generation_chunks (section_id);

    -- Defined after generation_chunks exists because the span check reads it.
    CREATE TRIGGER chunk_spans_check BEFORE INSERT ON chunk_spans
        FOR EACH ROW EXECUTE FUNCTION bazi_check_chunk_span();

    -- A chunk joins a generation only if it has provenance and every span points
    -- at the page revision that generation selected.
    CREATE FUNCTION bazi_check_generation_chunk() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM chunk_spans WHERE chunk_id = NEW.chunk_id) THEN
            RAISE EXCEPTION 'chunk % has no source spans', NEW.chunk_id
                USING ERRCODE = 'check_violation';
        END IF;
        IF EXISTS (SELECT 1 FROM chunk_spans s
                   WHERE s.chunk_id = NEW.chunk_id AND NOT EXISTS (
                       SELECT 1 FROM generation_pages gp
                       WHERE gp.generation_id = NEW.generation_id
                         AND gp.page_revision_id = s.page_revision_id)) THEN
            RAISE EXCEPTION 'chunk % cites page revisions outside generation %',
                NEW.chunk_id, NEW.generation_id USING ERRCODE = 'foreign_key_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER generation_chunks_sources BEFORE INSERT ON generation_chunks
        FOR EACH ROW EXECUTE FUNCTION bazi_check_generation_chunk();
    CREATE TRIGGER generation_chunks_building BEFORE INSERT OR UPDATE OR DELETE
        ON generation_chunks FOR EACH ROW EXECUTE FUNCTION bazi_generation_building();
    """)

    # ---- lexical and vector indexes ----------------------------------------------
    create_table('search_entries', """
        chunk_id uuid NOT NULL REFERENCES chunks,
        lexical_profile_version text NOT NULL,
        text_nfc text NOT NULL,
        text_folded text NOT NULL,
        ts_nfc tsvector NOT NULL,
        ts_folded tsvector NOT NULL,
        UNIQUE (chunk_id, lexical_profile_version)
    """)
    run("""
    CREATE INDEX search_entries_ts_nfc_idx ON search_entries USING gin (ts_nfc);
    CREATE INDEX search_entries_ts_folded_idx ON search_entries USING gin (ts_folded);
    CREATE INDEX search_entries_text_folded_trgm_idx ON search_entries
        USING gin (text_folded gin_trgm_ops);
    """)

    # Physical embeddings_<collection> tables are provisioned by the registry (T016).
    create_table('embedding_collections', """
        profile_id uuid NOT NULL UNIQUE REFERENCES model_profiles,
        dimension integer NOT NULL CHECK (dimension > 0),
        distance text NOT NULL CHECK (distance IN ('cosine', 'l2', 'inner_product')),
        physical_table text NOT NULL UNIQUE CHECK (physical_table ~ '^embeddings_[a-z0-9_]{1,40}$'),
        state text NOT NULL CHECK (state IN ('provisioning', 'ready', 'retired'))
    """)
    immutable('embedding_collections', 'profile_id', 'dimension', 'distance', 'physical_table')
    run("""
    CREATE TRIGGER embedding_collections_profile BEFORE INSERT ON embedding_collections
        FOR EACH ROW EXECUTE FUNCTION bazi_check_embedding_profile('profile_id');
    """)

    # ---- corpus releases ----------------------------------------------------------
    create_table('corpus_releases', """
        parent_id uuid REFERENCES corpus_releases,
        embedding_collection_id uuid NOT NULL REFERENCES embedding_collections,
        ontology_release_id uuid NOT NULL,
        lexical_profile_version text NOT NULL,
        state text NOT NULL DEFAULT 'building' CHECK (state IN
            ('building', 'ready', 'active', 'retired')),
        manifest_hash sha256_hex,
        CHECK (parent_id <> id),
        CHECK (state IN ('building', 'retired') OR manifest_hash IS NOT NULL)
    """)
    immutable('corpus_releases', 'parent_id', 'embedding_collection_id', 'ontology_release_id',
              'lexical_profile_version')
    run("""
    CREATE INDEX corpus_releases_state_idx ON corpus_releases (state);
    CREATE INDEX corpus_releases_parent_id_idx ON corpus_releases (parent_id);
    CREATE INDEX corpus_releases_embedding_collection_id_idx
        ON corpus_releases (embedding_collection_id);
    CREATE INDEX corpus_releases_ontology_release_id_idx ON corpus_releases (ontology_release_id);

    CREATE FUNCTION bazi_release_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state IS DISTINCT FROM OLD.state AND (OLD.state, NEW.state) NOT IN (
            ('building', 'ready'), ('building', 'retired'), ('ready', 'active'),
            ('ready', 'retired'), ('active', 'retired')) THEN
            RAISE EXCEPTION 'release state % -> % is not allowed', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.state <> 'building' AND NEW.manifest_hash IS DISTINCT FROM OLD.manifest_hash THEN
            RAISE EXCEPTION 'release manifest is frozen after building'
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF OLD.state = 'active' AND EXISTS (
                SELECT 1 FROM active_corpus WHERE release_id = OLD.id) THEN
            RAISE EXCEPTION 'release % is the active pointer; swap the pointer first', OLD.id
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
    END $$;
    """)

    create_table('corpus_members', """
        release_id uuid NOT NULL REFERENCES corpus_releases,
        book_version_id uuid NOT NULL REFERENCES book_versions,
        generation_id uuid NOT NULL,
        UNIQUE (release_id, book_version_id),
        FOREIGN KEY (generation_id, book_version_id) REFERENCES generations (id, book_version_id)
    """)
    immutable('corpus_members', 'release_id', 'book_version_id', 'generation_id')
    run("""
    CREATE INDEX corpus_members_release_generation_idx ON corpus_members (release_id, generation_id);
    CREATE INDEX corpus_members_book_version_id_idx ON corpus_members (book_version_id);
    CREATE INDEX corpus_members_generation_id_idx ON corpus_members (generation_id);

    CREATE FUNCTION bazi_check_corpus_member() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        row_ corpus_members := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        release_state text;
        generation_state text;
    BEGIN
        SELECT state INTO release_state FROM corpus_releases WHERE id = row_.release_id FOR SHARE;
        IF release_state IS DISTINCT FROM 'building' THEN
            RAISE EXCEPTION 'members of release % are frozen (state %)',
                row_.release_id, release_state USING ERRCODE = 'restrict_violation';
        END IF;
        IF TG_OP <> 'DELETE' THEN
            SELECT state INTO generation_state FROM generations WHERE id = NEW.generation_id
                FOR SHARE;
            IF generation_state NOT IN ('ready', 'published') THEN
                RAISE EXCEPTION 'generation % is % and cannot join a release',
                    NEW.generation_id, generation_state USING ERRCODE = 'check_violation';
            END IF;
        END IF;
        RETURN row_;
    END $$;
    CREATE TRIGGER corpus_members_check BEFORE INSERT OR UPDATE OR DELETE ON corpus_members
        FOR EACH ROW EXECUTE FUNCTION bazi_check_corpus_member();
    """)

    create_table('active_corpus', """
        slot text NOT NULL UNIQUE DEFAULT 'default',
        release_id uuid NOT NULL REFERENCES corpus_releases,
        visibility_epoch bigint NOT NULL DEFAULT 0 CHECK (visibility_epoch >= 0)
    """)
    run("""
    CREATE INDEX active_corpus_release_id_idx ON active_corpus (release_id);

    CREATE FUNCTION bazi_check_active_corpus() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF (SELECT state FROM corpus_releases WHERE id = NEW.release_id FOR SHARE)
                IS DISTINCT FROM 'active' THEN
            RAISE EXCEPTION 'active pointer must reference an active release'
                USING ERRCODE = 'check_violation';
        END IF;
        IF TG_OP = 'UPDATE' AND NEW.visibility_epoch < OLD.visibility_epoch THEN
            RAISE EXCEPTION 'visibility_epoch never decreases' USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER active_corpus_check BEFORE INSERT OR UPDATE ON active_corpus
        FOR EACH ROW EXECUTE FUNCTION bazi_check_active_corpus();

    -- Created last: the transition check reads active_corpus.
    CREATE TRIGGER corpus_releases_transition BEFORE UPDATE ON corpus_releases
        FOR EACH ROW EXECUTE FUNCTION bazi_release_transition();
    """)


def downgrade() -> None:
    run("""
    DROP TABLE active_corpus, corpus_members, corpus_releases, embedding_collections,
        search_entries, generation_chunks, chunk_spans, chunks, sections, generation_pages,
        blocks, page_revisions, pages, generations, pipeline_profiles;
    DROP FUNCTION bazi_check_active_corpus(), bazi_check_corpus_member(),
        bazi_release_transition(), bazi_check_generation_chunk(), bazi_check_chunk_span(),
        bazi_check_generation_page(), bazi_check_block(), bazi_generation_building(),
        bazi_generation_transition(), bazi_check_embedding_profile(), bazi_valid_bbox(jsonb);
    """)
