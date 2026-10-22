"""M020 definition curation: an outside LLM drafts concept definitions from published pages.

``curation_calls`` keeps every model answer by a key over (step, model, prompt version, input)
so a rerun never pays twice for the same work. ``curation_candidates`` are the concept
mentions found per parent section, each with the evidence span the code located (the model
only quotes; offsets are never taken from it). A drafted definition is an ordinary draft
revision of ``concepts``; ``concept_sources`` ties that revision to its evidence and
``concept_curation`` holds the claims, the model's own review and its status. Approval stays
a person's decision through the existing review flow.

Revision ID: 0020_m020_curation
Revises: 0019_m019_summarize_stage
"""
from alembic import op

revision = '0020_m020_curation'
down_revision = '0019_m019_summarize_stage'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE TABLE curation_calls (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        call_key sha256_hex NOT NULL UNIQUE,
        step text NOT NULL CHECK (step IN ('discover', 'compose', 'review')),
        model text NOT NULL,
        prompt_version text NOT NULL,
        output jsonb NOT NULL,
        prompt_tokens integer NOT NULL DEFAULT 0,
        completion_tokens integer NOT NULL DEFAULT 0,
        latency_ms integer NOT NULL DEFAULT 0
    );

    CREATE TABLE curation_candidates (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        book_version_id uuid NOT NULL REFERENCES book_versions,
        parent_id uuid NOT NULL REFERENCES chunk_parents,
        school_id uuid NOT NULL REFERENCES schools,
        name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
        name_key text NOT NULL,
        kind text NOT NULL CHECK (kind IN ('explains', 'mentions', 'example')),
        quote text NOT NULL,
        quote_hash sha256_hex NOT NULL,
        located text NOT NULL CHECK (located IN ('exact', 'fuzzy', 'not_found')),
        evidence_id uuid REFERENCES evidence_spans,
        context_missing boolean NOT NULL DEFAULT false,
        UNIQUE (parent_id, name_key, quote_hash),
        CHECK ((located = 'not_found') = (evidence_id IS NULL))
    );
    CREATE INDEX curation_candidates_book_version_id_idx ON curation_candidates (book_version_id);
    CREATE INDEX curation_candidates_school_id_idx ON curation_candidates (school_id);
    CREATE INDEX curation_candidates_evidence_id_idx ON curation_candidates (evidence_id);
    CREATE INDEX curation_candidates_name_idx ON curation_candidates (school_id, name_key);

    CREATE TABLE concept_sources (
        concept_id uuid NOT NULL REFERENCES concepts,
        evidence_id uuid NOT NULL REFERENCES evidence_spans,
        ordinal integer NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (concept_id, evidence_id)
    );
    CREATE INDEX concept_sources_evidence_id_idx ON concept_sources (evidence_id);

    CREATE TABLE concept_curation (
        concept_id uuid PRIMARY KEY REFERENCES concepts,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        name_key text NOT NULL,
        essential_notes text NOT NULL DEFAULT '',
        claims jsonb NOT NULL DEFAULT '[]',
        issues jsonb NOT NULL DEFAULT '[]',
        status text NOT NULL CHECK (status IN
            ('ready', 'needs_context', 'needs_split', 'rewrite_requested')),
        llm_verdict text CHECK (llm_verdict IN ('pass', 'fix', 'fail')),
        llm_problems jsonb NOT NULL DEFAULT '[]',
        independent_sources integer NOT NULL DEFAULT 0 CHECK (independent_sources >= 0),
        dossier_hash sha256_hex NOT NULL,
        rewrite_note text NOT NULL DEFAULT '' CHECK (char_length(rewrite_note) <= 2000),
        compose_model text,
        review_model text,
        prompt_version text NOT NULL
    );
    CREATE INDEX concept_curation_verdict_idx ON concept_curation (llm_verdict, status);
    CREATE TRIGGER concept_curation_touch BEFORE UPDATE ON concept_curation
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    """)


def downgrade() -> None:
    run("""
    DROP TABLE concept_curation;
    DROP TABLE concept_sources;
    DROP TABLE curation_candidates;
    DROP TABLE curation_calls;
    """)
