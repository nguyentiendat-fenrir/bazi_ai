"""M016 operations metrics across owners, as counts only.

Contract addition (docs/12 · Observability; T051): queue depth and age, job failures,
stage leases, page quality, chat runs, rejected claims, rule outcomes, usage, operations
and the last backup are needed for the admin metrics page and its alerts. Chat runs,
messages, traces and usage are owner-private under row-level security, so one definer
function returns the aggregates — numbers and timestamps, never ids or text.

Revision ID: 0016_m016_operations_metrics
Revises: 0015_m015_erasure
"""
from alembic import op

revision = '0016_m016_operations_metrics'
down_revision = '0015_m015_erasure'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE FUNCTION bazi_operations_metrics() RETURNS jsonb
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT jsonb_build_object(
      'ingestion', jsonb_build_object(
        'by_state', (SELECT coalesce(jsonb_object_agg(state, n), '{}') FROM
                     (SELECT state, count(*) AS n FROM ingestion_jobs GROUP BY state) s),
        'oldest_queued_seconds', (SELECT extract(epoch FROM now() - min(created_at))::bigint
                                  FROM ingestion_jobs WHERE state = 'queued'),
        'failed_24h', (SELECT count(*) FROM ingestion_jobs
                       WHERE state = 'failed' AND updated_at > now() - interval '24 hours'),
        'repeated_failures', (SELECT count(*) FROM (SELECT book_version_id FROM ingestion_jobs
                              WHERE state = 'failed' AND updated_at > now() - interval '24 hours'
                              GROUP BY book_version_id HAVING count(*) >= 3) r)),
      'stages', jsonb_build_object(
        'running', (SELECT count(*) FROM job_stages WHERE state = 'running'),
        'expired_leases', (SELECT count(*) FROM job_stages
                           WHERE state = 'running' AND lease_until < now())),
      'pages', (SELECT coalesce(jsonb_object_agg(state, n), '{}') FROM
                (SELECT state, count(*) AS n FROM page_revisions GROUP BY state) p),
      'chat', jsonb_build_object(
        'by_state', (SELECT coalesce(jsonb_object_agg(state, n), '{}') FROM
                     (SELECT state, count(*) AS n FROM chat_runs GROUP BY state) c),
        'oldest_queued_seconds', (SELECT extract(epoch FROM now() - min(created_at))::bigint
                                  FROM chat_runs WHERE state = 'queued'),
        'completed_24h', (SELECT count(*) FROM chat_runs WHERE state = 'completed'
                          AND updated_at > now() - interval '24 hours'),
        'failed_24h', (SELECT count(*) FROM chat_runs WHERE state = 'failed'
                       AND updated_at > now() - interval '24 hours'),
        'rejected_claims_24h', (SELECT coalesce(sum((structured_answer->>'rejected_claims')::int), 0)
                                FROM messages WHERE role = 'assistant' AND status = 'completed'
                                AND structured_answer ? 'rejected_claims'
                                AND created_at > now() - interval '24 hours'),
        'claims_24h', (SELECT count(*) FROM claims WHERE created_at > now() - interval '24 hours')),
      'rules_24h', (SELECT coalesce(jsonb_object_agg(status, n), '{}') FROM
                    (SELECT status, count(*) AS n FROM rule_traces
                     WHERE created_at > now() - interval '24 hours' GROUP BY status) t),
      'usage_24h', (SELECT coalesce(jsonb_object_agg(currency, jsonb_build_object(
                      'requests', n, 'input_tokens', i, 'output_tokens', o, 'cost', c)), '{}') FROM
                    (SELECT currency, count(*) AS n, sum(input_tokens) AS i,
                            sum(output_tokens) AS o, sum(coalesce(actual_cost, estimated_cost)) AS c
                     FROM usage_records WHERE created_at > now() - interval '24 hours'
                     GROUP BY currency) u),
      'reservations_held', (SELECT count(*) FROM budget_reservations
                            WHERE status = 'held' AND expires_at > now()),
      'operations', (SELECT coalesce(jsonb_object_agg(state, n), '{}') FROM
                     (SELECT state, count(*) AS n FROM operation_jobs GROUP BY state) o),
      'last_backup_at', (SELECT max(created_at) FROM backups
                         WHERE state IN ('succeeded', 'verified')),
      'active_embedding', (SELECT EXISTS (SELECT 1 FROM active_corpus a
                           JOIN corpus_releases r ON r.id = a.release_id
                           JOIN embedding_collections e ON e.id = r.embedding_collection_id
                           WHERE e.state = 'ready')),
      'corpus_empty', (SELECT NOT EXISTS (SELECT 1 FROM active_corpus))
    )
    $$;
    REVOKE ALL ON FUNCTION bazi_operations_metrics() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION bazi_operations_metrics() TO bazi_runtime;
    """)


def downgrade() -> None:
    run('DROP FUNCTION bazi_operations_metrics();')
