"""M012 evidence bundles: what the server handed a model, kept to check its citations.

Contract addition (docs/07 · Citation validation, T037): a model cites opaque
handles (E1, E2…) from the bundle it was given. The bundle is stored server
side — owner, release, visibility epoch and the exact spans of every group — so
a citation is resolved against what was actually provided, never against spans a
client sends back. Bundles are private to their owner (row-level security, like
other user data) and expire; chat runs (K6) reference them by id.

Revision ID: 0012_m012_evidence_bundles
Revises: 0011_m011_dependency_functions
"""
from alembic import op

revision = '0012_m012_evidence_bundles'
down_revision = '0011_m011_dependency_functions'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE TABLE evidence_bundles (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        owner_id uuid NOT NULL REFERENCES users,
        corpus_release_id uuid NOT NULL REFERENCES corpus_releases,
        visibility_epoch bigint NOT NULL CHECK (visibility_epoch >= 0),
        query_hash sha256_hex NOT NULL,
        groups jsonb NOT NULL CHECK (jsonb_typeof(groups) = 'array'),
        expires_at timestamptz NOT NULL,
        CHECK (expires_at > created_at)
    );
    CREATE TRIGGER evidence_bundles_touch BEFORE UPDATE ON evidence_bundles
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    CREATE TRIGGER evidence_bundles_immutable BEFORE UPDATE ON evidence_bundles
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable(
            'owner_id', 'corpus_release_id', 'visibility_epoch', 'query_hash', 'groups');
    CREATE INDEX evidence_bundles_owner_idx ON evidence_bundles (owner_id, created_at);
    CREATE INDEX evidence_bundles_release_idx ON evidence_bundles (corpus_release_id);
    CREATE INDEX evidence_bundles_expires_idx ON evidence_bundles (expires_at);

    ALTER TABLE evidence_bundles ENABLE ROW LEVEL SECURITY;
    CREATE POLICY evidence_bundles_owner ON evidence_bundles FOR ALL TO bazi_runtime
        USING (owner_id = bazi_current_user_id()) WITH CHECK (owner_id = bazi_current_user_id());
    """)


def downgrade() -> None:
    run('DROP TABLE evidence_bundles;')
