from pydantic import BaseModel

class Category(BaseModel):
    slug: str
    display_name: str
    
class PendingCategory(BaseModel):
    id: int
    name: str
    expires_at: str
    resolved: bool
