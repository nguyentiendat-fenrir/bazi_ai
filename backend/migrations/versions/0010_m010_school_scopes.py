"""M010 school scopes: which school a book version (or a page range of it) speaks for.

Contract addition (docs/04, docs/06, T020): a school is assigned by a reviewer,
never inferred silently; a book can mix schools, so a scope covers either the
whole version (no pages) or an inclusive physical page range, and the narrowest
approved scope wins. Page ranges, unlike section paths, stay stable across
generations. Approved scopes become per-generation chunk classifications, so a
published snapshot never drifts when a scope changes later.

Revision ID: 0010_m010_school_scopes
Revises: 0009_m009_batch_items
"""
from alembic import op

revision = '0010_m010_school_scopes'
down_revision = '0009_m009_batch_items'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE TABLE school_scopes (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        book_version_id uuid NOT NULL REFERENCES book_versions,
        school_id uuid NOT NULL REFERENCES schools,
        first_page integer CHECK (first_page >= 1),
        last_page integer,
        state text NOT NULL DEFAULT 'draft' CHECK (state IN
            ('draft', 'in_review', 'approved', 'rejected', 'revoked')),
        reason text NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 500),
        created_by uuid NOT NULL REFERENCES users,
        CHECK ((first_page IS NULL) = (last_page IS NULL)),
        CHECK (last_page >= first_page)
    );
    CREATE TRIGGER school_scopes_touch BEFORE UPDATE ON school_scopes
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    CREATE TRIGGER school_scopes_immutable BEFORE UPDATE ON school_scopes
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable('book_version_id', 'created_by');
    CREATE TRIGGER school_scopes_lifecycle BEFORE INSERT OR UPDATE ON school_scopes
        FOR EACH ROW EXECUTE FUNCTION bazi_review_lifecycle(
            'school_scope', 'school_id', 'first_page', 'last_page');
    -- One live scope per range; a changed decision is a new row after revoke/reject.
    CREATE UNIQUE INDEX school_scopes_live_uq ON school_scopes
        (book_version_id, coalesce(first_page, 0), coalesce(last_page, 0))
        WHERE state IN ('draft', 'in_review', 'approved');
    CREATE INDEX school_scopes_book_version_id_idx ON school_scopes (book_version_id, state);
    CREATE INDEX school_scopes_school_id_idx ON school_scopes (school_id);
    CREATE INDEX school_scopes_created_by_idx ON school_scopes (created_by);

    INSERT INTO entity_registry (kind, table_name) VALUES ('school_scope', 'school_scopes');
    CREATE TRIGGER school_scopes_referenced_delete BEFORE DELETE ON school_scopes
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_referenced_delete('school_scope');
    """)


def downgrade() -> None:
    run("""
    DROP TABLE school_scopes;
    DELETE FROM entity_registry WHERE kind = 'school_scope';
    """)
