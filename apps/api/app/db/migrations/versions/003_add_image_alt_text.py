"""add image_alt_text

Revision ID: 003
Revises: 002
Create Date: 2026-07-10 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        op.execute("ALTER TABLE article_queue ADD COLUMN image_alt_text TEXT;")
    except Exception as e:
        # Ignore if column already exists due to earlier manual execution or models.py sync
        if "duplicate column name" not in str(e).lower():
            raise

def downgrade() -> None:
    pass
