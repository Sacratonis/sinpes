"""refine writer article contract

Revision ID: 008
Revises: 007
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE article_queue ADD COLUMN body_html TEXT")
    op.execute("ALTER TABLE article_queue ADD COLUMN font_claims TEXT")
    op.execute("UPDATE article_queue SET body_html = body_markdown WHERE body_html IS NULL")


def downgrade() -> None:
    pass
