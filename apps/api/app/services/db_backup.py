"""WAL-consistent local SQLite backups."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import config


def backup_database() -> dict:
    source = Path(config.DATABASE_PATH)
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")

    backup_dir = Path(config.DATABASE_BACKUP_DIR)
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"sinpes-{timestamp}.db"

    source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    destination_conn = None
    try:
        destination_conn = sqlite3.connect(backup_path)
        source_conn.backup(destination_conn)
        destination_conn.commit()
    except Exception:
        if backup_path.exists():
            backup_path.unlink()
        raise
    finally:
        if destination_conn is not None:
            destination_conn.close()
        source_conn.close()

    os.chmod(backup_path, 0o600)
    return {"path": str(backup_path), "uploaded": False}
