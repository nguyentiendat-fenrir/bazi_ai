"""M005 rulesets, calculation policies, birth profiles, charts, analyses, traces.

Owner consistency uses composite FKs (a chart's profile and an analysis' chart
belong to the same owner). Rulesets are immutable snapshots of approved rules of
one school/method. ``chart_analyses.run_id`` gets its FK in M006 with chat_runs.

Revision ID: 0005_m005_charts
Revises: 0004_m004_knowledge
"""
from alembic import op

revision = '0005_m005_charts'
down_revision = '0004_m004_knowledge'
branch_labels = None
depends_on = None

KINDS = {'ruleset': 'rulesets', 'calculation_policy': 'calculation_policies',
         'birth_profile': 'birth_profiles', 'chart': 'bazi_charts', 'analysis': 'chart_analyses'}


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def create_table(name: str, columns: str) -> None:
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


def immutable(table: str, *columns: str) -> None:
    cols = ', '.join(f"'{c}'" for c in columns)
    run(f"""
    CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table}
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable({cols});
    """)


def upgrade() -> None:
    create_table('rulesets', """
        school_id uuid NOT NULL REFERENCES schools,
        method_id uuid NOT NULL,
        version text NOT NULL,
        state text NOT NULL DEFAULT 'building' CHECK (state IN ('building', 'published', 'retired')),
        manifest_hash sha256_hex,
        UNIQUE (school_id, method_id, version),
        FOREIGN KEY (method_id, school_id) REFERENCES methods (id, school_id),
        CHECK (state = 'building' OR manifest_hash IS NOT NULL)
    """)
    immutable('rulesets', 'school_id', 'method_id', 'version')
    run("""
    CREATE INDEX rulesets_method_id_idx ON rulesets (method_id);

    CREATE FUNCTION bazi_snapshot_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state IS DISTINCT FROM OLD.state AND (OLD.state, NEW.state) NOT IN (
                ('building', 'published'), ('building', 'retired'), ('published', 'retired')) THEN
            RAISE EXCEPTION '% state % -> % is not allowed', TG_TABLE_NAME, OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.state <> 'building' AND NEW.manifest_hash IS DISTINCT FROM OLD.manifest_hash THEN
            RAISE EXCEPTION '% manifest is frozen after building', TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER rulesets_transition BEFORE UPDATE ON rulesets
        FOR EACH ROW EXECUTE FUNCTION bazi_snapshot_transition();
    """)

    create_table('ruleset_members', """
        ruleset_id uuid NOT NULL REFERENCES rulesets,
        rule_id uuid NOT NULL REFERENCES knowledge_rules,
        ordinal integer NOT NULL CHECK (ordinal >= 0),
        UNIQUE (ruleset_id, rule_id),
        UNIQUE (ruleset_id, ordinal)
    """)
    immutable('ruleset_members', 'ruleset_id', 'rule_id', 'ordinal')
    run("""
    CREATE INDEX ruleset_members_rule_id_idx ON ruleset_members (rule_id);

    -- Only approved rules of the ruleset's own school/method, only while building.
    CREATE FUNCTION bazi_check_ruleset_member() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        target ruleset_members := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        rs rulesets;
    BEGIN
        SELECT * INTO rs FROM rulesets WHERE id = target.ruleset_id FOR SHARE;
        IF rs.state <> 'building' THEN
            RAISE EXCEPTION 'ruleset % is frozen', rs.id USING ERRCODE = 'restrict_violation';
        END IF;
        IF TG_OP <> 'DELETE' AND NOT EXISTS (
                SELECT 1 FROM knowledge_rules WHERE id = NEW.rule_id AND state = 'approved'
                AND school_id = rs.school_id AND method_id = rs.method_id) THEN
            RAISE EXCEPTION 'rule % is not an approved rule of the ruleset school/method',
                NEW.rule_id USING ERRCODE = 'check_violation';
        END IF;
        RETURN target;
    END $$;
    CREATE TRIGGER ruleset_members_check BEFORE INSERT OR UPDATE OR DELETE ON ruleset_members
        FOR EACH ROW EXECUTE FUNCTION bazi_check_ruleset_member();
    """)

    create_table('calculation_policies', """
        key text NOT NULL,
        revision integer NOT NULL CHECK (revision >= 1),
        config jsonb NOT NULL,
        manifest_hash sha256_hex NOT NULL,
        state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'active', 'retired')),
        UNIQUE (key, revision),
        CHECK (manifest_hash = bazi_sha256_text(config::text))
    """)
    run("""
    CREATE FUNCTION bazi_policy_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state IS DISTINCT FROM OLD.state AND (OLD.state, NEW.state) NOT IN (
                ('draft', 'active'), ('draft', 'retired'), ('active', 'retired')) THEN
            RAISE EXCEPTION 'policy state % -> % is not allowed', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.state <> 'draft' AND (NEW.config IS DISTINCT FROM OLD.config
                OR NEW.key IS DISTINCT FROM OLD.key OR NEW.revision IS DISTINCT FROM OLD.revision) THEN
            RAISE EXCEPTION 'calculation policy is immutable after activation'
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER calculation_policies_transition BEFORE UPDATE ON calculation_policies
        FOR EACH ROW EXECUTE FUNCTION bazi_policy_transition();
    """)

    create_table('birth_profiles', """
        owner_id uuid NOT NULL REFERENCES users,
        label text NOT NULL,
        birth_input_encrypted bytea NOT NULL,
        crypto_key_version text NOT NULL,
        revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
        deleted_at timestamptz,
        UNIQUE (id, owner_id)
    """)
    run('CREATE INDEX birth_profiles_owner_id_idx ON birth_profiles (owner_id);')

    create_table('bazi_charts', """
        owner_id uuid NOT NULL REFERENCES users,
        profile_id uuid,
        profile_revision integer CHECK (profile_revision >= 1),
        policy_id uuid NOT NULL REFERENCES calculation_policies,
        input_snapshot_encrypted bytea NOT NULL,
        facts jsonb NOT NULL CHECK (jsonb_typeof(facts) = 'object'),
        facts_hash sha256_hex NOT NULL,
        engine_manifest jsonb NOT NULL,
        validation_status text NOT NULL CHECK (validation_status IN ('valid', 'partial', 'invalid')),
        UNIQUE (id, owner_id),
        FOREIGN KEY (profile_id, owner_id) REFERENCES birth_profiles (id, owner_id),
        CHECK ((profile_id IS NULL) = (profile_revision IS NULL)),
        CHECK (facts_hash = bazi_sha256_text(facts::text))
    """)
    immutable('bazi_charts', 'owner_id', 'profile_id', 'profile_revision', 'policy_id',
              'input_snapshot_encrypted', 'facts', 'facts_hash', 'engine_manifest')
    run("""
    CREATE INDEX bazi_charts_owner_created_idx ON bazi_charts (owner_id, created_at);
    CREATE INDEX bazi_charts_profile_id_idx ON bazi_charts (profile_id);
    CREATE INDEX bazi_charts_policy_id_idx ON bazi_charts (policy_id);
    """)

    create_table('chart_analyses', """
        owner_id uuid NOT NULL REFERENCES users,
        chart_id uuid NOT NULL,
        ruleset_id uuid REFERENCES rulesets,
        corpus_release_id uuid REFERENCES corpus_releases,
        answer jsonb,
        status text NOT NULL DEFAULT 'pending' CHECK (status IN
            ('pending', 'completed', 'failed', 'stale', 'withdrawn')),
        stale_reason text,
        run_id uuid,
        UNIQUE (id, owner_id),
        FOREIGN KEY (chart_id, owner_id) REFERENCES bazi_charts (id, owner_id),
        CHECK (status <> 'completed' OR answer IS NOT NULL),
        CHECK ((status = 'stale') = (stale_reason IS NOT NULL))
    """)
    immutable('chart_analyses', 'owner_id', 'chart_id', 'ruleset_id', 'corpus_release_id')
    run("""
    CREATE INDEX chart_analyses_chart_created_idx ON chart_analyses (chart_id, created_at);
    CREATE INDEX chart_analyses_owner_id_idx ON chart_analyses (owner_id);
    CREATE INDEX chart_analyses_ruleset_id_idx ON chart_analyses (ruleset_id);
    CREATE INDEX chart_analyses_corpus_release_id_idx ON chart_analyses (corpus_release_id);
    CREATE INDEX chart_analyses_run_id_idx ON chart_analyses (run_id);

    -- A completed answer is history: it may become stale/withdrawn but never change.
    CREATE FUNCTION bazi_analysis_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.status IN ('completed', 'stale', 'withdrawn')
                AND NEW.answer IS DISTINCT FROM OLD.answer THEN
            RAISE EXCEPTION 'completed analysis % is immutable; create a new analysis', OLD.id
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF OLD.status IN ('completed', 'stale', 'withdrawn')
                AND NEW.status NOT IN ('completed', 'stale', 'withdrawn') THEN
            RAISE EXCEPTION 'analysis % cannot return to %', OLD.id, NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER chart_analyses_frozen BEFORE UPDATE ON chart_analyses
        FOR EACH ROW EXECUTE FUNCTION bazi_analysis_frozen();
    """)

    create_table('rule_traces', """
        analysis_id uuid NOT NULL REFERENCES chart_analyses,
        rule_id uuid NOT NULL REFERENCES knowledge_rules,
        status text NOT NULL CHECK (status IN ('true', 'false', 'unknown', 'conflict', 'skipped')),
        predicates jsonb NOT NULL,
        emissions jsonb NOT NULL,
        conflicts jsonb NOT NULL DEFAULT '[]',
        UNIQUE (analysis_id, rule_id)
    """)
    immutable('rule_traces', 'analysis_id', 'rule_id', 'status', 'predicates', 'emissions',
              'conflicts')
    run('CREATE INDEX rule_traces_rule_id_idx ON rule_traces (rule_id);')

    for kind, table in KINDS.items():
        run(f"""
        INSERT INTO entity_registry (kind, table_name) VALUES ('{kind}', '{table}');
        CREATE TRIGGER {table}_referenced_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION bazi_guard_referenced_delete('{kind}');
        """)


def downgrade() -> None:
    kinds = ', '.join(f"'{k}'" for k in KINDS)
    run(f"""
    DROP TABLE rule_traces, chart_analyses, bazi_charts, birth_profiles, calculation_policies,
        ruleset_members, rulesets;
    DELETE FROM entity_registry WHERE kind IN ({kinds});
    DROP FUNCTION bazi_analysis_frozen(), bazi_policy_transition(), bazi_check_ruleset_member(),
        bazi_snapshot_transition();
    """)
