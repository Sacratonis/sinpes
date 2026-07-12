import sqlite3
from typing import Optional, List
from app.schemas.font import FontRegistry, FontTranslation

class FontRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_snapshot_batch(self, last_rowid: int, limit: int) -> List[FontRegistry]:
        rows = self.conn.execute(
            "SELECT rowid, * FROM font_registry WHERE status = 'active' AND rowid > ? ORDER BY rowid ASC LIMIT ?", 
            (last_rowid, limit)
        ).fetchall()
        return [FontRegistry(**dict(row)) for row in rows]

    def get_translations_for_slugs(self, slugs: List[str]) -> List[FontTranslation]:
        if not slugs:
            return []
        placeholders = ','.join(['?'] * len(slugs))
        rows = self.conn.execute(
            f"SELECT * FROM font_translations WHERE slug IN ({placeholders})", 
            tuple(slugs)
        ).fetchall()
        return [FontTranslation(**dict(row)) for row in rows]
        
    def soft_delete_font(self, slug: str) -> None:
        self.conn.execute("UPDATE font_registry SET status = 'removed' WHERE slug = ?", (slug,))

    def get_all_slugs(self) -> List[str]:
        rows = self.conn.execute("SELECT slug FROM font_registry").fetchall()
        return [row['slug'] for row in rows]

    def activate_queued_fonts(self, limit: int) -> None:
        self.conn.execute("""
            UPDATE font_registry SET status = 'active'
            WHERE slug IN (
                SELECT font_registry.slug FROM font_registry
                INNER JOIN categories ON categories.slug = font_registry.category
                WHERE font_registry.status = 'queued'
                ORDER BY font_registry.rowid ASC LIMIT ?
            )
        """, (limit,))

    def check_hash_exists(self, file_hash: str) -> bool:
        row = self.conn.execute("SELECT slug FROM font_registry WHERE file_hash = ?", (file_hash,)).fetchone()
        return bool(row)

    def insert_font(self, font: FontRegistry) -> None:
        self.conn.execute(
            """INSERT INTO font_registry (
                slug, display_name, is_demo, category, variants, weights, 
                woff2_url, file_format, file_size_kb, use_cases, status, 
                vault_status, file_hash, embedded_family_name, last_updated, download_zip_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                font.slug, font.display_name, font.is_demo, font.category, 
                font.variants, font.weights, font.woff2_url, font.file_format, 
                font.file_size_kb, font.use_cases, font.status, font.vault_status, 
                font.file_hash, font.embedded_family_name, font.last_updated, font.download_zip_url
            )
        )
        
    def insert_translation(self, translation: FontTranslation) -> None:
        self.conn.execute(
            """INSERT INTO font_translations (slug, locale, description, seo_image_url)
               VALUES (?, ?, ?, ?)""",
            (translation.slug, translation.locale, translation.description, translation.seo_image_url)
        )
