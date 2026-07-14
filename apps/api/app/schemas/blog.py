from pydantic import BaseModel
from typing import Optional

class BlogPost(BaseModel):
    id: str
    source_topic: str
    language: str
    validity: str
    title: Optional[str] = None
    slug: Optional[str] = None
    meta_description: Optional[str] = None
    body_markdown: Optional[str] = None
    body_html: Optional[str] = None
    image_url: Optional[str] = None
    image_alt_text: Optional[str] = None
    status: str
    created_at: str
    published_at: Optional[str] = None
