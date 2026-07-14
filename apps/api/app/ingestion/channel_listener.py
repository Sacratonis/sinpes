import json
import sqlite3
import time
from app.schemas.ingestion import FontIngestionPayload


def find_mergeable_family_uploads(
    db_conn: sqlite3.Connection, slug: str, window_seconds: int = 900
) -> list[dict]:
    """Find recent, untouched queue rows for a Telegram-split font family."""
    rows = db_conn.execute(
        "SELECT id, file_path, text_payload, image_path, received_at FROM upload_queue "
        "WHERE processed = 0 AND failed = 0 AND attempts = 0 AND CAST(received_at AS REAL) >= ? "
        "ORDER BY id ASC",
        (time.time() - window_seconds,),
    ).fetchall()
    matches = []
    for row in rows:
        try:
            data = json.loads(row["text_payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        if data.get("slug") != slug:
            continue
        matches.append({
            "id": row["id"],
            "font_files": data.get("font_files") or [row["file_path"]],
        })
    return matches


def queue_incoming_upload(
    db_conn: sqlite3.Connection,
    payload: FontIngestionPayload,
    merge_item_ids: list[int] | None = None,
):
    """
    Called when @SinpesBot receives the batched upload from the curator.
    Stores the validated v1 payload as JSON for the queue manager.
    """
    from app.repositories.queue_repo import QueueRepository
    merge_ids = [int(value) for value in (merge_item_ids or [])]
    eligible_ids = []
    if merge_ids:
        placeholders = ",".join("?" for _ in merge_ids)
        eligible_ids = [row["id"] for row in db_conn.execute(
            f"SELECT id FROM upload_queue WHERE id IN ({placeholders}) "
            "AND processed = 0 AND failed = 0 AND attempts = 0 ORDER BY id ASC",
            tuple(merge_ids),
        ).fetchall()]
    if eligible_ids:
        survivor = eligible_ids[0]
        db_conn.execute(
            "UPDATE upload_queue SET file_path = ?, text_payload = ?, image_path = '' WHERE id = ?",
            (payload.font_files[0], payload.model_dump_json(), survivor),
        )
        if len(eligible_ids) > 1:
            placeholders = ",".join("?" for _ in eligible_ids[1:])
            db_conn.execute(f"DELETE FROM upload_queue WHERE id IN ({placeholders})", tuple(eligible_ids[1:]))
        queue_id = survivor
        merged = True
    else:
        repo = QueueRepository(db_conn)
        repo.enqueue_item(
            file_path=payload.font_files[0],
            text_payload=payload.model_dump_json(),
            image_path="",
        )
        queue_id = db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        merged = False
    db_conn.commit()
    return {"queue_id": queue_id, "merged": merged}
