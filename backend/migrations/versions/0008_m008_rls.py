"""M008 runtime role, row-level security for user-owned data, last-admin guard.

The API connects as a LOGIN role that is a member of ``bazi_runtime``: not the
table owner, NOSUPERUSER, NOBYPASSRLS, so the policies below always apply. Each
transaction sets ``app.user_id`` from the authenticated principal; when it is
unset, owner-scoped tables show nothing (fail closed). Admins get no implicit
access to other users' profiles, charts or chats (docs/04 · Xóa, retention, quyền).

Roles are cluster-wide, so the role is created if missing and never dropped on
downgrade (other databases may still grant to it).

Revision ID: 0008_m008_rls
Revises: 0007_m007_operations
"""
from alembic import op

revision = '0008_m008_rls'
down_revision = '0007_m007_operations'
branch_labels = None
depends_on = None

OWNER = 'owner_id = bazi_current_user_id()'
# table -> USING expression; WITH CHECK uses the same expression.
POLICIES = {
    'birth_profiles': OWNER,
    'bazi_charts': OWNER,
    'chart_analyses': OWNER,
    'conversations': OWNER,
    'chat_runs': OWNER,
    'usage_records': OWNER,
    'budget_reservations': OWNER,
    'idempotency_keys': OWNER,
    'feedback': 'user_id = bazi_current_user_id()',
    'settings': "scope = 'system' OR owner_id = bazi_current_user_id()",
    'messages': 'EXISTS (SELECT 1 FROM conversations c WHERE c.id = conversation_id'
                ' AND c.owner_id = bazi_current_user_id())',
    'run_events': 'EXISTS (SELECT 1 FROM chat_runs r WHERE r.id = run_id'
                  ' AND r.owner_id = bazi_current_user_id())',
    'rule_traces': 'EXISTS (SELECT 1 FROM chart_analyses a WHERE a.id = analysis_id'
                   ' AND a.owner_id = bazi_current_user_id())',
    'claims': 'EXISTS (SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id'
              ' WHERE m.id = message_id AND c.owner_id = bazi_current_user_id())'
              ' OR EXISTS (SELECT 1 FROM chart_analyses a WHERE a.id = analysis_id'
              ' AND a.owner_id = bazi_current_user_id())',
    'citations': 'EXISTS (SELECT 1 FROM claims cl WHERE cl.id = claim_id)',
    'analysis_dependencies': 'EXISTS (SELECT 1 FROM chart_analyses a WHERE a.id = analysis_id'
                             ' AND a.owner_id = bazi_current_user_id())'
                             ' OR EXISTS (SELECT 1 FROM chat_runs r WHERE r.id = run_id'
                             ' AND r.owner_id = bazi_current_user_id())',
}


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bazi_runtime') THEN
            CREATE ROLE bazi_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
        END IF;
    END $$;

    CREATE FUNCTION bazi_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
        SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
    $$;

    GRANT USAGE ON SCHEMA public TO bazi_runtime;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bazi_runtime;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bazi_runtime;
    GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO bazi_runtime;
    -- Migration bookkeeping and the registry are not runtime data.
    REVOKE INSERT, UPDATE, DELETE ON alembic_version, entity_registry FROM bazi_runtime;
    -- Tables of later migrations (created by this same migration role) get the same grants.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bazi_runtime;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO bazi_runtime;

    -- Reference guards must see every user's rows, not only the caller's under RLS;
    -- run them with the owner's rights and a fixed search_path.
    ALTER FUNCTION bazi_guard_referenced_delete() SECURITY DEFINER SET search_path = public, pg_temp;
    """)
    for table, expression in POLICIES.items():
        run(f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        CREATE POLICY {table}_owner ON {table} FOR ALL TO bazi_runtime
            USING ({expression}) WITH CHECK ({expression});
        """)
    run("""
    -- Serialised by an advisory lock so two concurrent demotions cannot both pass.
    CREATE FUNCTION bazi_keep_one_admin() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.role = 'admin' AND OLD.enabled
                AND (TG_OP = 'DELETE' OR NEW.role <> 'admin' OR NOT NEW.enabled) THEN
            PERFORM pg_advisory_xact_lock(hashtext('bazi.users.admins'));
            IF NOT EXISTS (SELECT 1 FROM users WHERE role = 'admin' AND enabled
                           AND id <> OLD.id) THEN
                RAISE EXCEPTION 'the last active admin cannot be disabled or demoted'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END $$;
    CREATE TRIGGER users_keep_one_admin BEFORE UPDATE OF role, enabled OR DELETE ON users
        FOR EACH ROW EXECUTE FUNCTION bazi_keep_one_admin();
    """)


def downgrade() -> None:
    run("""
    DROP TRIGGER users_keep_one_admin ON users;
    DROP FUNCTION bazi_keep_one_admin();
    """)
    for table in POLICIES:
        run(f"""
        DROP POLICY {table}_owner ON {table};
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """)
    run("""
    ALTER FUNCTION bazi_guard_referenced_delete() SECURITY INVOKER RESET search_path;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM bazi_runtime;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM bazi_runtime;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM bazi_runtime;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM bazi_runtime;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM bazi_runtime;
    REVOKE USAGE ON SCHEMA public FROM bazi_runtime;
    DROP FUNCTION bazi_current_user_id();
    """)
