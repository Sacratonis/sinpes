"""persist writer article content scope

Revision ID: 009
Revises: 008
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE article_queue ADD COLUMN content_scope TEXT")
    op.execute(
        """UPDATE article_queue
           SET content_scope = CASE
               WHEN word_count >= 1000 THEN 'deep_dive'
               WHEN word_count >= 650 THEN 'guide'
               ELSE 'brief'
           END
           WHERE content_scope IS NULL"""
    )


def downgrade() -> None:
    pass
