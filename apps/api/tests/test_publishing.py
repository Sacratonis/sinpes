import sqlite3
import unittest

from app.repositories.font_repo import FontRepository
from app.repositories.meta_repo import MetaRepository


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE font_registry (slug TEXT PRIMARY KEY, status TEXT NOT NULL);
            CREATE TABLE categories (slug TEXT PRIMARY KEY);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_drip_batch_activates_only_requested_queued_fonts(self):
        self.connection.executemany(
            "INSERT INTO font_registry (slug, status) VALUES (?, ?)",
            [("one", "queued"), ("two", "queued"), ("three", "vault")],
        )
        self.connection.execute("ALTER TABLE font_registry ADD COLUMN category TEXT")
        self.connection.execute("UPDATE font_registry SET category = 'known'")
        self.connection.execute("INSERT INTO categories(slug) VALUES('known')")

        FontRepository(self.connection).activate_queued_fonts(1)

        statuses = dict(
            self.connection.execute("SELECT slug, status FROM font_registry").fetchall()
        )
        self.assertEqual(statuses["one"], "active")
        self.assertEqual(statuses["two"], "queued")
        self.assertEqual(statuses["three"], "vault")

    def test_publish_does_not_activate_font_with_pending_category(self):
        self.connection.execute("ALTER TABLE font_registry ADD COLUMN category TEXT")
        self.connection.execute(
            "INSERT INTO font_registry(slug, status, category) VALUES('waiting', 'queued', 'new-category')"
        )

        FontRepository(self.connection).activate_queued_fonts(48)

        status = self.connection.execute(
            "SELECT status FROM font_registry WHERE slug = 'waiting'"
        ).fetchone()[0]
        self.assertEqual(status, "queued")

    def test_build_lock_can_be_cleared(self):
        repository = MetaRepository(self.connection)
        repository.set_value("build_in_progress", "true")
        repository.set_value("build_in_progress", "false")

        self.assertEqual(repository.get_value("build_in_progress"), "false")


if __name__ == "__main__":
    unittest.main()
