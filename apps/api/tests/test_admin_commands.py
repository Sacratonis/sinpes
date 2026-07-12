import json
import sqlite3
import unittest
from unittest.mock import patch

from app.ingestion.category_resolver import resolve_category
from app.repositories.category_repo import CategoryRepository
from app.repositories.queue_repo import QueueRepository
from app.services.admin_actions import confirm_erase, prepare_erase


class AdminCommandTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE categories (slug TEXT PRIMARY KEY, display_name TEXT UNIQUE);
            CREATE TABLE pending_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                expires_at TEXT NOT NULL, resolved BOOLEAN NOT NULL DEFAULT 0
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE font_registry (
                slug TEXT PRIMARY KEY, display_name TEXT, status TEXT,
                category TEXT, variants TEXT, woff2_url TEXT, download_zip_url TEXT
            );
            CREATE TABLE font_translations (
                slug TEXT, locale TEXT, seo_image_url TEXT
            );
            CREATE TABLE upload_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT DEFAULT '',
                text_payload TEXT, image_path TEXT DEFAULT '', received_at TEXT DEFAULT '',
                processed BOOLEAN DEFAULT 0, attempts INTEGER DEFAULT 0,
                last_error TEXT, failed BOOLEAN DEFAULT 0
            );
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_unknown_category_waits_for_explicit_id_approval(self):
        alerts = []
        slug = resolve_category(self.connection, "Monospaced", False, alerts.append)
        pending = CategoryRepository(self.connection).get_unresolved_pending_categories()

        self.assertEqual(slug, "monospaced")
        self.assertEqual(len(pending), 1)
        self.assertIn(f"/category_confirm {pending[0].id}", alerts[0])
        self.assertFalse(CategoryRepository(self.connection).check_category_exists(slug))

    def test_retry_only_resets_failed_item(self):
        self.connection.execute(
            "INSERT INTO upload_queue(text_payload, failed, attempts, last_error) VALUES(?, 1, 3, 'bad')",
            ("{}",),
        )
        repository = QueueRepository(self.connection)
        self.assertTrue(repository.retry_item(1))
        row = self.connection.execute("SELECT * FROM upload_queue WHERE id = 1").fetchone()
        self.assertEqual((row["failed"], row["attempts"], row["last_error"]), (0, 0, None))

    @patch("app.services.admin_actions.delete_r2_objects", return_value=4)
    def test_erase_requires_preview_then_deletes_db_and_r2(self, delete_objects):
        base = "https://pub-ba3e9b7a820041848227936dc3222808.r2.dev"
        variants = json.dumps([{"url": f"{base}/fonts/demo-400-normal.woff2"}])
        self.connection.execute(
            "INSERT INTO font_registry VALUES(?, ?, ?, ?, ?, ?, ?)",
            ("demo", "Demo", "active", "sans-serif", variants,
             f"{base}/fonts/demo-400-normal.woff2", f"{base}/downloads/demo.zip"),
        )
        self.connection.execute(
            "INSERT INTO font_translations VALUES(?, ?, ?)",
            ("demo", "en", f"{base}/images/demo.webp"),
        )
        self.connection.execute(
            "INSERT INTO upload_queue(text_payload) VALUES(?)", (json.dumps({"slug": "demo"}),)
        )

        font, keys = prepare_erase(self.connection, "demo")
        self.assertEqual(font["slug"], "demo")
        self.assertGreaterEqual(len(keys), 3)
        self.assertEqual(confirm_erase(self.connection, "demo"), 4)
        self.assertIsNone(self.connection.execute(
            "SELECT slug FROM font_registry WHERE slug = 'demo'"
        ).fetchone())
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM upload_queue").fetchone()[0], 0)
        delete_objects.assert_called_once()


if __name__ == "__main__":
    unittest.main()
