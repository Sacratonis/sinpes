import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

from app.repositories.meta_repo import MetaRepository
from app.services.indexnow import (
    PENDING_KEY,
    localized_urls,
    queue_indexnow_urls,
    submit_pending_indexnow,
)


class IndexNowTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    def tearDown(self):
        self.connection.close()

    def test_localized_urls_cover_all_public_languages(self):
        with patch("app.services.indexnow.config.SITE_URL", "https://sinpes.com"):
            self.assertEqual(
                localized_urls("/font/inter/"),
                [
                    "https://sinpes.com/font/inter/",
                    "https://sinpes.com/es/font/inter/",
                    "https://sinpes.com/pt/font/inter/",
                ],
            )

    def test_queue_keeps_only_canonical_same_host_urls(self):
        with patch("app.services.indexnow.config.SITE_URL", "https://sinpes.com"):
            queued = queue_indexnow_urls(
                self.connection,
                [
                    "https://sinpes.com/font/inter/",
                    "https://sinpes.com/font/inter/",
                    "https://example.com/copied-page/",
                    "http://sinpes.com/insecure/",
                ],
            )
        self.assertEqual(queued, ["https://sinpes.com/font/inter/"])

    def test_successful_submission_clears_pending_urls(self):
        MetaRepository(self.connection).set_value(
            PENDING_KEY,
            json.dumps(["https://sinpes.com/font/inter/"]),
        )
        response = Mock(status_code=202)
        with (
            patch("app.services.indexnow.config.SITE_URL", "https://sinpes.com"),
            patch("app.services.indexnow.config.INDEXNOW_ENABLED", True),
            patch("app.services.indexnow.config.INDEXNOW_KEY", "test-key"),
            patch("app.services.indexnow.requests.post", return_value=response) as post,
        ):
            result = submit_pending_indexnow(self.connection)

        self.assertEqual(result, {"status": "submitted", "count": 1})
        self.assertEqual(
            json.loads(MetaRepository(self.connection).get_value(PENDING_KEY)),
            [],
        )
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
