from datetime import date
from typing import Literal
from pydantic import BaseModel


class ReviewChange(BaseModel):
    status: Literal["open", "cleared", "missing", "expired"]
    valid_until: date | None = None


class DealAction(BaseModel):
    action: Literal["schedule_kickoff", "request_review_update"]
