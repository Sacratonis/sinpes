import sqlite3
import unittest
from unittest.mock import patch

from app.oracle.trend_aggregator import (
    fetch_oracle_hitlist,
    format_oracle_hitlist,
    get_oracle_status,
    run_oracle,
)


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
            CREATE TABLE oracle_keyword_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, name TEXT, source TEXT,
                raw_score REAL, normalized_score REAL, metric TEXT, payload TEXT, collected_at TEXT
            );
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_oracle_normalizes_sources_and_removes_fake_templates(self):
        sources = {
            "Pinterest": lambda: [{"name": "Wedding Fonts", "score": 50, "metric": "growth_percent"}],
            "Bing": lambda: [{"name": "Free Serif Font", "score": 100, "metric": "seo_opportunity"}],
        }
        with patch("app.oracle.trend_aggregator.SOURCES", sources), patch(
            "app.oracle.trend_aggregator.enrich_keywords", side_effect=RuntimeError("temporary Groq failure")
        ):
            result = run_oracle(self.connection)

        self.assertEqual(result["keyword_count"], 2)
        hitlist = fetch_oracle_hitlist(self.connection)
        self.assertEqual(hitlist[0]["name"], "Free Serif Font")
        self.assertNotIn("keywords", hitlist[0])
        self.assertIn(hitlist[0]["opportunity_type"], {
            "article", "collection_page", "new_font_demand", "existing_page_improvement"
        })
        self.assertEqual(get_oracle_status(self.connection)["status"], "ready")

    def test_one_broken_source_does_not_break_run(self):
        def broken():
            raise RuntimeError("PINTEREST_ACCESS_TOKEN is not configured")

        with patch("app.oracle.trend_aggregator.SOURCES", {"Pinterest": broken}), patch(
            "app.oracle.trend_aggregator.enrich_keywords", return_value=[]
        ):
            result = run_oracle(self.connection)

        self.assertEqual(result["sources"]["Pinterest"]["status"], "not_configured")
        self.assertEqual(result["keyword_count"], 0)

    def test_groq_receives_candidates_and_site_context_once(self):
        with patch(
            "app.oracle.trend_aggregator.SOURCES",
            {"Bing": lambda: [{"name": "Serif Fonts", "score": 2}]},
        ), patch(
            "app.oracle.trend_aggregator.enrich_keywords", return_value=[]
        ) as enrich:
            run_oracle(self.connection)

        enrich.assert_called_once()
        candidates, context = enrich.call_args.args
        self.assertEqual(candidates[0]["name"], "Serif Fonts")
        self.assertIn("fonts", context)

    def test_history_is_preserved_across_runs(self):
        sources = {"Google Autocomplete": lambda: [{"name": "Fonts for Editorial Design", "score": 8}]}
        with patch("app.oracle.trend_aggregator.SOURCES", sources), patch(
            "app.oracle.trend_aggregator.enrich_keywords", side_effect=RuntimeError("temporary Groq failure")
        ):
            run_oracle(self.connection)
            run_oracle(self.connection)

        count = self.connection.execute("SELECT COUNT(*) FROM oracle_keyword_history").fetchone()[0]
        self.assertEqual(count, 2)
        hitlist = fetch_oracle_hitlist(self.connection)
        self.assertEqual(hitlist[0]["seen_days"], 1)

    def test_font_matching_requires_category_and_use_case(self):
        from app.oracle.trend_aggregator import _eligible_font_slugs
        context = {
            "categories": [{"slug": "sans-serif", "display_name": "Sans Serif"}],
            "fonts": [
                {"slug": "ui-sans", "category": "sans-serif", "use_cases": ["UI Design"], "status": "active"},
                {"slug": "logo-sans", "category": "sans-serif", "use_cases": ["Logo Design"], "status": "active"},
            ],
        }
        self.assertEqual(_eligible_font_slugs("sans serif font for logo", context), ["logo-sans"])

    def test_groq_rejection_is_not_reintroduced_by_fallback(self):
        sources = {"Google Autocomplete": lambda: [{"name": "vague typography query", "score": 8}]}
        with patch("app.oracle.trend_aggregator.SOURCES", sources), patch(
            "app.oracle.trend_aggregator.enrich_keywords", return_value=[]
        ):
            result = run_oracle(self.connection)
        self.assertEqual(result["keyword_count"], 0)
        self.assertEqual(fetch_oracle_hitlist(self.connection), [])

    def test_license_queries_are_excluded_without_license_records(self):
        sources = {"Google Autocomplete": lambda: [{"name": "free fonts for commercial use", "score": 10}]}
        with patch("app.oracle.trend_aggregator.SOURCES", sources), patch(
            "app.oracle.trend_aggregator.enrich_keywords", side_effect=RuntimeError("temporary Groq failure")
        ):
            result = run_oracle(self.connection)
        self.assertEqual(result["keyword_count"], 0)

    def test_hitlist_explains_action_fonts_and_evidence(self):
        text = format_oracle_hitlist([{
            "name": "fonts for editorial design",
            "opportunity_type": "article",
            "normalized_score": 78,
            "confidence": "high",
            "reason": "Repeated search evidence.",
            "recommended_action": "Write a practical guide.",
            "matched_font_slugs": ["wensley"],
            "evidence": [{"source": "Google Autocomplete", "metric": "suggestion_position", "score": 9}],
            "trend": "rising",
        }])
        self.assertIn("Action: Write a practical guide.", text)
        self.assertIn("Fonts: wensley", text)
        self.assertIn("Priority: 78/100", text)


if __name__ == "__main__":
    unittest.main()
