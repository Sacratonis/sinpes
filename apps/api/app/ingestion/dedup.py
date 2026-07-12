import sqlite3
from typing import Callable

def check_duplicate(db_conn: sqlite3.Connection, sha256: str, font_name: str, alert_callback: Callable[[str], None]) -> bool:
    from app.repositories.font_repo import FontRepository
    repo = FontRepository(db_conn)
    
    if repo.check_hash_exists(sha256):
        alert_callback(
            f"'{font_name}' was dropped — it's an exact duplicate of "
            f"a file already archived."
        )
        return True  # duplicate, do not insert

    return False