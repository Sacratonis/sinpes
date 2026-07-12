"""add article_queue

Revision ID: 002
Revises: 001
Create Date: 2026-07-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS article_queue (
            id TEXT PRIMARY KEY,
            source_topic TEXT NOT NULL,
            source_keyword_data TEXT, -- JSON
            language TEXT NOT NULL,
            validity TEXT NOT NULL, -- 'valid' or 'invalid'
            validity_reasoning TEXT,
            title TEXT,
            slug TEXT,
            meta_description TEXT,
            target_keyword TEXT,
            secondary_keywords TEXT, -- JSON array
            body_markdown TEXT,
            referenced_font_slugs TEXT, -- JSON array
            image_prompt TEXT,
            image_url TEXT,
            word_count INTEGER,
            status TEXT NOT NULL DEFAULT 'pending_review', -- pending_review, approved, edited, rejected, published
            rejection_note TEXT,
            created_at TEXT NOT NULL,
            published_at TEXT
        );
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS article_queue;")
