from datetime import date
from typing import Literal

from pydantic import BaseModel, model_validator


class ReviewChange(BaseModel):
    status: Literal["open", "cleared", "missing", "expired"]
    valid_until: date | None = None


class DealAction(BaseModel):
    action: Literal["schedule_kickoff", "request_review_update"]


class StageProposal(BaseModel):
    to_stage: Literal["rollout", "rollout_planning"]
    rationale: str


class StageDecision(BaseModel):
    decision: Literal["approve", "reject"]
    to_stage: Literal["rollout", "rollout_planning"] | None = None

    @model_validator(mode="after")
    def edits_require_approval(self):
        if self.decision == "reject" and self.to_stage is not None:
            raise ValueError("Only an approval can specify a destination stage")
        return self


class ResetDataset(BaseModel):
    dataset: Literal["kickoff", "stretch"] = "kickoff"
