"""clean existing font display names

Revision ID: 007
Revises: 006
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE font_registry SET display_name = 'BUSE' WHERE slug = 'buse'")


def downgrade() -> None:
    pass
