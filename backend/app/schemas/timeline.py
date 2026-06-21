from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TimelineGauge(BaseModel):
    value: float
    low: float
    high: float

    model_config = {"from_attributes": True}


class TimelinePreview(BaseModel):
    """Compact, server-computed scalar preview for a timeline row.

    Flat and type-agnostic: the row renders value+unit, one neutral flag chip,
    an optional reference-range gauge, and a few facet chips. Built from the
    stored FHIR JSONB (see ``services/timeline_preview.py``). ``emphasis`` is a
    NEUTRAL visual token only ("normal"|"notable"|"muted") — never good/bad.
    """

    value: str | None = None
    unit: str | None = None
    flag: str | None = None
    emphasis: str | None = None
    gauge: TimelineGauge | None = None
    facets: list[str] = []

    model_config = {"from_attributes": True}


class TimelineEvent(BaseModel):
    id: UUID
    record_type: str
    display_text: str
    effective_date: datetime | None
    code_display: str | None
    category: list[str] | None
    provider: str | None = None
    preview: TimelinePreview | None = None

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    events: list[TimelineEvent]
    total: int


class TimelineStats(BaseModel):
    total_records: int
    records_by_type: dict[str, int]
    date_range_start: datetime | None
    date_range_end: datetime | None
