"""add safe fallback font category

Revision ID: 015
Revises: 014
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT OR IGNORE INTO categories(slug, display_name) "
        "VALUES('uncategorized', 'Uncategorized')"
    )


def downgrade() -> None:
    # Keep the row when fonts depend on it. Removing a category during rollback
    # would make existing font records unschedulable.
    pass
