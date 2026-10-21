"""M019 the ``summarize`` ingestion stage (RAG pilot parent summaries); index eval_runs FK.

Revision ID: 0019_m019_summarize_stage
Revises: 0018_m018_rag_parents
"""
from alembic import op

revision = '0019_m019_summarize_stage'
down_revision = '0018_m018_rag_parents'
branch_labels = None
depends_on = None

STAGES = ("'validate', 'dedupe', 'inspect', 'extract', 'ocr', 'normalize', 'structure',"
          " 'quality', 'chunk', 'embed', 'extract_candidates', 'publish'")


def upgrade() -> None:
    op.execute('ALTER TABLE job_stages DROP CONSTRAINT job_stages_stage_check')
    op.execute(f"ALTER TABLE job_stages ADD CONSTRAINT job_stages_stage_check"
               f" CHECK (stage IN ({STAGES}, 'summarize'))")
    op.execute('CREATE INDEX IF NOT EXISTS eval_runs_created_by_idx ON eval_runs (created_by)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS eval_runs_created_by_idx')
    op.execute("DELETE FROM job_stages WHERE stage = 'summarize'")
    op.execute('ALTER TABLE job_stages DROP CONSTRAINT job_stages_stage_check')
    op.execute(f'ALTER TABLE job_stages ADD CONSTRAINT job_stages_stage_check CHECK (stage IN ({STAGES}))')
