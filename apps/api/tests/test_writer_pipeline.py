import unittest
import sqlite3

from app.services.writer_pipeline import InsufficientDepth, WriterValidationFailure, _find_duplicate, _normalize_h2_ids, _validate_article, queue_manual_article


class WriterPipelineTests(unittest.TestCase):
    def setUp(self):
        self.fonts = [
            {"slug": "alpha", "display_name": "Alpha", "weights": "[400]", "variants": '[{"weight":400,"style":"normal"}]'},
            {"slug": "beta", "display_name": "Beta", "weights": "[400,700]", "variants": '[{"weight":400,"style":"normal"},{"weight":700,"style":"normal"}]'},
        ]

    def test_invalid_topic_exits_without_article(self):
        result = _validate_article(
            {"validity": "invalid", "reasoning": "No useful typography connection."},
            self.fonts,
            "en",
        )
        self.assertEqual(result["validity"], "invalid")

    def test_validation_failure_preserves_reason_and_draft(self):
        draft = {"validity": "valid", "title": "Failed draft"}
        failure = WriterValidationFailure("Unsupported claim", draft)
        self.assertEqual(failure.reason, "Unsupported claim")
        self.assertEqual(failure.draft, draft)

    def test_valid_article_requires_real_internal_links(self):
        body = (
            '<h2 id="practical-pairing">Practical pairing</h2>'
            '<p>Apply <a href="/font/alpha/">Alpha</a>, then compare it with <a href="/font/beta/">Beta</a>.</p>'
            '<h2 id="type-scale">Type scale</h2><p>Use a controlled type scale.</p>'
            '<h2 id="spacing-test">Spacing test</h2><p>Test spacing in context.</p>'
            + '<p>Useful typography guidance for designers and clear practical application.</p>' * 80
        )
        result = _validate_article(
            {
                "validity": "valid",
                "content_scope": "guide",
                "reasoning": "Useful topic.",
                "title": "A Practical Font Pairing Guide",
                "slug": "practical-font-pairing-guide",
                "meta_description": "Learn a practical font pairing method using free SINPES typefaces.",
                "target_keyword": "font pairing guide",
                "secondary_keywords": ["free font pairing"],
                "body_html": body,
                "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400, 700], "styles": ["normal"], "is_variable": False},
                ],
            },
            self.fonts,
            "en",
        )
        self.assertEqual(result["validity"], "valid")
        self.assertGreaterEqual(result["word_count"], 650)

    def test_meta_description_limit(self):
        with self.assertRaisesRegex(ValueError, "160"):
            _validate_article(
                {
                    "validity": "valid", "content_scope": "brief", "title": "Title", "slug": "title",
                    "meta_description": "x" * 161, "target_keyword": "font", "secondary_keywords": ["type"],
                    "body_html": "<p>font</p>", "referenced_font_slugs": ["alpha", "beta"],
                    "font_claims": [{"slug": "alpha"}, {"slug": "beta"}],
                }, self.fonts, "en",
            )

    def test_secondary_keywords_must_be_an_array(self):
        body = (
            '<p><a href="/font/alpha/">Alpha</a> and <a href="/font/beta/">Beta</a>.</p>'
            '<h2 id="one">One</h2><p>Test typography.</p>'
            '<h2 id="two">Two</h2><p>Compare spacing.</p>'
            '<h2 id="three">Three</h2><p>Review hierarchy.</p>'
            + '<p>Useful practical typography guidance for readable editorial layouts.</p>' * 60
        )
        with self.assertRaisesRegex(ValueError, "secondary_keywords"):
            _validate_article({
                "validity": "valid", "content_scope": "brief", "title": "Readable Type",
                "slug": "readable-type", "meta_description": "Practical typography guidance.",
                "target_keyword": "readable typography", "secondary_keywords": "spacing, hierarchy",
                "body_html": body, "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400, 700], "styles": ["normal"], "is_variable": False},
                ],
            }, self.fonts, "en")

    def test_brief_rejects_body_below_450_words(self):
        body = (
            '<p><a href="/font/alpha/">Alpha</a> and <a href="/font/beta/">Beta</a>.</p>'
            '<h2 id="one">One</h2><p>Test the type in its final layout.</p>'
            '<h2 id="two">Two</h2><p>Compare spacing and hierarchy carefully.</p>'
            '<h2 id="three">Three</h2><p>Review the result with real content.</p>'
            + '<p>Useful practical typography guidance for designers working on readable editorial layouts.</p>' * 30
        )
        with self.assertRaises(InsufficientDepth):
            _validate_article({
                "validity": "valid", "content_scope": "brief", "title": "Readable Editorial Type",
                "slug": "readable-editorial-type", "meta_description": "Practical editorial typography guidance.",
                "target_keyword": "editorial typography", "secondary_keywords": ["layout"], "body_html": body,
                "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400, 700], "styles": ["normal"], "is_variable": False},
                ],
            }, self.fonts, "en")

    def test_rejects_unsupported_weight_claim(self):
        body = '<p><a href="/font/alpha/">Alpha</a> and <a href="/font/beta/">Beta</a>.</p>'
        body += '<h2 id="one">One</h2><p>Test.</p><h2 id="two">Two</h2><p>Test.</p><h2 id="three">Three</h2><p>Test.</p>'
        body += '<p>Specific practical typography advice for an editorial layout.</p>' * 90
        with self.assertRaisesRegex(ValueError, "Unsupported weight"):
            _validate_article({
                "validity": "valid", "content_scope": "guide", "title": "Practical Editorial Type", "slug": "practical-editorial-type",
                "meta_description": "A practical editorial typography guide.", "target_keyword": "editorial typography", "secondary_keywords": ["layout"],
                "body_html": body, "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [900], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400], "styles": ["normal"], "is_variable": False},
                ],
            }, self.fonts, "en")

    def test_rejects_unsupported_font_anatomy_claim(self):
        body = (
            '<p><a href="/font/alpha/">Alpha</a> has a moderate x-height, while '
            '<a href="/font/beta/">Beta</a> has clean proportions, an average character width of 0.5em, and reliable small caps.</p>'
            '<h2 id="one">One</h2><p>Test typography in context.</p>'
            '<h2 id="two">Two</h2><p>Compare spacing carefully.</p>'
            '<h2 id="three">Three</h2><p>Review the final hierarchy.</p>'
            + '<p>Useful practical typography guidance for readable editorial design systems.</p>' * 50
        )
        with self.assertRaisesRegex(ValueError, "font-anatomy"):
            _validate_article({
                "validity": "valid", "content_scope": "brief", "title": "Readable Type",
                "slug": "readable-type", "meta_description": "Practical typography guidance.",
                "target_keyword": "readable typography", "secondary_keywords": ["layout"], "body_html": body,
                "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400, 700], "styles": ["normal"], "is_variable": False},
                ],
            }, self.fonts, "en")

    def test_rejects_bold_claim_for_single_weight_font(self):
        body = (
            '<p>Use <a href="/font/alpha/">Alpha</a> in bold and compare it with '
            '<a href="/font/beta/">Beta</a>.</p>'
            '<h2 id="one">One</h2><p>Test typography.</p>'
            '<h2 id="two">Two</h2><p>Compare spacing.</p>'
            '<h2 id="three">Three</h2><p>Review hierarchy.</p>'
            + '<p>Useful practical typography guidance for readable editorial layouts.</p>' * 60
        )
        with self.assertRaisesRegex(ValueError, "unsupported bold"):
            _validate_article({
                "validity": "valid", "content_scope": "brief", "title": "Readable Type",
                "slug": "readable-type", "meta_description": "Practical typography guidance.",
                "target_keyword": "readable typography", "secondary_keywords": ["layout"],
                "body_html": body, "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400, 700], "styles": ["normal"], "is_variable": False},
                ],
            }, self.fonts, "en")

    def test_rejects_non_action_font_narrative(self):
        body = (
            '<p><a href="/font/alpha/">Alpha</a> feels airy beside '
            '<a href="/font/beta/">Beta</a>.</p>'
            '<h2 id="one">One</h2><p>Test typography.</p>'
            '<h2 id="two">Two</h2><p>Compare spacing.</p>'
            '<h2 id="three">Three</h2><p>Review hierarchy.</p>'
            + '<p>Useful practical typography guidance for readable editorial layouts.</p>' * 60
        )
        with self.assertRaisesRegex(ValueError, "neutral action"):
            _validate_article({
                "validity": "valid", "content_scope": "brief", "title": "Readable Type",
                "slug": "readable-type", "meta_description": "Practical typography guidance.",
                "target_keyword": "readable typography", "secondary_keywords": ["layout"],
                "body_html": body, "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400, 700], "styles": ["normal"], "is_variable": False},
                ],
            }, self.fonts, "en")

    def test_duplicate_detection_ignores_marketing_framing(self):
        duplicate = _find_duplicate(
            "The Secret to Top-Tier UI: Mastering Typography Essentials",
            ["UI Typography Essentials"],
        )
        self.assertEqual(duplicate, "UI Typography Essentials")

    def test_related_topics_are_not_false_duplicates(self):
        duplicate = _find_duplicate(
            "UI Typography Essentials",
            ["Typography Directions for Editorial Design"],
        )
        self.assertIsNone(duplicate)

    def test_rejects_malformed_heading_html(self):
        body = '<p><a href="/font/alpha/">Alpha</a> and <a href="/font/beta/">Beta</a>.</p>'
        body += '<h2 id="broken-heading">Broken heading</p>'
        body += '<p>Specific practical typography guidance for interface design.</p>' * 110
        with self.assertRaisesRegex(ValueError, "Malformed HTML"):
            _validate_article({
                "validity": "valid", "content_scope": "guide", "title": "Practical UI Type", "slug": "practical-ui-type",
                "meta_description": "Practical UI typography guidance.", "target_keyword": "UI typography", "secondary_keywords": ["interface type"],
                "body_html": body, "referenced_font_slugs": ["alpha", "beta"],
                "font_claims": [
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400], "styles": ["normal"], "is_variable": False},
                ],
            }, self.fonts, "en")

    def test_manual_article_waits_for_curated_image(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE font_registry (slug TEXT, status TEXT, weights TEXT, variants TEXT, is_variable BOOLEAN DEFAULT 0);
            CREATE TABLE font_translations (slug TEXT, locale TEXT, seo_image_url TEXT);
            CREATE TABLE article_queue (
                id TEXT, source_topic TEXT, source_keyword_data TEXT, language TEXT, validity TEXT,
                validity_reasoning TEXT, title TEXT, slug TEXT, meta_description TEXT,
                target_keyword TEXT, secondary_keywords TEXT, body_markdown TEXT, body_html TEXT,
                referenced_font_slugs TEXT, font_claims TEXT, image_url TEXT, image_alt_text TEXT,
                word_count INTEGER, status TEXT, created_at TEXT, content_scope TEXT
            );
        """)
        for slug in ("alpha", "beta"):
            conn.execute("INSERT INTO font_registry VALUES (?, 'active', '[400]', '[{\"weight\":400,\"style\":\"normal\"}]', 0)", (slug,))
            conn.execute("INSERT INTO font_translations VALUES (?, 'en', 'hero.webp')", (slug,))
        body = '<p><a href="/font/alpha/">Alpha</a> and <a href="/font/beta/">Beta</a>.</p>'
        body += '<h2 id="practical-test">Practical test</h2>' + '<p>Specific typography guidance for interface testing and implementation.</p>' * 100
        article_id = queue_manual_article(conn, "Manual UI Type", "A manual UI typography article.", ["alpha", "beta"], body)
        row = conn.execute("SELECT status,image_url FROM article_queue WHERE id=?", (article_id,)).fetchone()
        self.assertEqual(row["status"], "awaiting_image")
        self.assertIsNone(row["image_url"])
        conn.close()

    def test_h2_ids_are_normalized_and_deduplicated(self):
        body = '<h2 id="Bad ID">Type Scale</h2><h2>Type Scale</h2>'
        normalized = _normalize_h2_ids(body)
        self.assertIn('id="type-scale"', normalized)
        self.assertIn('id="type-scale-2"', normalized)


if __name__ == "__main__":
    unittest.main()
