"""M009 per-file results of an ingestion batch.

Contract addition (docs/04, T009): GET /ingestion-batches/{id} must report
every file, including rejected ones that never became an object, version or
job, so a bad file never fails or hides the rest of the batch. Display names
are sanitised base names for people, never used as storage paths.

Revision ID: 0009_m009_batch_items
Revises: 0008_m008_rls
"""
from alembic import op

revision = '0009_m009_batch_items'
down_revision = '0008_m008_rls'
branch_labels = None
depends_on = None


def run(sql: str) -> None:
    # Raw DBAPI cursor without parameters: psycopg then leaves '%' in PL/pgSQL alone.
    op.get_bind().connection.dbapi_connection.cursor().execute(sql)


def upgrade() -> None:
    run("""
    CREATE TABLE ingestion_batch_items (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        batch_id uuid NOT NULL REFERENCES ingestion_batches,
        display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 255),
        outcome text NOT NULL CHECK (outcome IN ('accepted', 'duplicate', 'rejected')),
        error_code text,
        sha256 sha256_hex,
        size_bytes bigint CHECK (size_bytes >= 0),
        object_id uuid REFERENCES objects,
        book_version_id uuid REFERENCES book_versions,
        duplicate_of_version_id uuid REFERENCES book_versions,
        job_id uuid REFERENCES ingestion_jobs,
        CHECK ((outcome = 'rejected') = (error_code IS NOT NULL)),
        CHECK (outcome <> 'accepted' OR book_version_id IS NOT NULL),
        CHECK (outcome <> 'duplicate' OR duplicate_of_version_id IS NOT NULL)
    );
    CREATE TRIGGER ingestion_batch_items_touch BEFORE UPDATE ON ingestion_batch_items
        FOR EACH ROW EXECUTE FUNCTION bazi_touch_updated_at();
    CREATE TRIGGER ingestion_batch_items_immutable BEFORE UPDATE ON ingestion_batch_items
        FOR EACH ROW EXECUTE FUNCTION bazi_guard_immutable(
            'batch_id', 'display_name', 'outcome', 'error_code', 'sha256', 'size_bytes',
            'object_id', 'book_version_id', 'duplicate_of_version_id', 'job_id');
    CREATE INDEX ingestion_batch_items_batch_idx ON ingestion_batch_items (batch_id, created_at);
    CREATE INDEX ingestion_batch_items_object_id_idx ON ingestion_batch_items (object_id);
    CREATE INDEX ingestion_batch_items_book_version_id_idx ON ingestion_batch_items (book_version_id);
    CREATE INDEX ingestion_batch_items_duplicate_idx ON ingestion_batch_items (duplicate_of_version_id);
    CREATE INDEX ingestion_batch_items_job_id_idx ON ingestion_batch_items (job_id);
    """)


def downgrade() -> None:
    run('DROP TABLE ingestion_batch_items;')
