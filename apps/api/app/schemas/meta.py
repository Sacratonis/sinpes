from pydantic import BaseModel
from typing import Optional

class MetaRecord(BaseModel):
    key: str
    value: str
