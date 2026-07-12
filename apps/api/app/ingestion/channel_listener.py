import sqlite3
from app.schemas.ingestion import FontIngestionPayload

def queue_incoming_upload(db_conn: sqlite3.Connection, payload: FontIngestionPayload):
    """
    Called when @SinpesBot receives the batched upload from the curator.
    Stores the validated v1 payload as JSON for the queue manager.
    """
    from app.repositories.queue_repo import QueueRepository
    repo = QueueRepository(db_conn)
    repo.enqueue_item(
        file_path=payload.font_files[0],
        text_payload=payload.model_dump_json(),
        image_path="",
    )
    db_conn.commit()
