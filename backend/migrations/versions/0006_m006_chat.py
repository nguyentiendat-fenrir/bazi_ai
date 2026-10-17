"""M006 conversations, messages, chat runs, events, claims, citations, dependencies.

chat_runs ↔ messages (and chart_analyses → chat_runs) form an FK cycle: the
FKs are DEFERRABLE INITIALLY DEFERRED so the API can create the user message,
pending assistant message and run in one transaction (docs/09). Composite FKs
keep runs and messages inside one conversation and one owner.

Revision ID: 0006_m006_chat
Revises: 0005_m005_charts
"""
from alembic import op

revision = '0006_m006_chat'
down_revision = '0005_m005_charts'
branch_labels = None
depends_on = None

KINDS = {'conversation': 'conversations', 'message': 'messages', 'run': 'chat_runs',
         'claim': 'claims'}
DEFERRED = 'DEFERRABLE INITIALLY DEFERRED'


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
    create_table('conversations', """
        owner_id uuid NOT NULL REFERENCES users,
        title text NOT NULL DEFAULT '',
        starred boolean NOT NULL DEFAULT false,
        context jsonb NOT NULL DEFAULT '{}',
        revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
        deleted_at timestamptz,
        UNIQUE (id, owner_id)
    """)
    immutable('conversations', 'owner_id')
    run('CREATE INDEX conversations_owner_updated_idx ON conversations (owner_id, updated_at);')

    create_table('messages', """
        conversation_id uuid NOT NULL REFERENCES conversations,
        seq bigint NOT NULL CHECK (seq >= 1),
        role text NOT NULL CHECK (role IN ('user', 'assistant')),
        content text NOT NULL DEFAULT '',
        structured_answer jsonb,
        status text NOT NULL CHECK (status IN
            ('pending', 'streaming', 'completed', 'failed', 'cancelled')),
        run_id uuid,
        UNIQUE (conversation_id, seq),
        UNIQUE (id, conversation_id)
    """)
    immutable('messages', 'conversation_id', 'seq', 'role')
    run("""
    CREATE INDEX messages_content_fts_idx ON messages USING gin (to_tsvector('simple', content));
    CREATE INDEX messages_run_id_idx ON messages (run_id);
    """)

    create_table('chat_runs', f"""
        conversation_id uuid NOT NULL,
        user_message_id uuid NOT NULL,
        assistant_message_id uuid NOT NULL,
        owner_id uuid NOT NULL REFERENCES users,
        mode text NOT NULL CHECK (mode IN ('research', 'chart_analysis', 'comparison')),
        context_snapshot jsonb NOT NULL,
        model_profile_id uuid REFERENCES model_profiles,
        corpus_release_id uuid REFERENCES corpus_releases,
        state text NOT NULL DEFAULT 'queued' CHECK (state IN
            ('queued', 'running', 'waiting_provider', 'completed', 'failed', 'cancelled')),
        error jsonb,
        prompt_version text NOT NULL,
        UNIQUE (id, conversation_id),
        UNIQUE (user_message_id),
        UNIQUE (assistant_message_id),
        FOREIGN KEY (conversation_id, owner_id) REFERENCES conversations (id, owner_id),
        FOREIGN KEY (user_message_id, conversation_id)
            REFERENCES messages (id, conversation_id) {DEFERRED},
        FOREIGN KEY (assistant_message_id, conversation_id)
            REFERENCES messages (id, conversation_id) {DEFERRED},
        CHECK (user_message_id <> assistant_message_id)
    """)
    immutable('chat_runs', 'conversation_id', 'user_message_id', 'assistant_message_id',
              'owner_id', 'mode', 'context_snapshot', 'model_profile_id', 'corpus_release_id',
              'prompt_version')
    run(f"""
    CREATE INDEX chat_runs_state_updated_idx ON chat_runs (state, updated_at);
    CREATE INDEX chat_runs_conversation_id_idx ON chat_runs (conversation_id, owner_id);
    CREATE INDEX chat_runs_owner_id_idx ON chat_runs (owner_id);
    CREATE INDEX chat_runs_model_profile_id_idx ON chat_runs (model_profile_id);
    CREATE INDEX chat_runs_corpus_release_id_idx ON chat_runs (corpus_release_id);

    ALTER TABLE messages ADD CONSTRAINT messages_run_fkey FOREIGN KEY (run_id, conversation_id)
        REFERENCES chat_runs (id, conversation_id) {DEFERRED};
    ALTER TABLE chart_analyses ADD CONSTRAINT chart_analyses_run_id_fkey FOREIGN KEY (run_id)
        REFERENCES chat_runs {DEFERRED};

    -- Checked at commit, after the run and both messages exist.
    CREATE FUNCTION bazi_check_run_roles() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF (SELECT role FROM messages WHERE id = NEW.user_message_id) IS DISTINCT FROM 'user'
           OR (SELECT role FROM messages WHERE id = NEW.assistant_message_id)
              IS DISTINCT FROM 'assistant' THEN
            RAISE EXCEPTION 'run % must link a user message and an assistant message', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER chat_runs_roles AFTER INSERT ON chat_runs {DEFERRED}
        FOR EACH ROW EXECUTE FUNCTION bazi_check_run_roles();

    CREATE FUNCTION bazi_run_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state IS DISTINCT FROM OLD.state AND (OLD.state, NEW.state) NOT IN (
                ('queued', 'running'), ('queued', 'cancelled'), ('queued', 'failed'),
                ('running', 'waiting_provider'), ('waiting_provider', 'running'),
                ('running', 'completed'), ('running', 'failed'), ('running', 'cancelled'),
                ('waiting_provider', 'failed'), ('waiting_provider', 'cancelled')) THEN
            RAISE EXCEPTION 'run state % -> % is not allowed', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER chat_runs_transition BEFORE UPDATE ON chat_runs
        FOR EACH ROW EXECUTE FUNCTION bazi_run_transition();
    """)

    create_table('run_events', """
        run_id uuid NOT NULL REFERENCES chat_runs,
        seq bigint NOT NULL CHECK (seq >= 1),
        event_type text NOT NULL,
        payload jsonb NOT NULL,
        expires_at timestamptz NOT NULL,
        UNIQUE (run_id, seq)
    """)
    immutable('run_events', 'run_id', 'seq', 'event_type', 'payload', 'expires_at')
    run('CREATE INDEX run_events_expires_at_idx ON run_events (expires_at);')

    create_table('claims', """
        message_id uuid REFERENCES messages,
        analysis_id uuid REFERENCES chart_analyses,
        local_key text NOT NULL,
        text text NOT NULL,
        kind text NOT NULL CHECK (kind IN
            ('calculation', 'rule_result', 'source_statement', 'interpretation', 'limitation')),
        school_id uuid REFERENCES schools,
        support_status text NOT NULL CHECK (support_status IN
            ('validated', 'needs_review', 'insufficient')),
        inference_level text NOT NULL CHECK (inference_level IN
            ('direct', 'conditional', 'interpretive')),
        fact_paths jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(fact_paths) = 'array'),
        trace_refs jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(trace_refs) = 'array'),
        CHECK (num_nonnulls(message_id, analysis_id) >= 1)
    """)
    immutable('claims', 'message_id', 'analysis_id', 'local_key', 'text', 'kind', 'school_id',
              'inference_level', 'fact_paths', 'trace_refs')
    run("""
    CREATE UNIQUE INDEX claims_message_key_uq ON claims (message_id, local_key)
        WHERE message_id IS NOT NULL;
    CREATE UNIQUE INDEX claims_analysis_key_uq ON claims (analysis_id, local_key)
        WHERE analysis_id IS NOT NULL;
    CREATE INDEX claims_message_id_idx ON claims (message_id);
    CREATE INDEX claims_analysis_id_idx ON claims (analysis_id);
    CREATE INDEX claims_school_id_idx ON claims (school_id);
    """)

    create_table('citations', """
        claim_id uuid NOT NULL REFERENCES claims,
        evidence_id uuid NOT NULL REFERENCES evidence_spans,
        chunk_id uuid REFERENCES chunks,
        corpus_release_id uuid NOT NULL REFERENCES corpus_releases,
        validation jsonb NOT NULL,
        display_snapshot jsonb NOT NULL,
        UNIQUE (claim_id, evidence_id)
    """)
    immutable('citations', 'claim_id', 'evidence_id', 'chunk_id', 'corpus_release_id',
              'validation', 'display_snapshot')
    run("""
    CREATE INDEX citations_evidence_id_idx ON citations (evidence_id);
    CREATE INDEX citations_chunk_id_idx ON citations (chunk_id);
    CREATE INDEX citations_corpus_release_id_idx ON citations (corpus_release_id);

    -- The cited source must be in the release the answer was generated from.
    CREATE FUNCTION bazi_check_citation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM evidence_spans e JOIN corpus_members m
                       ON m.book_version_id = e.book_version_id
                       WHERE e.id = NEW.evidence_id AND m.release_id = NEW.corpus_release_id) THEN
            RAISE EXCEPTION 'evidence % is not in corpus release %', NEW.evidence_id,
                NEW.corpus_release_id USING ERRCODE = 'foreign_key_violation';
        END IF;
        IF NEW.chunk_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM corpus_members m JOIN generation_chunks gc
                ON gc.generation_id = m.generation_id
                WHERE m.release_id = NEW.corpus_release_id AND gc.chunk_id = NEW.chunk_id) THEN
            RAISE EXCEPTION 'chunk % is not in corpus release %', NEW.chunk_id,
                NEW.corpus_release_id USING ERRCODE = 'foreign_key_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER citations_membership BEFORE INSERT ON citations
        FOR EACH ROW EXECUTE FUNCTION bazi_check_citation();
    """)

    create_table('analysis_dependencies', """
        analysis_id uuid REFERENCES chart_analyses,
        run_id uuid REFERENCES chat_runs,
        dependency_kind text NOT NULL REFERENCES entity_registry,
        dependency_id uuid NOT NULL,
        content_hash sha256_hex,
        CHECK (num_nonnulls(analysis_id, run_id) >= 1)
    """)
    immutable('analysis_dependencies', 'analysis_id', 'run_id', 'dependency_kind',
              'dependency_id', 'content_hash')
    run("""
    CREATE INDEX analysis_dependencies_target_idx
        ON analysis_dependencies (dependency_kind, dependency_id);
    CREATE INDEX analysis_dependencies_analysis_id_idx ON analysis_dependencies (analysis_id);
    CREATE INDEX analysis_dependencies_run_id_idx ON analysis_dependencies (run_id);
    CREATE TRIGGER analysis_dependencies_target BEFORE INSERT ON analysis_dependencies
        FOR EACH ROW EXECUTE FUNCTION bazi_check_polymorphic('dependency_kind', 'dependency_id');
    """)

    create_table('feedback', """
        user_id uuid NOT NULL REFERENCES users,
        message_id uuid REFERENCES messages,
        analysis_id uuid REFERENCES chart_analyses,
        rating integer NOT NULL CHECK (rating BETWEEN -1 AND 1),
        categories jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(categories) = 'array'),
        comment text,
        CHECK (num_nonnulls(message_id, analysis_id) = 1)
    """)
    run("""
    CREATE INDEX feedback_user_id_idx ON feedback (user_id);
    CREATE INDEX feedback_message_id_idx ON feedback (message_id);
    CREATE INDEX feedback_analysis_id_idx ON feedback (analysis_id);

    CREATE FUNCTION bazi_check_feedback_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NOT EXISTS (
                SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE m.id = NEW.message_id AND c.owner_id = NEW.user_id
                UNION ALL
                SELECT 1 FROM chart_analyses a WHERE a.id = NEW.analysis_id
                AND a.owner_id = NEW.user_id) THEN
            RAISE EXCEPTION 'feedback target is not owned by the user'
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER feedback_owner BEFORE INSERT OR UPDATE ON feedback
        FOR EACH ROW EXECUTE FUNCTION bazi_check_feedback_owner();
    """)

    for kind, table in KINDS.items():
        run(f"""
        INSERT INTO entity_registry (kind, table_name) VALUES ('{kind}', '{table}');
        CREATE TRIGGER {table}_referenced_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION bazi_guard_referenced_delete('{kind}');
        """)


def downgrade() -> None:
    kinds = ', '.join(f"'{k}'" for k in KINDS)
    run(f"""
    ALTER TABLE chart_analyses DROP CONSTRAINT chart_analyses_run_id_fkey;
    ALTER TABLE messages DROP CONSTRAINT messages_run_fkey;
    DROP TABLE feedback, analysis_dependencies, citations, claims, run_events, chat_runs,
        messages, conversations;
    DELETE FROM entity_registry WHERE kind IN ({kinds});
    DROP FUNCTION bazi_check_feedback_owner(), bazi_check_citation(), bazi_run_transition(),
        bazi_check_run_roles();
    """)
