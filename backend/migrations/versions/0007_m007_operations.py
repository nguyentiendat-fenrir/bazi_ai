"""M007 ingestion jobs, outbox, idempotency, evaluation, usage/budget, operations, audit.

PostgreSQL is the source of truth for work (docs/05, ADR-06): stages carry an
idempotency key, lease and fencing token; at most one active ingestion job per
book version and pipeline profile (partial unique index). ``ingestion_jobs``
stores ``pipeline_profile_id`` — not in the original data dictionary — so that
rule is a plain index rather than a racy trigger; a composite FK keeps it equal
to the generation's profile.

Revision ID: 0007_m007_operations
Revises: 0006_m006_chat
"""
from alembic import op

revision = '0007_m007_operations'
down_revision = '0006_m006_chat'
branch_labels = None
depends_on = None

JOB_ACTIVE = "('queued', 'running', 'retry_wait', 'waiting_review', 'cancel_requested')"
STAGES = ("('validate', 'dedupe', 'inspect', 'extract', 'ocr', 'normalize', 'structure',"
          " 'quality', 'chunk', 'embed', 'extract_candidates', 'publish')")


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
    # ---- ingestion ----------------------------------------------------------------
    create_table('ingestion_batches', """
        created_by uuid NOT NULL REFERENCES users,
        name text NOT NULL,
        state text NOT NULL DEFAULT 'open' CHECK (state IN
            ('open', 'running', 'completed', 'partial', 'failed', 'cancelled')),
        config jsonb NOT NULL DEFAULT '{}'
    """)
    run('CREATE INDEX ingestion_batches_created_idx ON ingestion_batches (created_by, created_at);')

    run('ALTER TABLE generations ADD CONSTRAINT generations_id_profile_key'
        ' UNIQUE (id, pipeline_profile_id);')
    create_table('ingestion_jobs', f"""
        batch_id uuid REFERENCES ingestion_batches,
        book_version_id uuid NOT NULL REFERENCES book_versions,
        generation_id uuid NOT NULL,
        pipeline_profile_id uuid NOT NULL REFERENCES pipeline_profiles,
        parent_job_id uuid REFERENCES ingestion_jobs,
        requested_by uuid NOT NULL REFERENCES users,
        state text NOT NULL DEFAULT 'queued' CHECK (state IN
            ('queued', 'running', 'retry_wait', 'waiting_review', 'cancel_requested',
             'succeeded', 'partial', 'failed', 'cancelled')),
        counters jsonb NOT NULL DEFAULT '{{}}',
        error jsonb,
        cancel_requested boolean NOT NULL DEFAULT false,
        FOREIGN KEY (generation_id, book_version_id) REFERENCES generations (id, book_version_id),
        FOREIGN KEY (generation_id, pipeline_profile_id)
            REFERENCES generations (id, pipeline_profile_id),
        CHECK (parent_job_id <> id)
    """)
    immutable('ingestion_jobs', 'batch_id', 'book_version_id', 'generation_id',
              'pipeline_profile_id', 'parent_job_id', 'requested_by')
    run(f"""
    CREATE UNIQUE INDEX ingestion_jobs_one_active_uq
        ON ingestion_jobs (book_version_id, pipeline_profile_id) WHERE state IN {JOB_ACTIVE};
    CREATE INDEX ingestion_jobs_state_updated_idx ON ingestion_jobs (state, updated_at);
    CREATE INDEX ingestion_jobs_active_idx ON ingestion_jobs (updated_at)
        WHERE state IN {JOB_ACTIVE};
    CREATE INDEX ingestion_jobs_batch_id_idx ON ingestion_jobs (batch_id);
    CREATE INDEX ingestion_jobs_book_version_id_idx ON ingestion_jobs (book_version_id);
    CREATE INDEX ingestion_jobs_generation_id_idx ON ingestion_jobs (generation_id);
    CREATE INDEX ingestion_jobs_pipeline_profile_id_idx ON ingestion_jobs (pipeline_profile_id);
    CREATE INDEX ingestion_jobs_parent_job_id_idx ON ingestion_jobs (parent_job_id);
    CREATE INDEX ingestion_jobs_requested_by_idx ON ingestion_jobs (requested_by);

    -- docs/05 job state machine; terminal states are retried by a new child job.
    CREATE FUNCTION bazi_job_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state IS DISTINCT FROM OLD.state AND (OLD.state, NEW.state) NOT IN (
                ('queued', 'running'), ('running', 'succeeded'), ('running', 'partial'),
                ('running', 'failed'), ('running', 'retry_wait'), ('retry_wait', 'queued'),
                ('running', 'waiting_review'), ('waiting_review', 'queued'),
                ('queued', 'cancel_requested'), ('running', 'cancel_requested'),
                ('retry_wait', 'cancel_requested'), ('waiting_review', 'cancel_requested'),
                ('cancel_requested', 'cancelled')) THEN
            RAISE EXCEPTION 'job state % -> % is not allowed', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER ingestion_jobs_transition BEFORE UPDATE ON ingestion_jobs
        FOR EACH ROW EXECUTE FUNCTION bazi_job_transition();
    """)

    create_table('job_stages', f"""
        job_id uuid NOT NULL REFERENCES ingestion_jobs,
        stage text NOT NULL CHECK (stage IN {STAGES}),
        unit_key text NOT NULL,
        input_hash sha256_hex NOT NULL,
        idempotency_key sha256_hex NOT NULL UNIQUE,
        state text NOT NULL DEFAULT 'pending' CHECK (state IN
            ('pending', 'running', 'succeeded', 'failed', 'skipped')),
        attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
        checkpoint jsonb NOT NULL DEFAULT '{{}}',
        output_ref jsonb,
        lease_until timestamptz,
        fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
        worker_id text,
        CHECK (state <> 'running' OR (lease_until IS NOT NULL AND worker_id IS NOT NULL))
    """)
    immutable('job_stages', 'job_id', 'stage', 'unit_key', 'input_hash', 'idempotency_key')
    run("""
    CREATE INDEX job_stages_state_lease_idx ON job_stages (state, lease_until);
    CREATE INDEX job_stages_job_id_idx ON job_stages (job_id, stage);

    CREATE FUNCTION bazi_fencing_monotonic() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.fencing_token < OLD.fencing_token THEN
            RAISE EXCEPTION 'fencing_token never decreases' USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER job_stages_fencing BEFORE UPDATE ON job_stages
        FOR EACH ROW EXECUTE FUNCTION bazi_fencing_monotonic();
    """)

    create_table('job_events', """
        job_id uuid NOT NULL REFERENCES ingestion_jobs,
        seq bigint NOT NULL CHECK (seq >= 1),
        level text NOT NULL CHECK (level IN ('debug', 'info', 'warning', 'error')),
        code text NOT NULL,
        payload jsonb NOT NULL DEFAULT '{}',
        UNIQUE (job_id, seq)
    """)
    immutable('job_events', 'job_id', 'seq', 'level', 'code', 'payload')

    # ---- messaging and idempotency ------------------------------------------------
    create_table('outbox_events', """
        event_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
        topic text NOT NULL,
        payload jsonb NOT NULL,
        published_at timestamptz,
        attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0)
    """)
    immutable('outbox_events', 'event_id', 'topic', 'payload')
    run('CREATE INDEX outbox_events_unpublished_idx ON outbox_events (created_at)'
        ' WHERE published_at IS NULL;')

    create_table('processed_events', """
        consumer text NOT NULL,
        event_id uuid NOT NULL,
        processed_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (consumer, event_id)
    """)

    create_table('idempotency_keys', """
        owner_id uuid NOT NULL REFERENCES users,
        route text NOT NULL,
        key text NOT NULL CHECK (char_length(key) BETWEEN 1 AND 128),
        request_hash sha256_hex NOT NULL,
        status text NOT NULL CHECK (status IN ('in_progress', 'completed')),
        response_code integer CHECK (response_code BETWEEN 100 AND 599),
        response jsonb,
        expires_at timestamptz NOT NULL,
        UNIQUE (owner_id, route, key),
        CHECK (status <> 'completed' OR response_code IS NOT NULL)
    """)
    immutable('idempotency_keys', 'owner_id', 'route', 'key', 'request_hash')
    run('CREATE INDEX idempotency_keys_expires_at_idx ON idempotency_keys (expires_at);')

    # ---- evaluation ---------------------------------------------------------------
    create_table('evaluation_datasets', """
        name text NOT NULL,
        version text NOT NULL,
        split_manifest jsonb NOT NULL DEFAULT '{}',
        rights jsonb NOT NULL DEFAULT '{}',
        state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'approved', 'retired')),
        UNIQUE (name, version)
    """)
    create_table('evaluation_items', """
        dataset_id uuid NOT NULL REFERENCES evaluation_datasets,
        key text NOT NULL,
        kind text NOT NULL CHECK (kind IN ('retrieval', 'answer', 'calculation', 'rule', 'no_answer')),
        input jsonb NOT NULL,
        expected jsonb NOT NULL,
        source_manifest jsonb NOT NULL DEFAULT '{}',
        reviewer_id uuid REFERENCES users,
        split text NOT NULL CHECK (split IN ('dev', 'test', 'holdout')),
        UNIQUE (dataset_id, key)
    """)
    run("""
    CREATE INDEX evaluation_items_reviewer_id_idx ON evaluation_items (reviewer_id);

    -- docs/13: gold must be reviewed before its dataset is approved for release gates.
    CREATE FUNCTION bazi_dataset_reviewed() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.state = 'approved' AND OLD.state <> 'approved' AND EXISTS (
                SELECT 1 FROM evaluation_items WHERE dataset_id = NEW.id AND reviewer_id IS NULL) THEN
            RAISE EXCEPTION 'dataset % has unreviewed items', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$;
    CREATE TRIGGER evaluation_datasets_reviewed BEFORE UPDATE OF state ON evaluation_datasets
        FOR EACH ROW EXECUTE FUNCTION bazi_dataset_reviewed();
    """)

    create_table('evaluation_runs', """
        dataset_id uuid NOT NULL REFERENCES evaluation_datasets,
        requested_by uuid NOT NULL REFERENCES users,
        config_snapshot jsonb NOT NULL,
        status text NOT NULL DEFAULT 'queued' CHECK (status IN
            ('queued', 'running', 'completed', 'failed', 'cancelled')),
        metrics jsonb NOT NULL DEFAULT '{}',
        report_object_id uuid REFERENCES objects
    """)
    run("""
    CREATE INDEX evaluation_runs_status_created_idx ON evaluation_runs (status, created_at);
    CREATE INDEX evaluation_runs_dataset_id_idx ON evaluation_runs (dataset_id);
    CREATE INDEX evaluation_runs_requested_by_idx ON evaluation_runs (requested_by);
    CREATE INDEX evaluation_runs_report_object_id_idx ON evaluation_runs (report_object_id);
    """)

    create_table('evaluation_results', """
        run_id uuid NOT NULL REFERENCES evaluation_runs,
        item_id uuid NOT NULL REFERENCES evaluation_items,
        actual jsonb NOT NULL,
        scores jsonb NOT NULL,
        status text NOT NULL CHECK (status IN ('passed', 'failed', 'error', 'skipped')),
        duration_ms integer NOT NULL CHECK (duration_ms >= 0),
        UNIQUE (run_id, item_id)
    """)
    run('CREATE INDEX evaluation_results_item_id_idx ON evaluation_results (item_id);')

    # ---- usage and budget ---------------------------------------------------------
    create_table('usage_records', """
        owner_id uuid NOT NULL REFERENCES users,
        run_id uuid REFERENCES chat_runs,
        job_id uuid REFERENCES ingestion_jobs,
        profile_id uuid NOT NULL REFERENCES model_profiles,
        provider_request_id text,
        input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
        output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
        estimated_cost numeric(18,8) NOT NULL CHECK (estimated_cost >= 0),
        actual_cost numeric(18,8) CHECK (actual_cost >= 0),
        currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
        status text NOT NULL CHECK (status IN ('reserved', 'completed', 'failed', 'reconciled'))
    """)
    run("""
    CREATE INDEX usage_records_owner_created_idx ON usage_records (owner_id, created_at);
    CREATE INDEX usage_records_run_id_idx ON usage_records (run_id);
    CREATE INDEX usage_records_job_id_idx ON usage_records (job_id);
    CREATE INDEX usage_records_profile_id_idx ON usage_records (profile_id);
    """)

    create_table('budget_reservations', """
        owner_id uuid NOT NULL REFERENCES users,
        usage_id uuid NOT NULL REFERENCES usage_records,
        reserved_cost numeric(18,8) NOT NULL CHECK (reserved_cost >= 0),
        expires_at timestamptz NOT NULL,
        status text NOT NULL DEFAULT 'held' CHECK (status IN
            ('held', 'consumed', 'released', 'expired'))
    """)
    run("""
    CREATE INDEX budget_reservations_owner_held_idx ON budget_reservations (owner_id, expires_at)
        WHERE status = 'held';
    CREATE INDEX budget_reservations_owner_id_idx ON budget_reservations (owner_id);
    CREATE INDEX budget_reservations_usage_id_idx ON budget_reservations (usage_id);
    """)

    # ---- operations ---------------------------------------------------------------
    create_table('operation_jobs', """
        kind text NOT NULL CHECK (kind IN ('deletion', 'backup', 'restore', 'reindex', 'reevaluate')),
        requested_by uuid NOT NULL REFERENCES users,
        state text NOT NULL DEFAULT 'queued' CHECK (state IN
            ('queued', 'running', 'retry_wait', 'cancel_requested', 'succeeded', 'failed',
             'cancelled')),
        progress jsonb NOT NULL DEFAULT '{}',
        error jsonb,
        target_manifest jsonb NOT NULL,
        idempotency_key sha256_hex NOT NULL UNIQUE,
        lease_until timestamptz,
        fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
        checkpoint jsonb NOT NULL DEFAULT '{}',
        cancel_requested boolean NOT NULL DEFAULT false
    """)
    immutable('operation_jobs', 'kind', 'requested_by', 'target_manifest', 'idempotency_key')
    run("""
    CREATE INDEX operation_jobs_state_lease_idx ON operation_jobs (state, lease_until);
    CREATE INDEX operation_jobs_requested_by_idx ON operation_jobs (requested_by);
    CREATE TRIGGER operation_jobs_fencing BEFORE UPDATE ON operation_jobs
        FOR EACH ROW EXECUTE FUNCTION bazi_fencing_monotonic();
    """)

    create_table('backups', """
        operation_job_id uuid NOT NULL REFERENCES operation_jobs,
        manifest_object_id uuid NOT NULL REFERENCES objects,
        archive_location text NOT NULL,
        db_schema_version text NOT NULL,
        checksum sha256_hex NOT NULL,
        encryption_key_ref text NOT NULL,
        state text NOT NULL CHECK (state IN ('running', 'succeeded', 'failed', 'verified')),
        verified_at timestamptz,
        CHECK ((state = 'verified') = (verified_at IS NOT NULL))
    """)
    run("""
    CREATE INDEX backups_operation_job_id_idx ON backups (operation_job_id);
    CREATE INDEX backups_manifest_object_id_idx ON backups (manifest_object_id);
    """)

    create_table('audit_logs', """
        actor_id uuid REFERENCES users,
        action text NOT NULL,
        target_kind text,
        target_id uuid,
        trace_id text NOT NULL,
        redacted_diff jsonb NOT NULL DEFAULT '{}',
        outcome text NOT NULL CHECK (outcome IN ('success', 'denied', 'failed'))
    """)
    run("""
    CREATE INDEX audit_logs_target_idx ON audit_logs (target_kind, target_id, created_at);
    CREATE INDEX audit_logs_actor_id_idx ON audit_logs (actor_id);

    -- Never edited; deleted only by the retention job (docs/12, default 180 days),
    -- which sets bazi.retention for its own transaction.
    CREATE FUNCTION bazi_audit_retention_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'UPDATE' OR current_setting('bazi.retention', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'audit_logs is append-only' USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN OLD;
    END $$;
    CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION bazi_audit_retention_only();
    """)


def downgrade() -> None:
    run("""
    DROP TABLE audit_logs, backups, operation_jobs, budget_reservations, usage_records,
        evaluation_results, evaluation_runs, evaluation_items, evaluation_datasets,
        idempotency_keys, processed_events, outbox_events, job_events, job_stages,
        ingestion_jobs, ingestion_batches;
    ALTER TABLE generations DROP CONSTRAINT generations_id_profile_key;
    DROP FUNCTION bazi_audit_retention_only(), bazi_dataset_reviewed(), bazi_fencing_monotonic(),
        bazi_job_transition();
    """)
