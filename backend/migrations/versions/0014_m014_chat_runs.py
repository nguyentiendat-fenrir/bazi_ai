"""M014 chat run queue across owners, without exposing anyone's conversations.

Contract addition (docs/09 · orchestration; T039): chat runs, messages and run
events are owner-private under row-level security, yet one reasoning worker
serves every owner. These definer functions only hand out the next queued run
(id and owner, nothing else) and fail runs a dead worker left running; the
worker then reads and writes as that owner, under the same row-level security
as the API. Expired run events are removed by owner-agnostic housekeeping.

Revision ID: 0014_m014_chat_runs
Revises: 0013_m013_usage_totals
"""
from alembic import op

revision = '0014_m014_chat_runs'
down_revision = '0013_m013_usage_totals'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE FUNCTION bazi_claim_chat_run() RETURNS TABLE (run_id uuid, owner_id uuid)
        LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        UPDATE chat_runs r SET state = 'running'
        WHERE r.id = (SELECT q.id FROM chat_runs q WHERE q.state = 'queued'
                      ORDER BY q.created_at, q.id FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING r.id, r.owner_id;
    $$;

    -- A worker that died mid-run leaves it running; after the cap it is failed, never resumed.
    CREATE FUNCTION bazi_fail_stale_chat_runs(older_than interval) RETURNS bigint
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE
        changed bigint;
    BEGIN
        WITH stale AS (
            UPDATE chat_runs SET state = 'failed',
                error = jsonb_build_object('code', 'RUN_ABANDONED', 'retryable', true)
            WHERE state IN ('running', 'waiting_provider') AND updated_at < now() - older_than
            RETURNING id, assistant_message_id)
        UPDATE messages m SET status = 'failed' FROM stale
        WHERE m.id = stale.assistant_message_id AND m.status IN ('pending', 'streaming');
        GET DIAGNOSTICS changed = ROW_COUNT;
        RETURN changed;
    END $$;

    CREATE FUNCTION bazi_expire_run_events() RETURNS bigint
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE
        removed bigint;
    BEGIN
        DELETE FROM run_events WHERE expires_at < now();
        GET DIAGNOSTICS removed = ROW_COUNT;
        RETURN removed;
    END $$;

    REVOKE ALL ON FUNCTION bazi_claim_chat_run() FROM PUBLIC;
    REVOKE ALL ON FUNCTION bazi_fail_stale_chat_runs(interval) FROM PUBLIC;
    REVOKE ALL ON FUNCTION bazi_expire_run_events() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION bazi_claim_chat_run() TO bazi_runtime;
    GRANT EXECUTE ON FUNCTION bazi_fail_stale_chat_runs(interval) TO bazi_runtime;
    GRANT EXECUTE ON FUNCTION bazi_expire_run_events() TO bazi_runtime;
    """)


def downgrade() -> None:
    run("""
    DROP FUNCTION bazi_expire_run_events();
    DROP FUNCTION bazi_fail_stale_chat_runs(interval);
    DROP FUNCTION bazi_claim_chat_run();
    """)
