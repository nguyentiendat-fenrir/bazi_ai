"""M017 one feedback per person and target, and feedback totals as counts.

Contract addition (docs/09, docs/12; product feedback): a person rates an answer or a
rule analysis of their own, once (a later rating replaces the earlier one). Feedback
stays owner-private; admins see only counts per rating and category through a definer
function, never the question, the answer or the comment.

Revision ID: 0017_m017_feedback
Revises: 0016_m016_operations_metrics
"""
from alembic import op

revision = '0017_m017_feedback'
down_revision = '0016_m016_operations_metrics'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE UNIQUE INDEX feedback_user_message_uq ON feedback (user_id, message_id)
        WHERE message_id IS NOT NULL;
    CREATE UNIQUE INDEX feedback_user_analysis_uq ON feedback (user_id, analysis_id)
        WHERE analysis_id IS NOT NULL;

    CREATE FUNCTION bazi_feedback_totals(since timestamptz) RETURNS jsonb
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        SELECT jsonb_build_object(
          'helpful', count(*) FILTER (WHERE rating = 1),
          'not_helpful', count(*) FILTER (WHERE rating = -1),
          'answers', count(*) FILTER (WHERE message_id IS NOT NULL),
          'analyses', count(*) FILTER (WHERE analysis_id IS NOT NULL),
          'categories', coalesce((SELECT jsonb_object_agg(c, n) FROM (
              SELECT c, count(*) AS n FROM feedback f2, jsonb_array_elements_text(f2.categories) c
              WHERE f2.updated_at >= since AND f2.rating = -1 GROUP BY c) x), '{}'))
        FROM feedback WHERE updated_at >= since
    $$;
    REVOKE ALL ON FUNCTION bazi_feedback_totals(timestamptz) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION bazi_feedback_totals(timestamptz) TO bazi_runtime;
    """)


def downgrade() -> None:
    run("""
    DROP FUNCTION bazi_feedback_totals(timestamptz);
    DROP INDEX feedback_user_analysis_uq;
    DROP INDEX feedback_user_message_uq;
    """)
