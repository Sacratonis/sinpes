"""add oracle keyword storage

Revision ID: 006
Revises: 005
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS oracle_keywords (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            region TEXT,
            score REAL NOT NULL DEFAULT 0,
            metric TEXT,
            rank INTEGER NOT NULL,
            payload TEXT NOT NULL,
            collected_at TEXT NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oracle_keywords")
