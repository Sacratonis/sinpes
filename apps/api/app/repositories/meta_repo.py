import sqlite3
from typing import Optional

class MetaRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        
    def get_value(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else None
        
    def set_value(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
