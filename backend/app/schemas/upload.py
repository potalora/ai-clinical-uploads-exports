from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UploadResponse(BaseModel):
    upload_id: str
    status: str
    records_inserted: int
    errors: list[Any] = []


class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    ingestion_status: str
    record_count: int
    ingestion_progress: dict = {}
    ingestion_errors: list[Any] = []
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None


class UploadHistoryItem(BaseModel):
    id: str
    filename: str
    ingestion_status: str
    record_count: int
    file_size_bytes: int | None = None
    created_at: str | None = None


class UploadHistoryResponse(BaseModel):
    items: list[UploadHistoryItem]
    total: int
