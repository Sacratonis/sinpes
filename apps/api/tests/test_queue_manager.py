import sqlite3
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.ingestion.media_processor import HeroImageGenerationError
from app.services.queue_manager import DuplicateFontUpload, release_next_from_queue


class QueueManagerTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """CREATE TABLE upload_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL DEFAULT '',
                text_payload TEXT NOT NULL DEFAULT '{}',
                image_path TEXT NOT NULL DEFAULT '',
                received_at TEXT NOT NULL,
                processed BOOLEAN NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                failed BOOLEAN NOT NULL DEFAULT 0
            )"""
        )

    def tearDown(self):
        self.connection.close()

    def _insert_item(self):
        self.connection.execute(
            "INSERT INTO upload_queue(received_at) VALUES(?)",
            (str(time.time() - 1),),
        )
        self.connection.commit()

    def _database_context(self):
        connection = self.connection

        @contextmanager
        def database():
            yield connection

        return database

    def test_duplicate_upload_is_marked_processed_not_failed(self):
        self._insert_item()
        with (
            patch("app.services.queue_manager.get_db", self._database_context()),
            patch(
                "app.services.queue_manager.process_font_upload",
                side_effect=DuplicateFontUpload("already saved as 'example'"),
            ),
            patch("app.services.queue_manager.send_telegram_alert") as notify,
        ):
            self.assertTrue(release_next_from_queue())

        row = self.connection.execute("SELECT * FROM upload_queue WHERE id = 1").fetchone()
        self.assertEqual((row["processed"], row["failed"]), (1, 0))
        notify.assert_called_once()

    def test_hero_outage_is_deferred_not_failed(self):
        self._insert_item()
        with (
            patch("app.services.queue_manager.get_db", self._database_context()),
            patch(
                "app.services.queue_manager.process_font_upload",
                side_effect=HeroImageGenerationError("providers unavailable"),
            ),
            patch("app.services.queue_manager.send_telegram_alert") as notify,
        ):
            self.assertFalse(release_next_from_queue())

        row = self.connection.execute("SELECT * FROM upload_queue WHERE id = 1").fetchone()
        self.assertEqual((row["processed"], row["failed"], row["attempts"]), (0, 0, 1))
        self.assertGreater(float(row["received_at"]), time.time())
        notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
