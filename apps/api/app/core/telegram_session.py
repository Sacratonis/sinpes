"""Private filesystem storage for reusable Telethon authorization sessions."""

from __future__ import annotations

import os
import re
from pathlib import Path

from telethon import TelegramClient


_SESSION_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_SESSION_SIDECARS = ("-journal", "-shm", "-wal")


def telegram_session_directory(configured_dir: str | None, database_path: str) -> Path:
    """Return the configured private directory, defaulting beside the database."""
    if configured_dir:
        return Path(configured_dir).expanduser()
    return Path(database_path).expanduser().parent / "telegram-sessions"


def _assert_owned_path(path: Path, *, expected_directory: bool) -> None:
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlinked Telegram session path: {path}")
    stat_result = path.stat()
    if stat_result.st_uid != os.geteuid():
        raise RuntimeError(f"Telegram session path is not owned by the service user: {path}")
    if expected_directory != path.is_dir():
        kind = "directory" if expected_directory else "file"
        raise RuntimeError(f"Telegram session path is not a {kind}: {path}")


def _prepare_private_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _assert_owned_path(path, expected_directory=True)
    else:
        path.mkdir(parents=True, mode=0o700)
        _assert_owned_path(path, expected_directory=True)
    path.chmod(0o700)


def _harden_file(path: Path) -> None:
    if not (path.exists() or path.is_symlink()):
        return
    _assert_owned_path(path, expected_directory=False)
    path.chmod(0o600)


def harden_telegram_session(client: TelegramClient) -> None:
    """Restrict a Telethon SQLite session and its transient sidecars to its owner."""
    filename = getattr(getattr(client, "session", None), "filename", None)
    if not filename:
        return
    session_file = Path(filename)
    _harden_file(session_file)
    for suffix in _SESSION_SIDECARS:
        _harden_file(Path(f"{session_file}{suffix}"))


def create_secure_telegram_client(
    session_name: str,
    api_id: int,
    api_hash: str,
    *,
    session_dir: str | Path,
) -> TelegramClient:
    """Create a Telethon client whose reusable credential is outside the repo."""
    if not _SESSION_NAME.fullmatch(session_name):
        raise ValueError("Telegram session name must contain only letters, digits, '_' or '-'")
    directory = Path(session_dir).expanduser()
    _prepare_private_directory(directory)
    session_base = directory / session_name
    session_file = Path(f"{session_base}.session")
    # Reject or restrict an existing credential before Telethon opens it. This
    # prevents a planted symlink from redirecting SQLite outside the private dir.
    _harden_file(session_file)
    for suffix in _SESSION_SIDECARS:
        _harden_file(Path(f"{session_file}{suffix}"))
    client = TelegramClient(str(session_base), int(api_id), api_hash)
    harden_telegram_session(client)
    return client
