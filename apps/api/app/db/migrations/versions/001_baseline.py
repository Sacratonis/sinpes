"""baseline

Revision ID: 001
Revises: 
Create Date: 2026-07-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS font_registry (
            slug TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            is_demo BOOLEAN NOT NULL DEFAULT 0,
            category TEXT NOT NULL,
            variants TEXT NOT NULL,
            weights TEXT,
            woff2_url TEXT NOT NULL,
            file_format TEXT NOT NULL,
            file_size_kb INTEGER NOT NULL,
            use_cases TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'vault',
            vault_status TEXT,
            file_hash TEXT NOT NULL UNIQUE,
            embedded_family_name TEXT,
            last_updated TEXT NOT NULL
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS font_translations (
            slug TEXT NOT NULL,
            locale TEXT NOT NULL,
            description TEXT NOT NULL,
            seo_image_url TEXT NOT NULL,
            PRIMARY KEY (slug, locale),
            FOREIGN KEY (slug) REFERENCES font_registry(slug) ON DELETE CASCADE
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            slug TEXT PRIMARY KEY,
            display_name TEXT NOT NULL UNIQUE
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pending_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            resolved BOOLEAN NOT NULL DEFAULT 0
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS upload_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            text_payload TEXT NOT NULL,
            image_path TEXT NOT NULL,
            received_at TEXT NOT NULL,
            processed BOOLEAN NOT NULL DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            failed INTEGER DEFAULT 0
        );
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

def downgrade() -> None:
    pass
