"""add download_zip_url

Revision ID: 004
Revises: 003
Create Date: 2026-07-10 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        op.execute("ALTER TABLE font_registry ADD COLUMN download_zip_url TEXT;")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            raise

def downgrade() -> None:
    pass
