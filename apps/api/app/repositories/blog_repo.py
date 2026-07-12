import sqlite3
from datetime import datetime, timezone
from app.schemas.blog import BlogPost

class BlogRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def check_post_exists(self, slug: str) -> bool:
        row = self.conn.execute("SELECT slug FROM article_queue WHERE slug = ?", (slug,)).fetchone()
        return bool(row)

    def publish_post(self, slug: str) -> None:
        self.conn.execute(
            "UPDATE article_queue SET status = 'published', published_at = ? WHERE slug = ?",
            (datetime.now(timezone.utc).isoformat(), slug),
        )

    def get_published_articles(self):
        return self.conn.execute("SELECT * FROM article_queue WHERE status = 'published'").fetchall()
