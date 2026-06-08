from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class DedupCandidateResponse(BaseModel):
    id: UUID
    record_a_id: UUID
    record_b_id: UUID
    similarity_score: float
    match_reasons: dict
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MergeRequest(BaseModel):
    candidate_id: UUID
    primary_record_id: UUID | None = None


class DismissRequest(BaseModel):
    candidate_id: UUID


class ReviewRecordSummary(BaseModel):
    id: UUID
    display_text: str
    record_type: str
    fhir_resource: dict | None = None

    model_config = {"from_attributes": True}


class ReviewCandidateResponse(BaseModel):
    candidate_id: UUID
    primary: ReviewRecordSummary
    secondary: ReviewRecordSummary
    similarity_score: float
    llm_classification: str | None = None
    llm_confidence: float | None = None
    llm_explanation: str | None = None
    field_diff: dict | None = None
    merged_at: datetime | None = None


class ReviewResponse(BaseModel):
    upload: dict
    auto_merged: list[ReviewCandidateResponse]
    needs_review: dict[str, list[ReviewCandidateResponse]]


class ResolutionAction(BaseModel):
    candidate_id: UUID
    action: str  # merge, update, dismiss, keep_both
    field_overrides: list[str] | None = None


class BulkResolveRequest(BaseModel):
    """Bulk resolve pending dedup candidates by ids or by score band.

    When ``candidate_ids`` is supplied those specific pending candidates are
    acted on; otherwise every pending candidate whose score falls in
    ``[score_min, score_max)`` is acted on (user-scoped in the handler).
    """

    action: str  # "merge" | "dismiss"
    candidate_ids: list[UUID] | None = None
    score_min: float | None = None
    score_max: float | None = None

    @field_validator("action")
    @classmethod
    def _validate_action(cls, value: str) -> str:
        """Reject any action other than merge/dismiss."""
        if value not in ("merge", "dismiss"):
            raise ValueError("action must be 'merge' or 'dismiss'")
        return value


class UndoMergeRequest(BaseModel):
    candidate_id: UUID


class UndoBulkRequest(BaseModel):
    """Bulk-undo a set of merged candidates by id.

    Each id must reference a ``status=="merged"`` candidate the requesting user
    owns; non-matching ids are silently skipped by the handler.
    """

    candidate_ids: list[UUID]
