"""M015 erasure of a person's private data, and the deletion ledger.

Contract addition (docs/12 · Deletion; T049): owner-private rows live under row-level
security, so an admin erasing someone else's data (and a restore re-applying an erasure)
needs a definer function. ``bazi_erase_owner`` hard-deletes, leaf to root, everything
private to one user: charts and their analyses/traces, birth profiles, conversations with
messages, claims, citations, runs and run events, evidence bundles, private cases, user
settings, feedback, idempotency replays and sessions. Usage rows stay for budget totals but
lose their run link; they carry no text. With ``account`` the user row is kept for the
authorship of reviewed knowledge and the audit trail, but its email and password are
replaced and sign-in is disabled.

Reviews are append-only and may name a private case revision; during an erasure the
referenced-delete guard lets that row go and the review keeps a dangling id as a tombstone.
The guard is itself a definer function, so it cannot tell callers apart by role, and a
session setting could be forged by any runtime session: the erasure instead records its
transaction id in ``erasure_tokens``, which only the definer functions can write.

Every erasure appends to ``deletion_ledger`` (user id, time, counts; no content), which a
restore re-applies so an older backup cannot bring erased data back.

Revision ID: 0015_m015_erasure
Revises: 0014_m014_chat_runs
"""
from alembic import op

revision = '0015_m015_erasure'
down_revision = '0014_m014_chat_runs'
branch_labels = None
depends_on = None

GUARD_BODY = """
    DECLARE
        ref record;
        referenced boolean;
    BEGIN
        {bypass}
        FOR ref IN SELECT * FROM (VALUES ('reviews', 'entity_kind', 'entity_id'),
                                         ('review_items', 'entity_kind', 'entity_id'),
                                         ('analysis_dependencies', 'dependency_kind',
                                          'dependency_id')) AS r(tbl, kind_col, id_col)
        LOOP
            CONTINUE WHEN to_regclass(ref.tbl) IS NULL;
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE %I = $1 AND %I = $2)',
                           ref.tbl, ref.kind_col, ref.id_col)
                INTO referenced USING TG_ARGV[0], OLD.id;
            IF referenced THEN
                RAISE EXCEPTION '% % is referenced by %', TG_ARGV[0], OLD.id, ref.tbl
                    USING ERRCODE = 'foreign_key_violation';
            END IF;
        END LOOP;
        RETURN OLD;
    END"""
BYPASS = """-- Only bazi_erase_owner writes erasure_tokens (runtime cannot), for its own transaction.
        IF EXISTS (SELECT 1 FROM erasure_tokens WHERE txid = txid_current()) THEN
            RETURN OLD;
        END IF;"""
