import unittest
from unittest.mock import Mock, patch

from app.oracle.scrapers.autocomplete import scrape_autocomplete


class OracleAutocompleteTests(unittest.TestCase):
    @patch("app.oracle.scrapers.autocomplete.requests.get")
    def test_tracks_repeat_appearances_and_seed_evidence(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = ["seed", ["best fonts for editorial design", "unrelated result"]]
        get.return_value = response
        rows = scrape_autocomplete(["best fonts for", "fonts for editorial"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["appearances"], 2)
        self.assertEqual(rows[0]["query_seeds"], ["best fonts for", "fonts for editorial"])


if __name__ == "__main__":
    unittest.main()
