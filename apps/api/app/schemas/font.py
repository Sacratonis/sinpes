from pydantic import BaseModel
from typing import Optional

class FontRegistry(BaseModel):
    rowid: Optional[int] = None
    slug: str
    display_name: str
    is_demo: bool
    category: str
    variants: str
    weights: Optional[str] = None
    woff2_url: str
    file_format: str
    file_size_kb: int
    use_cases: str
    status: str
    vault_status: Optional[str] = None
    file_hash: str
    embedded_family_name: Optional[str] = None
    last_updated: str
    download_zip_url: Optional[str] = None

class FontTranslation(BaseModel):
    slug: str
    locale: str
    description: str
    seo_image_url: str
