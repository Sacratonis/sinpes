"""persist verified variable-font capability

Revision ID: 014
Revises: 013
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE font_registry ADD COLUMN is_variable BOOLEAN NOT NULL DEFAULT 0")


def downgrade() -> None:
    # Existing SQLite deployments may not support a safe column drop. Keeping
    # the verified capability is safer than rebuilding this core table.
    pass
