import json
import unittest
from unittest.mock import Mock, patch

from app.oracle.groq_enricher import enrich_keywords


class OracleGroqEnricherTests(unittest.TestCase):
    @patch("app.oracle.groq_enricher.requests.post")
    def test_uses_20b_and_rejects_unknown_font_slugs(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": json.dumps({"items": [{
            "slug": "editorial-fonts",
            "relevant": True,
            "cluster": "editorial-fonts",
            "intent": "design guidance",
            "opportunity_type": "collection_page",
            "reason": "Repeated autocomplete evidence.",
            "recommended_action": "Create an editorial font collection.",
            "matched_font_slugs": ["wensley", "invented-font"],
            "confidence": "high",
            "translations": {"en": "editorial fonts", "es": "fuentes editoriales", "pt": "fontes editoriais"},
            "secondary_keywords": ["magazine fonts"],
        }]})}}]}
        post.return_value = response
        candidates = [{
            "slug": "editorial-fonts", "name": "editorial fonts", "sources": ["Google Autocomplete"],
            "normalized_score": 75, "trend": "new", "seen_days": 1, "evidence": [],
            "eligible_font_slugs": ["wensley"],
        }]
        context = {"fonts": [{
            "slug": "wensley", "display_name": "Wensley", "category": "sans-serif",
            "use_cases": ["Editorial Layouts"], "status": "active",
        }], "recent_titles": []}
        with patch("app.oracle.groq_enricher.config.oracle.groq_api_key", "test-key"), patch(
            "app.oracle.groq_enricher.config.oracle.groq_model", "openai/gpt-oss-20b"
        ):
            results = enrich_keywords(candidates, context)

        request = post.call_args.kwargs["json"]
        self.assertEqual(request["model"], "openai/gpt-oss-20b")
        self.assertEqual(results[0]["matched_font_slugs"], ["wensley"])
        self.assertEqual(results[0]["opportunity_type"], "article")


if __name__ == "__main__":
    unittest.main()
