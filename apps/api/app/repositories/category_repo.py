import sqlite3
from typing import Optional
from app.schemas.category import Category, PendingCategory

class CategoryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_category(self, slug: str, display_name: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO categories (slug, display_name) VALUES (?, ?)",
            (slug, display_name)
        )
        
    def check_category_exists(self, slug: str) -> bool:
        row = self.conn.execute("SELECT slug FROM categories WHERE slug = ?", (slug,)).fetchone()
        return bool(row)

    def add_pending_category(self, name: str, expires_at: str) -> None:
        self.conn.execute(
            "INSERT INTO pending_categories (name, expires_at) VALUES (?, ?)", 
            (name, expires_at)
        )

    def get_unresolved_pending_category_by_name(self, name: str) -> Optional[PendingCategory]:
        row = self.conn.execute(
            "SELECT * FROM pending_categories WHERE resolved = 0 AND name = ?", 
            (name,)
        ).fetchone()
        return PendingCategory(**dict(row)) if row else None

    def get_unresolved_pending_category(self, category_id: int) -> Optional[PendingCategory]:
        row = self.conn.execute(
            "SELECT * FROM pending_categories WHERE resolved = 0 AND id = ?",
            (category_id,),
        ).fetchone()
        return PendingCategory(**dict(row)) if row else None

    def get_unresolved_pending_categories(self) -> list[PendingCategory]:
        rows = self.conn.execute(
            "SELECT * FROM pending_categories WHERE resolved = 0 ORDER BY id ASC"
        ).fetchall()
        return [PendingCategory(**dict(row)) for row in rows]
        
    def resolve_pending_category(self, category_id: int) -> None:
        self.conn.execute(
            "UPDATE pending_categories SET resolved = 1 WHERE id = ?", 
            (category_id,)
        )

    def get_expired_pending_categories(self, current_time: str) -> list[PendingCategory]:
        rows = self.conn.execute(
            "SELECT * FROM pending_categories WHERE resolved = 0 AND expires_at < ?", 
            (current_time,)
        ).fetchall()
        return [PendingCategory(**dict(row)) for row in rows]

    def get_fonts_using_category(self, category_slug: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT slug FROM font_registry WHERE category = ?", 
            (category_slug,)
        ).fetchall()
        return [row['slug'] for row in rows]

    def delete_category(self, category_slug: str) -> None:
        self.conn.execute(
            "DELETE FROM categories WHERE slug = ?", 
            (category_slug,)
        )
        
    def update_category_name(self, category_slug: str, new_name: str) -> None:
        self.conn.execute(
            "UPDATE categories SET display_name = ? WHERE slug = ?", 
            (new_name, category_slug)
        )
