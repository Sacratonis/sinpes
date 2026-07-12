import sqlite3
import unittest
from unittest.mock import patch

from app.oracle.trend_aggregator import fetch_oracle_hitlist, get_oracle_status, run_oracle


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE font_registry (slug TEXT PRIMARY KEY);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE oracle_keywords (
                slug TEXT PRIMARY KEY, name TEXT, source TEXT, region TEXT,
                score REAL, metric TEXT, rank INTEGER, payload TEXT, collected_at TEXT
            );
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_oracle_ranks_and_persists_keywords(self):
        sources = {
            "Pinterest": lambda: [{"name": "Wedding Fonts", "source": "Pinterest", "score": 50}],
            "Bing": lambda: [{"name": "Free Serif Font", "source": "Bing", "score": 100}],
            "Yandex": lambda: [],
        }
        with patch("app.oracle.trend_aggregator.SOURCES", sources), patch(
            "app.oracle.trend_aggregator.enrich_keywords", side_effect=lambda rows: rows
        ):
            result = run_oracle(self.connection)

        self.assertEqual(result["keyword_count"], 2)
        hitlist = fetch_oracle_hitlist(self.connection)
        self.assertEqual(hitlist[0]["name"], "Free Serif Font")
        self.assertIn("free Free Serif Font font alternative", hitlist[0]["keywords"]["en"])
        self.assertEqual(get_oracle_status(self.connection)["status"], "ready")

    def test_one_broken_source_does_not_break_run(self):
        def broken():
            raise RuntimeError("PINTEREST_ACCESS_TOKEN is not configured")

        with patch("app.oracle.trend_aggregator.SOURCES", {"Pinterest": broken}), patch(
            "app.oracle.trend_aggregator.enrich_keywords", side_effect=lambda rows: rows
        ):
            result = run_oracle(self.connection)

        self.assertEqual(result["sources"]["Pinterest"]["status"], "not_configured")
        self.assertEqual(result["keyword_count"], 0)


if __name__ == "__main__":
    unittest.main()
