from typing import Literal
from pydantic import BaseModel


class ReviewChange(BaseModel):
    status: Literal["open", "cleared", "missing", "expired"]
