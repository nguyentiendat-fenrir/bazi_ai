"""M018 parent/child chunks, chunk metadata, evaluation runs and judge scores.

RAG pilot (chunker-3): children stay in ``chunks`` (embedded, retrieved, exact
spans); parents are the section-shaped text the LLM reads. A child's parent is
a property of the generation (``generation_chunks.parent_id``) because one
chunk row is shared by every generation that produced identical text and spans.
``chunk_meta`` holds per-generation metadata and the context header of each
child; ``chunk_parents.summary`` is filled by the ``summarize`` stage while the
generation is still building. Lists become their own chunk kind.

Evaluation of the pilot by people: ``eval_runs``/``eval_results`` keep every
answer with the full retrieval snapshot; ``judge_scores`` keep one score sheet
per judge (by name — judges share a password, they have no accounts) and result.

Revision ID: 0018_m018_rag_parents
Revises: 0017_m017_feedback
"""
from alembic import op

revision = '0018_m018_rag_parents'
down_revision = '0017_m017_feedback'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    ALTER TABLE chunks DROP CONSTRAINT chunks_kind_check;
    ALTER TABLE chunks ADD CONSTRAINT chunks_kind_check
        CHECK (kind IN ('text', 'list', 'table', 'case'));

    CREATE TABLE chunk_parents (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        generation_id uuid NOT NULL REFERENCES generations,
        section_id uuid REFERENCES sections,
        ordinal integer NOT NULL CHECK (ordinal >= 0),
        text text NOT NULL,
        token_count integer NOT NULL CHECK (token_count >= 0),
        content_hash sha256_hex NOT NULL,
        meta jsonb NOT NULL DEFAULT '{}',
        summary text,
        summary_status text NOT NULL DEFAULT 'pending'
            CHECK (summary_status IN ('pending', 'done', 'failed', 'skipped')),
        summary_model text,
        summary_prompt_version text,
        UNIQUE (generation_id, ordinal),
        CHECK (content_hash = bazi_sha256_text(text))
    );
    CREATE INDEX chunk_parents_section_id_idx ON chunk_parents (section_id);
    CREATE INDEX chunk_parents_content_hash_idx ON chunk_parents (content_hash);
    CREATE TRIGGER chunk_parents_touch BEFORE UPDATE ON chunk_parents
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    -- Text and membership are frozen; only the summary columns change, while building.
    CREATE TRIGGER chunk_parents_immutable BEFORE UPDATE ON chunk_parents
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable(
            'generation_id', 'section_id', 'ordinal', 'text', 'token_count', 'content_hash', 'meta');
    CREATE TRIGGER chunk_parents_building BEFORE INSERT OR UPDATE OR DELETE ON chunk_parents
        FOR EACH ROW EXECUTE FUNCTION bazi_generation_building();

    ALTER TABLE generation_chunks ADD COLUMN parent_id uuid REFERENCES chunk_parents;
    CREATE INDEX generation_chunks_parent_id_idx ON generation_chunks (parent_id);

    CREATE TABLE chunk_meta (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        generation_id uuid NOT NULL REFERENCES generations,
        chunk_id uuid NOT NULL REFERENCES chunks,
        meta jsonb NOT NULL,
        UNIQUE (generation_id, chunk_id)
    );
    CREATE INDEX chunk_meta_chunk_id_idx ON chunk_meta (chunk_id);
    CREATE TRIGGER chunk_meta_building BEFORE INSERT OR UPDATE OR DELETE ON chunk_meta
        FOR EACH ROW EXECUTE FUNCTION bazi_generation_building();

    CREATE TABLE eval_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        label text NOT NULL CHECK (char_length(label) BETWEEN 1 AND 200),
        questions_file text,
        settings jsonb NOT NULL DEFAULT '{}',
        versions jsonb NOT NULL DEFAULT '{}',
        created_by uuid REFERENCES users
    );
    CREATE TABLE eval_results (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        run_id uuid NOT NULL REFERENCES eval_runs ON DELETE CASCADE,
        ordinal integer NOT NULL CHECK (ordinal >= 1),
        question_key text NOT NULL,
        question text NOT NULL,
        status text NOT NULL,
        answer text,
        latency_ms integer,
        payload jsonb NOT NULL,
        UNIQUE (run_id, ordinal)
    );
    CREATE TABLE judge_scores (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        result_id uuid NOT NULL REFERENCES eval_results ON DELETE CASCADE,
        judge_name text NOT NULL CHECK (char_length(judge_name) BETWEEN 1 AND 80),
        scores jsonb NOT NULL DEFAULT '{}',
        chunk_labels jsonb NOT NULL DEFAULT '{}',
        notes text NOT NULL DEFAULT '' CHECK (char_length(notes) <= 5000),
        UNIQUE (result_id, judge_name)
    );
    CREATE TRIGGER judge_scores_touch BEFORE UPDATE ON judge_scores
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    """)


def downgrade() -> None:
    run("""
    DROP TABLE judge_scores;
    DROP TABLE eval_results;
    DROP TABLE eval_runs;
    DROP TABLE chunk_meta;
    DROP INDEX generation_chunks_parent_id_idx;
    ALTER TABLE generation_chunks DROP COLUMN parent_id;
    DROP TABLE chunk_parents;
    ALTER TABLE chunks DROP CONSTRAINT chunks_kind_check;
    ALTER TABLE chunks ADD CONSTRAINT chunks_kind_check CHECK (kind IN ('text', 'table', 'case'));
    """)
