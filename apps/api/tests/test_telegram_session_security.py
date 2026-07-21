import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.telegram_session import (
    create_secure_telegram_client,
    harden_telegram_session,
    telegram_session_directory,
)
from app.ingestion import bot_listener
from app.services import seo_bot, writer_bot


class TelegramSessionFilesystemTests(unittest.TestCase):
    def test_session_directory_and_database_are_owner_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            session_directory = Path(temporary_directory) / "telegram"
            client = create_secure_telegram_client(
                "security_test",
                12345,
                "0123456789abcdef0123456789abcdef",
                session_dir=session_directory,
            )
            try:
                session_file = Path(client.session.filename)
                self.assertTrue(session_file.exists())
                self.assertEqual(stat.S_IMODE(session_directory.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(session_file.stat().st_mode), 0o600)

                session_directory.chmod(0o777)
                session_file.chmod(0o666)
                second_client = create_secure_telegram_client(
                    "security_test",
                    12345,
                    "0123456789abcdef0123456789abcdef",
                    session_dir=session_directory,
                )
                second_client.session.close()
                self.assertEqual(stat.S_IMODE(session_directory.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(session_file.stat().st_mode), 0o600)
            finally:
                client.session.close()

    def test_session_sidecars_are_hardened(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            client = create_secure_telegram_client(
                "sidecars",
                12345,
                "0123456789abcdef0123456789abcdef",
                session_dir=temporary_directory,
            )
            try:
                session_file = Path(client.session.filename)
                sidecar = Path(f"{session_file}-wal")
                sidecar.write_bytes(b"runtime")
                sidecar.chmod(0o666)
                harden_telegram_session(client)
                self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)
            finally:
                client.session.close()

    def test_invalid_name_and_symlinked_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaises(ValueError):
                create_secure_telegram_client(
                    "../escape",
                    12345,
                    "0123456789abcdef0123456789abcdef",
                    session_dir=root,
                )

            real_directory = root / "real"
            real_directory.mkdir()
            symlink_directory = root / "sessions"
            symlink_directory.symlink_to(real_directory, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlinked"):
                create_secure_telegram_client(
                    "safe_name",
                    12345,
                    "0123456789abcdef0123456789abcdef",
                    session_dir=symlink_directory,
                )

    def test_symlinked_session_file_is_rejected_before_telethon_opens_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "target"
            target.write_bytes(b"must not be opened")
            session_file = root / "planted.session"
            session_file.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "symlinked"):
                create_secure_telegram_client(
                    "planted",
                    12345,
                    "0123456789abcdef0123456789abcdef",
                    session_dir=root,
                )
            self.assertEqual(target.read_bytes(), b"must not be opened")

    def test_default_directory_is_beside_database_not_source_checkout(self):
        self.assertEqual(
            telegram_session_directory(None, "/srv/sinpes/data/sinpes.db"),
            Path("/srv/sinpes/data/telegram-sessions"),
        )


class TelegramSessionStartupWiringTests(unittest.TestCase):
    def test_all_three_real_bot_clients_use_secure_factory(self):
        modules_and_names = (
            (bot_listener, "sinpes_bot_session"),
            (writer_bot, "sinpes_writer_bot_session"),
            (seo_bot, "sinpes_seo_bot_session"),
        )
        sentinel = object()
        for module, expected_name in modules_and_names:
            with self.subTest(module=module.__name__), patch.object(
                module,
                "create_secure_telegram_client",
                return_value=sentinel,
            ) as factory:
                self.assertIs(module.create_client(), sentinel)
                self.assertEqual(factory.call_args.args[0], expected_name)
                self.assertEqual(
                    Path(factory.call_args.kwargs["session_dir"]),
                    telegram_session_directory(
                        module.config.TELEGRAM_SESSION_DIR,
                        module.config.DATABASE_PATH,
                    ),
                )

    @staticmethod
    def _fake_client():
        client = MagicMock()
        client.on.side_effect = lambda *args, **kwargs: (lambda handler: handler)

        def close_scheduled_coroutine(coroutine):
            coroutine.close()

        client.loop.create_task.side_effect = close_scheduled_coroutine
        return client

    def test_ingestion_startup_rehardens_session_after_authorization(self):
        client = self._fake_client()
        with (
            patch.object(bot_listener, "create_client", return_value=client),
            patch.object(bot_listener, "register_handlers"),
            patch.object(bot_listener, "harden_telegram_session") as harden,
            patch.object(bot_listener.os, "makedirs"),
        ):
            bot_listener.start_listener()
        client.start.assert_called_once_with(bot_token=bot_listener.config.oracle.telegram_bot_token)
        harden.assert_called_once_with(client)
        client.run_until_disconnected.assert_called_once_with()

    def test_writer_startup_rehardens_session_after_authorization(self):
        client = self._fake_client()
        with (
            patch.object(writer_bot, "create_client", return_value=client),
            patch.object(writer_bot, "harden_telegram_session") as harden,
            patch.object(writer_bot.config.writer, "telegram_bot_token", "writer-token"),
            patch.object(writer_bot.config.writer, "telegram_review_channel_id", "-100123"),
        ):
            writer_bot.start_bot()
        client.start.assert_called_once_with(bot_token="writer-token")
        harden.assert_called_once_with(client)
        client.run_until_disconnected.assert_called_once_with()

    def test_seo_startup_rehardens_session_after_authorization(self):
        client = self._fake_client()
        with (
            patch.object(seo_bot, "create_client", return_value=client),
            patch.object(seo_bot, "harden_telegram_session") as harden,
            patch.object(seo_bot.config.seo, "enabled", True),
            patch.object(seo_bot.config.seo, "telegram_bot_token", "seo-token"),
            patch.object(seo_bot.config.seo, "telegram_admin_chat_id", "123"),
        ):
            seo_bot.start_bot()
        client.start.assert_called_once_with(bot_token="seo-token")
        harden.assert_called_once_with(client)
        client.run_until_disconnected.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
