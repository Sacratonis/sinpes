import sqlite3
import time
from typing import Optional
from app.schemas.queue import PipelineOverview, QueueItem, QueueStatus

class QueueRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_stats(self) -> QueueStatus:
        pending = self.conn.execute("SELECT COUNT(*) as c FROM upload_queue WHERE processed = 0 AND failed = 0").fetchone()['c']
        failed = self.conn.execute("SELECT COUNT(*) as c FROM upload_queue WHERE failed = 1").fetchone()['c']
        return QueueStatus(pending_items=pending, dead_letter_items=failed)

    def get_pipeline_overview(self) -> PipelineOverview:
        stats = self.get_stats()
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM font_registry "
            "WHERE status IN ('active', 'queued') GROUP BY status"
        ).fetchall()
        counts = {row["status"]: row["count"] for row in rows}
        return PipelineOverview(
            live_fonts=counts.get("active", 0),
            ready_to_publish=counts.get("queued", 0),
            pending_ingestion=stats.pending_items,
            failed_ingestion=stats.dead_letter_items,
        )

    def enqueue_item(self, file_path: str, text_payload: str, image_path: str) -> None:
        self.conn.execute(
            """INSERT INTO upload_queue 
               (file_path, text_payload, image_path, received_at) 
               VALUES (?, ?, ?, ?)""",
            (file_path, text_payload, image_path, str(time.time()))
        )

    def get_oldest_pending_item(self) -> Optional[QueueItem]:
        row = self.conn.execute(
            """SELECT * FROM upload_queue 
               WHERE processed = 0 AND failed = 0 AND CAST(received_at AS REAL) <= ?
               ORDER BY CAST(received_at AS REAL) ASC LIMIT 1""",
            (time.time(),),
        ).fetchone()
        return QueueItem(**dict(row)) if row else None

    def mark_processed(self, item_id: int) -> None:
        self.conn.execute(
            "UPDATE upload_queue SET processed = 1, last_error = NULL WHERE id = ?",
            (item_id,),
        )

    def mark_failed(self, item_id: int) -> None:
        self.conn.execute("UPDATE upload_queue SET failed = 1 WHERE id = ?", (item_id,))

    def increment_attempts(self, item_id: int, error_msg: str) -> None:
        self.conn.execute(
            """UPDATE upload_queue 
               SET attempts = attempts + 1, last_error = ? 
               WHERE id = ?""", 
            (error_msg, item_id)
        )

    def defer_item(self, item_id: int, error_msg: str, delay_seconds: int) -> None:
        self.conn.execute(
            """UPDATE upload_queue
               SET attempts = attempts + 1, last_error = ?, received_at = ?
               WHERE id = ?""",
            (error_msg, str(time.time() + max(1, delay_seconds)), item_id),
        )

    def get_failed_items(self, limit: int = 20):
        return self.conn.execute(
            "SELECT id, attempts, last_error FROM upload_queue "
            "WHERE failed = 1 ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def retry_item(self, item_id: int) -> bool:
        cursor = self.conn.execute(
            "UPDATE upload_queue SET failed = 0, processed = 0, attempts = 0, "
            "last_error = NULL WHERE id = ? AND failed = 1",
            (item_id,),
        )
        return cursor.rowcount == 1
