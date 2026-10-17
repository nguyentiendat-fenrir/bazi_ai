"""M011 dependency functions that cross owner boundaries without exposing content.

Contract addition (docs/06 · Impact analysis, T024): analyses and chat runs are
owner-scoped under row-level security, so a reviewer revoking a rule cannot see
whose answers depended on it — by design. These two functions run with the
owner's rights and expose only what the knowledge workflow needs: how many
analyses/runs depend on a set of entities, and marking completed analyses stale
with a reason. No IDs or content leave them.

``deps`` is ``{"rule": ["<uuid>", ...], "evidence": [...], ...}``.

Revision ID: 0011_m011_dependency_functions
Revises: 0010_m010_school_scopes
"""
from alembic import op

revision = '0011_m011_dependency_functions'
down_revision = '0010_m010_school_scopes'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE FUNCTION bazi_dependent_count(deps jsonb) RETURNS TABLE (analyses bigint, runs bigint)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        SELECT count(DISTINCT d.analysis_id), count(DISTINCT d.run_id)
        FROM analysis_dependencies d
        JOIN jsonb_each(deps) e(kind, ids) ON e.kind = d.dependency_kind
        WHERE d.dependency_id::text IN (SELECT jsonb_array_elements_text(e.ids))
    $$;

    CREATE FUNCTION bazi_mark_dependents_stale(deps jsonb, reason text) RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE
        changed bigint;
    BEGIN
        UPDATE chart_analyses a SET status = 'stale', stale_reason = left(reason, 500)
        WHERE a.status = 'completed' AND EXISTS (
            SELECT 1 FROM analysis_dependencies d
            JOIN jsonb_each(deps) e(kind, ids) ON e.kind = d.dependency_kind
            WHERE d.analysis_id = a.id
              AND d.dependency_id::text IN (SELECT jsonb_array_elements_text(e.ids)));
        GET DIAGNOSTICS changed = ROW_COUNT;
        RETURN changed;
    END $$;

    REVOKE ALL ON FUNCTION bazi_dependent_count(jsonb) FROM PUBLIC;
    REVOKE ALL ON FUNCTION bazi_mark_dependents_stale(jsonb, text) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION bazi_dependent_count(jsonb) TO bazi_runtime;
    GRANT EXECUTE ON FUNCTION bazi_mark_dependents_stale(jsonb, text) TO bazi_runtime;
    """)


def downgrade() -> None:
    run("""
    DROP FUNCTION bazi_mark_dependents_stale(jsonb, text);
    DROP FUNCTION bazi_dependent_count(jsonb);
    """)
