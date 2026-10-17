"""M013 usage totals across owners, without exposing anyone's requests.

Contract addition (docs/09 · Provider adapters, privacy, budget; T038): usage
records and budget holds are owner-private under row-level security, yet a
profile's daily budget is shared by every caller and admins see aggregate
usage. This definer function returns sums per profile and currency over a
window — no owner, no request, no content. Held reservations count until they
expire; failed calls count only what the provider reported as charged.

Revision ID: 0013_m013_usage_totals
Revises: 0012_m012_evidence_bundles
"""
from alembic import op

revision = '0013_m013_usage_totals'
down_revision = '0012_m012_evidence_bundles'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE FUNCTION bazi_usage_totals(since timestamptz, until timestamptz)
        RETURNS TABLE (profile_id uuid, currency text, requests bigint, input_tokens bigint,
                       output_tokens bigint, cost numeric)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        SELECT u.profile_id, u.currency::text, count(*), sum(u.input_tokens)::bigint,
               sum(u.output_tokens)::bigint,
               sum(CASE u.status
                   WHEN 'reserved' THEN (SELECT coalesce(sum(r.reserved_cost), 0)
                                         FROM budget_reservations r WHERE r.usage_id = u.id
                                         AND r.status = 'held' AND r.expires_at > now())
                   WHEN 'failed' THEN coalesce(u.actual_cost, 0)
                   ELSE coalesce(u.actual_cost, u.estimated_cost) END)
        FROM usage_records u
        WHERE u.created_at >= since AND u.created_at < until
        GROUP BY u.profile_id, u.currency
    $$;
    REVOKE ALL ON FUNCTION bazi_usage_totals(timestamptz, timestamptz) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION bazi_usage_totals(timestamptz, timestamptz) TO bazi_runtime;
    """)


def downgrade() -> None:
    run('DROP FUNCTION bazi_usage_totals(timestamptz, timestamptz);')
