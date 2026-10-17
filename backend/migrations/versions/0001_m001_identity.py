"""M001 extensions, shared triggers, users/sessions/settings/model profiles.

Revision ID: 0001_m001_identity
Revises:
"""
from alembic import op

revision = '0001_m001_identity'
down_revision = None
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def create_table(name: str, columns: str) -> None:
    """docs/04 common columns + an updated_at trigger on every table."""
    run(f"""
    CREATE TABLE {name} (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        {columns}
    );
    CREATE TRIGGER {name}_touch BEFORE UPDATE ON {name}
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    """)


def upgrade() -> None:
    run("""
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS unaccent;
    CREATE EXTENSION IF NOT EXISTS citext;

    CREATE DOMAIN sha256_hex AS char(64) CHECK (VALUE ~ '^[0-9a-f]{64}$');

    CREATE FUNCTION bazi_sha256_text(value text) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
        AS $$ SELECT encode(sha256(convert_to(value, 'UTF8')), 'hex') $$;

    CREATE FUNCTION bazi_touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        NEW.updated_at := now();
        RETURN NEW;
    END $$;

    -- Usage: BEFORE UPDATE ... EXECUTE FUNCTION bazi_guard_immutable('col', ...).
    CREATE FUNCTION bazi_guard_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        col text;
    BEGIN
        FOREACH col IN ARRAY TG_ARGV LOOP
            IF to_jsonb(NEW) -> col IS DISTINCT FROM to_jsonb(OLD) -> col THEN
                RAISE EXCEPTION '%.% is immutable', TG_TABLE_NAME, col
                    USING ERRCODE = 'restrict_violation';
            END IF;
        END LOOP;
        RETURN NEW;
    END $$;
    """)

    create_table('users', """
        email citext NOT NULL UNIQUE,
        password_hash text NOT NULL,
        role text NOT NULL CHECK (role IN ('admin', 'reviewer', 'reader')),
        enabled boolean NOT NULL DEFAULT true,
        locale text NOT NULL DEFAULT 'vi'
    """)

    create_table('sessions', """
        user_id uuid NOT NULL REFERENCES users,
        token_hash text NOT NULL UNIQUE,
        csrf_hash text NOT NULL,
        expires_at timestamptz NOT NULL,
        revoked_at timestamptz
    """)
    run("""
    CREATE INDEX sessions_user_id_idx ON sessions (user_id);
    CREATE INDEX sessions_expires_at_idx ON sessions (expires_at);
    """)

    create_table('settings', """
        scope text NOT NULL CHECK (scope IN ('system', 'user')),
        owner_id uuid REFERENCES users,
        key text NOT NULL,
        value jsonb NOT NULL,
        revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
        CHECK ((scope = 'user') = (owner_id IS NOT NULL)),
        UNIQUE NULLS NOT DISTINCT (scope, owner_id, key)
    """)
    run('CREATE INDEX settings_owner_id_idx ON settings (owner_id);')

    create_table('model_profiles', """
        kind text NOT NULL CHECK (kind IN ('llm', 'embedding', 'reranker')),
        provider text NOT NULL,
        model_name text NOT NULL,
        model_revision text NOT NULL,
        dimension integer CHECK (dimension > 0),
        config jsonb NOT NULL DEFAULT '{}',
        secret_ref text,
        profile_hash sha256_hex NOT NULL UNIQUE,
        enabled boolean NOT NULL DEFAULT true,
        CHECK (kind <> 'embedding' OR dimension IS NOT NULL)
    """)
    run("""
    CREATE TRIGGER model_profiles_immutable BEFORE UPDATE ON model_profiles
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable(
            'kind', 'provider', 'model_name', 'model_revision', 'dimension',
            'config', 'secret_ref', 'profile_hash');
    """)


def downgrade() -> None:
    run("""
    DROP TABLE model_profiles, settings, sessions, users;
    DROP FUNCTION bazi_guard_immutable(), bazi_touch_updated_at(), bazi_sha256_text(text);
    DROP DOMAIN sha256_hex;
    """)
