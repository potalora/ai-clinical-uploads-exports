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
    total_file_count: int = 1
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


class UnstructuredUploadResponse(BaseModel):
    upload_id: str
    status: str
    file_type: str


class ExtractedEntitySchema(BaseModel):
    entity_class: str
    text: str
    attributes: dict = {}
    start_pos: int | None = None
    end_pos: int | None = None
    confidence: float = 0.8


class ExtractionResultResponse(BaseModel):
    upload_id: str
    status: str
    extracted_text_preview: str | None = None
    entities: list[ExtractedEntitySchema] = []
    error: str | None = None


class ConfirmExtractionRequest(BaseModel):
    confirmed_entities: list[ExtractedEntitySchema]
    patient_id: str
