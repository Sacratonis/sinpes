import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.repositories.font_repo import FontRepository
from app.repositories.meta_repo import MetaRepository
from app.services.deployment_manager import (
    confirm_deployment_success,
    get_deployment_status,
    snapshot_hash,
    trigger_deployment,
)


class FakeHookResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE font_registry (slug TEXT PRIMARY KEY, status TEXT NOT NULL);
            CREATE TABLE categories (slug TEXT PRIMARY KEY);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )

    def tearDown(self):
        self.connection.close()

    def test_drip_batch_activates_only_requested_queued_fonts(self):
        self.connection.executemany(
            "INSERT INTO font_registry (slug, status) VALUES (?, ?)",
            [("one", "queued"), ("two", "queued"), ("three", "vault")],
        )
        self.connection.execute("ALTER TABLE font_registry ADD COLUMN category TEXT")
        self.connection.execute("UPDATE font_registry SET category = 'known'")
        self.connection.execute("INSERT INTO categories(slug) VALUES('known')")

        FontRepository(self.connection).activate_queued_fonts(1)

        statuses = dict(
            self.connection.execute("SELECT slug, status FROM font_registry").fetchall()
        )
        self.assertEqual(statuses["one"], "active")
        self.assertEqual(statuses["two"], "queued")
        self.assertEqual(statuses["three"], "vault")

    def test_publish_does_not_activate_font_with_pending_category(self):
        self.connection.execute("ALTER TABLE font_registry ADD COLUMN category TEXT")
        self.connection.execute(
            "INSERT INTO font_registry(slug, status, category) VALUES('waiting', 'queued', 'new-category')"
        )

        FontRepository(self.connection).activate_queued_fonts(48)

        status = self.connection.execute(
            "SELECT status FROM font_registry WHERE slug = 'waiting'"
        ).fetchone()[0]
        self.assertEqual(status, "queued")

    def test_build_lock_can_be_cleared(self):
        repository = MetaRepository(self.connection)
        repository.set_value("build_in_progress", "true")
        repository.set_value("build_in_progress", "false")

        self.assertEqual(repository.get_value("build_in_progress"), "false")

    def trigger(self, **kwargs):
        defaults = {
            "artifact_hash": snapshot_hash("fonts", "blog"),
            "source": "test",
            "now": datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        }
        defaults.update(kwargs)
        with (
            patch("app.services.deployment_manager.config.CF_PAGES_DEPLOY_HOOK_URL", "https://example.test/hook"),
            patch("app.services.deployment_manager.config.DEPLOY_MONTHLY_LIMIT", 80),
            patch("app.services.deployment_manager.config.DEPLOY_MANUAL_COOLDOWN_SECONDS", 900),
            patch("app.services.deployment_manager.config.DEPLOY_STALE_LOCK_SECONDS", 21600),
            patch("app.services.deployment_manager.urllib.request.urlopen", return_value=FakeHookResponse()),
        ):
            return trigger_deployment(self.connection, **defaults)

    def test_unchanged_snapshot_does_not_deploy(self):
        digest = snapshot_hash("fonts", "blog")
        MetaRepository(self.connection).set_value("last_successful_snapshot_hash", digest)

        decision = self.trigger(artifact_hash=digest)

        self.assertFalse(decision.triggered)
        self.assertEqual(decision.reason, "snapshot is unchanged")

    def test_only_one_automatic_deployment_per_day(self):
        first = self.trigger(automatic=True)
        self.assertTrue(first.triggered)
        confirm_deployment_success(self.connection)

        second = self.trigger(artifact_hash=snapshot_hash("changed"), automatic=True)

        self.assertFalse(second.triggered)
        self.assertEqual(second.reason, "automatic deployment already used today")

    def test_monthly_counter_and_successful_hash_are_recorded(self):
        decision = self.trigger()
        self.assertTrue(decision.triggered)
        self.assertEqual(MetaRepository(self.connection).get_value("deployment_count_2026_07"), "1")

        confirmation = confirm_deployment_success(self.connection)

        self.assertEqual(confirmation["status"], "ok")
        self.assertEqual(
            MetaRepository(self.connection).get_value("last_successful_snapshot_hash"),
            decision.artifact_hash,
        )

    def test_successful_deployment_submits_queued_indexnow_urls(self):
        changed_url = "https://sinpes.com/font/inter/"
        decision = self.trigger(indexnow_urls=[changed_url])
        self.assertTrue(decision.triggered)

        with patch(
            "app.services.deployment_manager.submit_pending_indexnow",
            return_value={"status": "submitted", "count": 1},
        ) as submit:
            confirmation = confirm_deployment_success(self.connection)

        self.assertEqual(confirmation["indexnow"]["status"], "submitted")
        submit.assert_called_once_with(self.connection)

    def test_confirmation_without_pending_deployment_is_ignored(self):
        self.assertEqual(confirm_deployment_success(self.connection)["status"], "ignored")

    def test_stale_build_lock_is_released(self):
        repository = MetaRepository(self.connection)
        repository.set_value("build_in_progress", "true")
        repository.set_value("last_build_triggered_at", "1")
        repository.set_value("pending_snapshot_hash", "stale")

        with patch("app.services.deployment_manager.config.DEPLOY_STALE_LOCK_SECONDS", 60):
            status = get_deployment_status(self.connection)

        self.assertFalse(status["in_progress"])
        self.assertEqual(status["pending_hash"], "")
        self.assertEqual(status["last_error"], "Cloudflare build confirmation timed out")


if __name__ == "__main__":
    unittest.main()
