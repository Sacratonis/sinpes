import json
import sqlite3
import unittest
from unittest.mock import patch

from app.seo.auditor import audit_article_font_links, audit_candidate, audit_font_images
from app.services.content_integrity import (
    ContentIntegrityError,
    analyze_keyword_conflicts,
    enforce_keyword_integrity,
    font_capabilities,
    keyword_overlap,
    normalize_keyword,
    validate_evidence_bound_text,
)
from app.services.writer_pipeline import publication_integrity_report
from app.services.seo_bot import is_authorized_private_chat, start_bot


class ContentIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE article_queue (
                id TEXT PRIMARY KEY, source_topic TEXT, source_keyword_data TEXT,
                language TEXT, validity TEXT, validity_reasoning TEXT, title TEXT,
                slug TEXT, meta_description TEXT, target_keyword TEXT,
                secondary_keywords TEXT, body_markdown TEXT, body_html TEXT,
                font_claims TEXT, referenced_font_slugs TEXT, image_prompt TEXT,
                image_url TEXT, image_alt_text TEXT, word_count INTEGER,
                content_scope TEXT, status TEXT, rejection_note TEXT,
                created_at TEXT, published_at TEXT
            );
            CREATE TABLE font_registry (
                slug TEXT PRIMARY KEY, display_name TEXT, category TEXT, use_cases TEXT,
                status TEXT, weights TEXT, variants TEXT, is_variable BOOLEAN DEFAULT 0
            );
            CREATE TABLE font_translations (
                slug TEXT, locale TEXT, description TEXT, seo_image_url TEXT
            );
        """)
        for slug in ("writer-alpha", "writer-beta"):
            self.conn.execute(
                """INSERT INTO font_registry VALUES
                   (?, ?, 'sans-serif', 'UI Design', 'active', '[400]',
                    '[{"weight":400,"style":"normal"}]', 0)""",
                (slug, slug.replace("-", " ").title()),
            )
            for locale in ("en", "es", "pt"):
                self.conn.execute(
                    "INSERT INTO font_translations VALUES (?, ?, '', ?)",
                    (slug, locale, f"https://cdn.test/{slug}-{locale}.webp"),
                )

    def tearDown(self):
        self.conn.close()

    def insert_article(
        self, article_id: str, keyword: str, *, title: str = "Existing article",
        status: str = "published", language: str = "en", intent_key: str | None = None,
    ):
        body = (
            '<p>Use <a href="/font/writer-alpha/">Writer Alpha</a> and compare it with '
            '<a href="/font/writer-beta/">Writer Beta</a>.</p>'
            '<h2 id="one">One</h2><p>Test the final layout.</p>'
            '<h2 id="two">Two</h2><p>Compare spacing carefully.</p>'
            '<h2 id="three">Three</h2><p>Review the hierarchy.</p>'
            + '<p>Specific practical typography guidance for readable interface layouts.</p>' * 60
        )
        self.conn.execute(
            """INSERT INTO article_queue (
                id,source_topic,source_keyword_data,language,validity,validity_reasoning,
                title,slug,meta_description,target_keyword,secondary_keywords,
                body_markdown,body_html,font_claims,referenced_font_slugs,word_count,
                content_scope,status,created_at
            ) VALUES (?,?,?,?, 'valid','Validated',?,?,?,?,'[]',?,?,?,?,0,'brief',?,?)""",
            (
                article_id, title,
                json.dumps({"intent_key": intent_key}) if intent_key else "{}",
                language, title, article_id, f"Practical guidance for {title.lower()}.",
                keyword, body, body,
                json.dumps([
                    {"slug": "writer-alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "writer-beta", "weights": [400], "styles": ["normal"], "is_variable": False},
                ]),
                json.dumps(["writer-alpha", "writer-beta"]),
                status, "2026-07-15T00:00:00+00:00",
            ),
        )
        self.conn.commit()

    def test_normalization_is_deterministic_but_does_not_rewrite_intent(self):
        self.assertEqual(normalize_keyword("  UI—Typography!  "), "ui typography")
        self.assertNotEqual(normalize_keyword("font pairing"), normalize_keyword("pairing fonts"))

    def test_exact_normalized_keyword_is_a_hard_block(self):
        self.insert_article("existing", "UI Typography")
        with self.assertRaisesRegex(ContentIntegrityError, "exact_target_keyword"):
            enforce_keyword_integrity(self.conn, "ui—typography!", "en")

    def test_exact_intent_key_is_a_hard_block(self):
        self.insert_article("existing", "interface type", intent_key="ui-body-readability")
        report = analyze_keyword_conflicts(
            self.conn, "screen typography", "en", intent_key="UI Body Readability",
        )
        self.assertTrue(report["blocked"])
        self.assertEqual(report["hard_conflicts"][0]["reason"], "exact_intent_key")

    def test_fuzzy_overlap_is_advisory_and_never_blocks(self):
        self.insert_article("existing", "editorial hierarchy spacing")
        report = analyze_keyword_conflicts(
            self.conn, "editorial hierarchy spacing workflow", "en",
        )
        self.assertFalse(report["blocked"])
        self.assertEqual(len(report["advisories"]), 1)
        self.assertGreaterEqual(report["advisories"][0]["score"], 0.70)

    def test_generic_words_do_not_create_fuzzy_conflicts(self):
        self.assertEqual(keyword_overlap("free typography font guide", "best font design guide"), 0.0)

    def test_writer_publication_path_uses_shared_hard_block(self):
        self.insert_article("published", "UI typography", title="Published UI Type")
        self.insert_article("candidate", "ui—typography!", title="Candidate", status="pending_review")
        with self.assertRaisesRegex(ContentIntegrityError, "Published UI Type"):
            publication_integrity_report(self.conn, "candidate")

    def test_seo_audit_path_uses_same_shared_hard_block_read_only(self):
        self.insert_article("published", "UI typography", title="Published UI Type")
        before = self.conn.total_changes
        report = audit_candidate(self.conn, "ui—typography!", "en")
        self.assertTrue(report["blocked"])
        self.assertEqual(report["hard_conflicts"][0]["article_id"], "published")
        self.assertEqual(self.conn.total_changes, before)

    def test_real_writer_and_seo_entry_points_are_wired_to_shared_functions(self):
        self.insert_article("candidate", "readable interface type", status="pending_review")
        with patch("app.services.writer_pipeline.enforce_keyword_integrity", return_value={"blocked": False}) as writer_check:
            publication_integrity_report(self.conn, "candidate")
            writer_check.assert_called_once()
        with patch("app.seo.auditor.analyze_keyword_conflicts", return_value={"blocked": False}) as seo_check:
            audit_candidate(self.conn, "readable interface type")
            seo_check.assert_called_once()

    def test_seo_bot_authorization_requires_owner_private_chat(self):
        self.assertTrue(is_authorized_private_chat(123, 123, True, 123))
        self.assertFalse(is_authorized_private_chat(999, 999, True, 123))
        self.assertFalse(is_authorized_private_chat(123, -100123, False, 123))

    def test_seo_bot_cannot_start_while_disabled(self):
        with patch("app.services.seo_bot.config.seo.enabled", False):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                start_bot()

    def test_variable_capability_reads_verified_registry_field(self):
        capabilities = font_capabilities({
            "weights": "[100,900]",
            "variants": '[{"weight":400,"style":"normal"}]',
            "is_variable": True,
        })
        self.assertTrue(capabilities["is_variable"])
        self.assertFalse(font_capabilities({"weights": "[400]", "variants": "[]", "is_variable": "0"})["is_variable"])

    def test_anatomy_scan_does_not_cross_paragraph_boundaries(self):
        body = (
            "<p>An elegant, modern layout can still use warm letterforms.</p>"
            '<h2 id="test-font">Test the font</h2>'
            '<p>Use <a href="/font/wensley/">Wensley</a> in the specimen.</p>'
        )
        validate_evidence_bound_text("A practical typography test", body)

    def test_anatomy_scan_still_rejects_same_paragraph_claim(self):
        body = '<p>Use <a href="/font/wensley/">Wensley</a> for its elegant x-height.</p>'
        with self.assertRaisesRegex(ContentIntegrityError, "font-anatomy"):
            validate_evidence_bound_text("A practical typography test", body)

    def test_image_audit_reports_cross_family_duplicates_and_missing_locales(self):
        self.conn.executemany(
            "INSERT INTO font_registry(slug,status) VALUES(?, 'active')",
            [("alpha",), ("beta",)],
        )
        self.conn.executemany(
            "INSERT INTO font_translations(slug,locale,seo_image_url) VALUES(?,?,?)",
            [
                ("alpha", "en", "https://cdn.test/shared.webp"),
                ("alpha", "es", "https://cdn.test/alpha-es.webp"),
                ("alpha", "pt", "https://cdn.test/alpha-pt.webp"),
                ("beta", "en", "https://cdn.test/shared.webp"),
            ],
        )
        report = audit_font_images(self.conn)
        self.assertEqual(len(report["cross_family_duplicates"]), 1)
        self.assertEqual(len(report["missing"]), 2)

    def test_link_audit_reports_only_non_public_font_targets(self):
        self.conn.execute("INSERT INTO font_registry(slug,status) VALUES('alpha', 'active')")
        self.conn.execute(
            "INSERT INTO article_queue(id,title,slug,target_keyword,language,status,source_keyword_data,created_at,body_html) "
            "VALUES('links','Links','links','links','en','published','{}','2026-07-15',?)",
            ('<a href="/font/alpha/">Alpha</a><a href="/font/missing/">Missing</a>',),
        )
        report = audit_article_font_links(self.conn)
        self.assertEqual(report["broken"][0]["missing_font_slugs"], ["missing"])


if __name__ == "__main__":
    unittest.main()
