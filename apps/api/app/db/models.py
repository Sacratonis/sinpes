import sqlite3

def create_tables(conn: sqlite3.Connection):
    conn.executescript("""
        -- Core Shared Data
        CREATE TABLE IF NOT EXISTS font_registry (
            slug TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            is_demo BOOLEAN NOT NULL DEFAULT 0,
            is_variable BOOLEAN NOT NULL DEFAULT 0,
            category TEXT NOT NULL,
            variants TEXT NOT NULL, -- JSON array
            weights TEXT,           -- JSON array or null
            woff2_url TEXT NOT NULL,
            download_zip_url TEXT,
            file_format TEXT NOT NULL,
            file_size_kb INTEGER NOT NULL,
            use_cases TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'vault', -- vault -> queued -> active
            vault_status TEXT,                    -- null or 'corrupt'
            file_hash TEXT NOT NULL UNIQUE,       -- SHA-256
            embedded_family_name TEXT,
            last_updated TEXT NOT NULL
        );

        -- Per-Language Localized Data
        CREATE TABLE IF NOT EXISTS font_translations (
            slug TEXT NOT NULL,
            locale TEXT NOT NULL,
            description TEXT NOT NULL,
            seo_image_url TEXT NOT NULL,
            PRIMARY KEY (slug, locale),
            FOREIGN KEY (slug) REFERENCES font_registry(slug) ON DELETE CASCADE
        );

        -- Categories
        CREATE TABLE IF NOT EXISTS categories (
            slug TEXT PRIMARY KEY,
            display_name TEXT NOT NULL UNIQUE
        );

        -- Pending Categories (Grace Period Queue)
        CREATE TABLE IF NOT EXISTS pending_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            resolved BOOLEAN NOT NULL DEFAULT 0
        );

        -- Internal Queue
        CREATE TABLE IF NOT EXISTS upload_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            text_payload TEXT NOT NULL,
            image_path TEXT NOT NULL,
            received_at TEXT NOT NULL,
            processed BOOLEAN NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            failed BOOLEAN NOT NULL DEFAULT 0
        );

        -- Key-Value System State
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

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
        );

        CREATE TABLE IF NOT EXISTS oracle_keyword_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            raw_score REAL NOT NULL DEFAULT 0,
            normalized_score REAL NOT NULL DEFAULT 0,
            metric TEXT,
            payload TEXT NOT NULL,
            collected_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_oracle_history_slug_source_time
            ON oracle_keyword_history(slug, source, collected_at);

        -- SEO Expert Bot: Article Queue
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
            body_html TEXT,
            font_claims TEXT,
            referenced_font_slugs TEXT, -- JSON array
            image_prompt TEXT,
            image_url TEXT,
            image_alt_text TEXT,
            word_count INTEGER,
            content_scope TEXT,
            status TEXT NOT NULL DEFAULT 'pending_review', -- pending_review, approved, edited, rejected, published
            rejection_note TEXT,
            created_at TEXT NOT NULL,
            published_at TEXT
        );
    """)
