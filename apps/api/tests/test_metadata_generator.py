import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

from app.ingestion.metadata_generator import _build_factual_descriptions, _build_factual_keywords, _validate_generated_metadata, generate_ingestion_payload


FACTS = {
    "display_name": "Example Sans",
    "slug": "example-sans",
    "weights": [400, 700],
    "styles": ["normal", "italic"],
    "is_variable": False,
    "variable_axes": {},
    "mapped_codepoint_count": 420,
    "unicode_coverage": ["Basic Latin", "Latin Extended"],
    "panose": None,
}


def generated_metadata():
    return {
        "category": "sans-serif",
        "translations": {
            "en": "Use Example Sans when testing interface hierarchy, editorial pages, and responsive layouts. " * 4,
            "es": "Usa Example Sans para probar jerarquías de interfaz, páginas editoriales y diseños adaptables. " * 4,
            "pt": "Use Example Sans para testar hierarquias de interface, páginas editoriais e layouts responsivos. " * 4,
        },
        "use_cases": ["UI Design", "Editorial Design", "Web Design"],
        "keywords": {
            "en": "Example Sans font, interface typography, editorial font",
            "es": "fuente Example Sans, tipografía de interfaz, fuente editorial",
            "pt": "fonte Example Sans, tipografia de interface, fonte editorial",
        },
    }


class MetadataGeneratorTests(unittest.TestCase):
    def test_factual_keywords_do_not_require_ai_copy(self):
        keywords = _build_factual_keywords(FACTS, "sans-serif", ["UI Design", "Web Design"])
        self.assertEqual(set(keywords), {"en", "es", "pt"})
        self.assertIn("Example Sans font", keywords["en"])
        self.assertNotIn("modern", json.dumps(keywords).lower())

    def test_factual_descriptions_use_only_extracted_values(self):
        descriptions = _build_factual_descriptions(FACTS, ["UI Design", "Editorial Design"])
        self.assertEqual(set(descriptions), {"en", "es", "pt"})
        self.assertIn("420", descriptions["en"])
        self.assertIn("400, 700", descriptions["en"])
        self.assertIn("diseño de interfaces", descriptions["es"])
        self.assertIn("design de interfaces", descriptions["pt"])
        self.assertNotIn("none", descriptions["es"])
        self.assertNotIn("none", descriptions["pt"])
        self.assertNotIn("license", json.dumps(descriptions).lower())

    def test_generated_metadata_builds_shared_payload_without_license_data(self):
        payload = _validate_generated_metadata(generated_metadata(), FACTS, ["/tmp/example.ttf"])
        self.assertEqual(payload.slug, "example-sans")
        self.assertEqual(set(payload.translations), {"en", "es", "pt"})
        self.assertEqual(payload.font_files, ["/tmp/example.ttf"])
        self.assertNotIn("license", payload.model_dump())

    def test_license_data_is_rejected(self):
        metadata = generated_metadata()
        metadata["license"] = "Open source"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            _validate_generated_metadata(metadata, FACTS, ["/tmp/example.ttf"])

    def test_unsupported_design_characteristic_is_rejected(self):
        metadata = generated_metadata()
        metadata["translations"]["en"] = "A clean and modern font for interface projects. " * 8
        with self.assertRaisesRegex(ValueError, "design-characteristic"):
            _validate_generated_metadata(metadata, FACTS, ["/tmp/example.ttf"])

    def test_verified_font_name_is_not_treated_as_a_design_claim(self):
        facts = {**FACTS, "display_name": "NeutralFace", "slug": "neutralface"}
        metadata = generated_metadata()
        serialized = json.dumps(metadata).replace("Example Sans", "NeutralFace")
        payload = _validate_generated_metadata(json.loads(serialized), facts, ["/tmp/neutralface.ttf"])
        self.assertEqual(payload.slug, "neutralface")

    def test_neutral_claim_remains_blocked_for_neutralface(self):
        facts = {**FACTS, "display_name": "NeutralFace", "slug": "neutralface"}
        metadata = generated_metadata()
        metadata["translations"]["en"] = "NeutralFace has a neutral appearance for interface projects. " * 6
        with self.assertRaisesRegex(ValueError, "design-characteristic"):
            _validate_generated_metadata(metadata, facts, ["/tmp/neutralface.ttf"])

    def test_long_use_case_sentences_are_rejected(self):
        metadata = generated_metadata()
        metadata["use_cases"] = ["Use this font for interface buttons", "Editorial Design", "Web Design"]
        with self.assertRaisesRegex(ValueError, "short label"):
            _validate_generated_metadata(metadata, FACTS, ["/tmp/example.ttf"])

    def test_mapped_characters_cannot_be_called_glyphs(self):
        metadata = generated_metadata()
        metadata["keywords"]["en"] = "Example Sans, 420 glyphs"
        with self.assertRaisesRegex(ValueError, "design-characteristic"):
            _validate_generated_metadata(metadata, FACTS, ["/tmp/example.ttf"])

    @patch("app.ingestion.metadata_generator.extract_font_facts", return_value=FACTS)
    @patch("app.ingestion.metadata_generator.requests.post")
    def test_font_only_generation_returns_valid_contract(self, post, _extract):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "category": "sans-serif",
                "use_cases": ["UI Design", "Editorial Design", "Web Design"],
                "keywords": generated_metadata()["keywords"],
            })}}]
        }
        post.return_value = response
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE categories (slug TEXT, display_name TEXT)")
        connection.execute("INSERT INTO categories VALUES ('sans-serif', 'Sans Serif')")
        with patch("app.ingestion.metadata_generator.config.oracle.groq_api_key", "test-key"):
            payload, facts = generate_ingestion_payload(connection, ["/tmp/example.ttf"])
        connection.close()
        self.assertEqual(payload.category, "sans-serif")
        self.assertEqual(facts["display_name"], "Example Sans")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "openai/gpt-oss-20b")
        self.assertEqual(post.call_args.kwargs["json"]["max_completion_tokens"], 800)


if __name__ == "__main__":
    unittest.main()
