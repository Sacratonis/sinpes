import unittest
from unittest.mock import Mock, patch

from app.oracle.gemini_enricher import enrich_keywords
from app.core.config import config


class GeminiEnricherTests(unittest.TestCase):
    @patch("app.oracle.gemini_enricher.requests.post")
    def test_enrichment_keeps_real_metrics_unchanged(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": """[
                {"slug":"wedding-fonts","relevant":true,"intent":"inspiration",
                 "cluster":"wedding typography","content_type":"use_case_page",
                 "reason":"Strong design intent","translations":{"en":"wedding fonts",
                 "es":"fuentes para bodas","pt":"fontes para casamento"},
                 "secondary_keywords":["wedding invitation fonts"]}
            ]"""}]}}]
        }
        post.return_value = response
        source = [{
            "slug": "wedding-fonts", "name": "Wedding Fonts", "source": "Pinterest",
            "score": 42.5, "metric": "growth_percent",
        }]

        with patch.object(config.oracle, "gemini_api_key", "test-key"), patch.object(
            config.oracle, "gemini_enrichment", True
        ):
            result = enrich_keywords(source)

        self.assertEqual(result[0]["score"], 42.5)
        self.assertEqual(result[0]["metric"], "growth_percent")
        self.assertEqual(result[0]["seo"]["content_type"], "use_case_page")


if __name__ == "__main__":
    unittest.main()