GUARD = ('CREATE OR REPLACE FUNCTION bazi_guard_referenced_delete() RETURNS trigger LANGUAGE plpgsql'
         ' SECURITY DEFINER SET search_path = public, pg_temp AS $${body} $$;')


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run(f"""
    CREATE TABLE deletion_ledger (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        subject_id uuid NOT NULL,
        account_deleted boolean NOT NULL,
        requested_by uuid,
        counts jsonb NOT NULL DEFAULT '{{}}'
    );
    CREATE INDEX deletion_ledger_created_idx ON deletion_ledger (created_at);
    CREATE TRIGGER deletion_ledger_append_only BEFORE UPDATE OR DELETE ON deletion_ledger
        FOR EACH ROW EXECUTE FUNCTION bazi_append_only();
    REVOKE ALL ON deletion_ledger FROM bazi_runtime;
    CREATE TABLE erasure_tokens (txid bigint PRIMARY KEY);
    REVOKE ALL ON erasure_tokens FROM bazi_runtime;

    {GUARD.format(body=GUARD_BODY.format(bypass=BYPASS))}

    CREATE FUNCTION bazi_erase_owner(subject uuid, account boolean, actor uuid,
                                     record_ledger boolean DEFAULT true) RETURNS jsonb
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    DECLARE
        counts jsonb := '{{}}';
        n bigint;
        convs uuid[];
        runs uuid[];
        msgs uuid[];
        analyses uuid[];
        claim_ids uuid[];
        case_ids uuid[];
        case_revs uuid[];
    BEGIN
        INSERT INTO erasure_tokens VALUES (txid_current()) ON CONFLICT DO NOTHING;
        SELECT coalesce(array_agg(id), '{{}}') INTO convs FROM conversations WHERE owner_id = subject;
        SELECT coalesce(array_agg(id), '{{}}') INTO runs FROM chat_runs
            WHERE owner_id = subject OR conversation_id = ANY(convs);
        SELECT coalesce(array_agg(id), '{{}}') INTO msgs FROM messages WHERE conversation_id = ANY(convs);
        SELECT coalesce(array_agg(id), '{{}}') INTO analyses FROM chart_analyses
            WHERE owner_id = subject OR run_id = ANY(runs);
        SELECT coalesce(array_agg(id), '{{}}') INTO claim_ids FROM claims
            WHERE message_id = ANY(msgs) OR analysis_id = ANY(analyses);
        SELECT coalesce(array_agg(id), '{{}}') INTO case_ids FROM cases
            WHERE owner_id = subject AND origin = 'user_case';
        SELECT coalesce(array_agg(id), '{{}}') INTO case_revs FROM case_revisions
            WHERE case_id = ANY(case_ids);

        DELETE FROM citations WHERE claim_id = ANY(claim_ids);
        DELETE FROM feedback WHERE user_id = subject OR message_id = ANY(msgs)
            OR analysis_id = ANY(analyses);
        DELETE FROM analysis_dependencies WHERE analysis_id = ANY(analyses) OR run_id = ANY(runs);
        DELETE FROM claims WHERE id = ANY(claim_ids);
        GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('claims', n);
        DELETE FROM rule_traces WHERE analysis_id = ANY(analyses);
        DELETE FROM run_events WHERE run_id = ANY(runs);
        UPDATE usage_records SET run_id = NULL WHERE run_id = ANY(runs);
        DELETE FROM chart_analyses WHERE id = ANY(analyses);
        GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('analyses', n);
        -- Runs and messages point at each other; one statement removes both.
        WITH gone_runs AS (DELETE FROM chat_runs WHERE id = ANY(runs) RETURNING id)
        DELETE FROM messages WHERE id = ANY(msgs);
        GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('messages', n);
        DELETE FROM conversations WHERE id = ANY(convs);
        GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('conversations', n);
        DELETE FROM evidence_bundles WHERE owner_id = subject;
        DELETE FROM bazi_charts WHERE owner_id = subject;
        GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('charts', n);
        DELETE FROM birth_profiles WHERE owner_id = subject;
        GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('birth_profiles', n);
        DELETE FROM review_items WHERE entity_kind = 'case_revision' AND entity_id = ANY(case_revs);
        DELETE FROM case_sources WHERE case_revision_id = ANY(case_revs);
        DELETE FROM case_revisions WHERE id = ANY(case_revs);
        DELETE FROM cases WHERE id = ANY(case_ids);
        GET DIAGNOSTICS n = ROW_COUNT; counts := counts || jsonb_build_object('cases', n);
        DELETE FROM settings WHERE scope = 'user' AND owner_id = subject;
        DELETE FROM idempotency_keys WHERE owner_id = subject;
        IF account THEN
            DELETE FROM sessions WHERE user_id = subject;
            UPDATE users SET email = 'deleted-' || id || '@invalid',
                password_hash = 'erased:' || gen_random_uuid() || gen_random_uuid(),
                enabled = false WHERE id = subject;
        END IF;
        DELETE FROM erasure_tokens WHERE txid = txid_current();
        IF record_ledger THEN
            INSERT INTO deletion_ledger (subject_id, account_deleted, requested_by, counts)
                VALUES (subject, account, actor, counts);
        END IF;
        RETURN counts;
    END $$;

    REVOKE ALL ON FUNCTION bazi_erase_owner(uuid, boolean, uuid, boolean) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION bazi_erase_owner(uuid, boolean, uuid, boolean) TO bazi_runtime;
    """)


def downgrade() -> None:
    run(f"""
    DROP FUNCTION bazi_erase_owner(uuid, boolean, uuid, boolean);
    {GUARD.format(body=GUARD_BODY.format(bypass=''))}
    DROP TABLE erasure_tokens;
    DROP TABLE deletion_ledger;
    """)
