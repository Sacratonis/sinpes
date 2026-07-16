"""repair duplicate and transient image queue failures

Revision ID: 013
Revises: 012
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A file-hash uniqueness error proves the family is already present. Treat
    # those historical rows as completed instead of keeping false failures.
    op.execute(
        """UPDATE upload_queue
           SET processed = 1,
               failed = 0,
               last_error = 'Duplicate upload skipped because the font is already saved.'
           WHERE failed = 1
             AND last_error LIKE 'UNIQUE constraint failed: font_registry.file_hash%'"""
    )

    # Historical provider outages should enter the new deferred-retry path.
    op.execute(
        """UPDATE upload_queue
           SET processed = 0,
               failed = 0,
               attempts = 0,
               last_error = NULL,
               received_at = strftime('%s', 'now')
           WHERE failed = 1
             AND last_error LIKE 'ORCHESTRATOR: Hero image generation failed%'"""
    )


def downgrade() -> None:
    # Historical failure states cannot be reconstructed safely.
    pass
