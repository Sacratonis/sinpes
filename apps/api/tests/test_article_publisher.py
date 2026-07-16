import json
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

from app.repositories.meta_repo import MetaRepository
from app.services.article_publisher import publish_approved_articles
from app.services.deployment_manager import snapshot_hash
from app.services.indexnow import PENDING_KEY


class FakeHookResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ArticlePublisherTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE font_registry (
                slug TEXT, display_name TEXT, category TEXT, use_cases TEXT, status TEXT,
                weights TEXT, variants TEXT, is_variable BOOLEAN DEFAULT 0
            );
            CREATE TABLE font_translations (
                slug TEXT, locale TEXT, description TEXT, seo_image_url TEXT
            );
            CREATE TABLE article_queue (
                id TEXT PRIMARY KEY, source_topic TEXT, source_keyword_data TEXT, language TEXT,
                validity TEXT, validity_reasoning TEXT, title TEXT, slug TEXT,
                meta_description TEXT, target_keyword TEXT, secondary_keywords TEXT,
                body_markdown TEXT, body_html TEXT, font_claims TEXT,
                referenced_font_slugs TEXT, image_prompt TEXT, image_url TEXT,
                image_alt_text TEXT, word_count INTEGER, content_scope TEXT, status TEXT,
                rejection_note TEXT, created_at TEXT, published_at TEXT
            );
        """)
        for slug in ("alpha", "beta"):
            self.conn.execute(
                """INSERT INTO font_registry VALUES
                   (?, ?, 'sans-serif', 'UI Design', 'active', '[400]',
                    '[{"weight":400,"style":"normal"}]', 0)""",
                (slug, slug.title()),
            )
            self.conn.execute(
                "INSERT INTO font_translations VALUES (?, 'en', '', ?)",
                (slug, f"https://r2.test/{slug}.webp"),
            )
        self._insert_article("article-one", "Readable UI type", "readable-ui-type")
        self._insert_article("article-two", "Editorial type scale", "editorial-type-scale")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _database_context(self):
        @contextmanager
        def database():
            yield self.conn
        return database

    def _body(self):
        return (
            '<p>Use <a href="/font/alpha/">Alpha</a> and compare it with '
            '<a href="/font/beta/">Beta</a>.</p>'
            '<h2 id="one">One</h2><p>Test the final layout.</p>'
            '<h2 id="two">Two</h2><p>Compare spacing carefully.</p>'
            '<h2 id="three">Three</h2><p>Review the final hierarchy.</p>'
            + '<p>Specific practical typography guidance for designers building readable layouts.</p>' * 55
        )

    def _insert_article(self, article_id, title, keyword):
        body = self._body()
        self.conn.execute(
            """INSERT INTO article_queue (
                id,source_topic,source_keyword_data,language,validity,validity_reasoning,
                title,slug,meta_description,target_keyword,secondary_keywords,
                body_markdown,body_html,font_claims,referenced_font_slugs,word_count,
                content_scope,status,created_at
            ) VALUES (?,?,'{}','en','valid','Validated',?,?,?,?, '[]',?,?,?,?,0,
                      'brief','approved',?)""",
            (
                article_id, title, title, article_id,
                f"Practical guidance for {title.lower()}.", keyword,
                body, body,
                json.dumps([
                    {"slug": "alpha", "weights": [400], "styles": ["normal"], "is_variable": False},
                    {"slug": "beta", "weights": [400], "styles": ["normal"], "is_variable": False},
                ]),
                json.dumps(["alpha", "beta"]),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    @patch("app.services.article_publisher.upload_to_r2")
    @patch("app.services.article_publisher.export_snapshot", return_value="fonts-snapshot")
    @patch("app.services.article_publisher.export_blog_snapshot", return_value="blog-snapshot")
    def test_batch_queues_two_articles_until_one_deployment_is_confirmed(
        self, _blog, _fonts, upload,
    ):
        with (
            patch("app.services.article_publisher.get_db", self._database_context()),
            patch("app.services.deployment_manager.config.SITE_URL", "https://sinpes.com"),
            patch("app.services.indexnow.config.SITE_URL", "https://sinpes.com"),
            patch("app.services.deployment_manager.config.CF_PAGES_DEPLOY_HOOK_URL", "https://hook.test"),
            patch("app.services.deployment_manager.urllib.request.urlopen", return_value=FakeHookResponse()) as hook,
        ):
            result = publish_approved_articles(limit=9, automatic=False)

        self.assertEqual(result["published_count"], 0)
        self.assertEqual(result["pending_confirmation_count"], 2)
        self.assertEqual(result["indexnow_url_count"], 8)
        self.assertEqual(hook.call_count, 1)
        self.assertEqual(upload.call_count, 1)
        statuses = dict(self.conn.execute("SELECT id,status FROM article_queue").fetchall())
        self.assertEqual(statuses, {"article-one": "publishing", "article-two": "publishing"})
        pending = json.loads(MetaRepository(self.conn).get_value(PENDING_KEY))
        self.assertIn("https://sinpes.com/blog/article-one/", pending)
        self.assertIn("https://sinpes.com/blog/article-two/", pending)
        self.assertIn("https://sinpes.com/pt/blog/", pending)

    @patch("app.services.article_publisher.upload_to_r2")
    @patch("app.services.article_publisher.export_snapshot", return_value="fonts-snapshot")
    @patch("app.services.article_publisher.export_blog_snapshot", return_value="blog-snapshot")
    def test_refused_deployment_restores_approved_status_and_previous_snapshot(
        self, _blog, _fonts, upload,
    ):
        digest = snapshot_hash("fonts-snapshot", "blog-snapshot")
        MetaRepository(self.conn).set_value("last_successful_snapshot_hash", digest)
        self.conn.commit()
        with (
            patch("app.services.article_publisher.get_db", self._database_context()),
            patch("app.services.deployment_manager.config.CF_PAGES_DEPLOY_HOOK_URL", "https://hook.test"),
        ):
            result = publish_approved_articles(limit=9, automatic=False)

        self.assertEqual(result["published_count"], 0)
        self.assertEqual(result["reason"], "snapshot is unchanged")
        statuses = dict(self.conn.execute("SELECT id,status FROM article_queue").fetchall())
        self.assertEqual(statuses, {"article-one": "approved", "article-two": "approved"})
        self.assertEqual(upload.call_count, 2)

    @patch("app.services.article_publisher.upload_to_r2")
    @patch("app.services.article_publisher.export_snapshot", return_value="fonts-snapshot")
    @patch("app.services.article_publisher.export_blog_snapshot", return_value="blog-snapshot")
    def test_failed_hook_restores_articles_and_removes_rolled_back_indexnow_urls(
        self, _blog, _fonts, upload,
    ):
        MetaRepository(self.conn).set_value(
            PENDING_KEY, json.dumps(["https://sinpes.com/blog/pre-existing/"])
        )
        self.conn.commit()
        with (
            patch("app.services.article_publisher.get_db", self._database_context()),
            patch("app.services.deployment_manager.config.SITE_URL", "https://sinpes.com"),
            patch("app.services.indexnow.config.SITE_URL", "https://sinpes.com"),
            patch("app.services.deployment_manager.config.CF_PAGES_DEPLOY_HOOK_URL", "https://hook.test"),
            patch(
                "app.services.deployment_manager.urllib.request.urlopen",
                side_effect=RuntimeError("hook unavailable"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "hook unavailable"):
                publish_approved_articles(limit=9, automatic=False)

        statuses = dict(self.conn.execute("SELECT id,status FROM article_queue").fetchall())
        self.assertEqual(statuses, {"article-one": "approved", "article-two": "approved"})
        self.assertEqual(
            json.loads(MetaRepository(self.conn).get_value(PENDING_KEY)),
            ["https://sinpes.com/blog/pre-existing/"],
        )
        self.assertEqual(upload.call_count, 2)

    @patch("app.services.article_publisher.upload_to_r2")
    @patch(
        "app.services.article_publisher.export_blog_snapshot",
        side_effect=RuntimeError("snapshot export unavailable"),
    )
    def test_export_failure_restores_queues_without_erasing_concurrent_article_lock(
        self, _blog, upload,
    ):
        MetaRepository(self.conn).set_value(
            PENDING_KEY, json.dumps(["https://sinpes.com/blog/pre-existing/"])
        )
        # Simulate another publisher owning an in-flight lock while this
        # batch is preparing its snapshot.
        from app.services.deployment_manager import PENDING_ARTICLES_KEY
        MetaRepository(self.conn).set_value(PENDING_ARTICLES_KEY, json.dumps(["other-batch"]))
        self.conn.commit()
        with (
            patch("app.services.article_publisher.get_db", self._database_context()),
            patch("app.services.deployment_manager.config.CF_PAGES_DEPLOY_HOOK_URL", "https://hook.test"),
        ):
            with self.assertRaisesRegex(RuntimeError, "snapshot export unavailable"):
                publish_approved_articles(limit=1)

        statuses = dict(self.conn.execute("SELECT id,status FROM article_queue").fetchall())
        self.assertEqual(statuses, {"article-one": "approved", "article-two": "approved"})
        self.assertEqual(
            json.loads(MetaRepository(self.conn).get_value(PENDING_KEY)),
            ["https://sinpes.com/blog/pre-existing/"],
        )
        self.assertEqual(
            json.loads(MetaRepository(self.conn).get_value(PENDING_ARTICLES_KEY)),
            ["other-batch"],
        )
        upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
