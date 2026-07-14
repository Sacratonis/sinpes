"""preserve Oracle keyword evidence history

Revision ID: 010
Revises: 009
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS oracle_keyword_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            raw_score REAL NOT NULL DEFAULT 0,
            normalized_score REAL NOT NULL DEFAULT 0,
            metric TEXT,
            payload TEXT NOT NULL,
            collected_at TEXT NOT NULL
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_oracle_history_slug_source_time "
        "ON oracle_keyword_history(slug, source, collected_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_oracle_history_slug_source_time")
    op.execute("DROP TABLE IF EXISTS oracle_keyword_history")
