from pydantic import BaseModel
from typing import Optional

class QueueItem(BaseModel):
    id: int
    file_path: str
    text_payload: str
    image_path: str
    received_at: str
    processed: bool
    attempts: int
    last_error: Optional[str] = None
    failed: bool
    
class QueueStatus(BaseModel):
    pending_items: int
    dead_letter_items: int


class PipelineOverview(BaseModel):
    live_fonts: int
    ready_to_publish: int
    pending_ingestion: int
    failed_ingestion: int
