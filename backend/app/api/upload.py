from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

# Global semaphore to limit concurrent Gemini API calls across all uploads
_gemini_semaphore: asyncio.Semaphore | None = None

# Extraction semaphore to limit concurrent file extractions (layer above Gemini semaphore)
_extraction_semaphore: asyncio.Semaphore | None = None

# Queue-based extraction worker state
_extraction_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None


def _get_gemini_semaphore() -> asyncio.Semaphore:
    global _gemini_semaphore
    if _gemini_semaphore is None:
        _gemini_semaphore = asyncio.Semaphore(settings.gemini_concurrency_limit)
    return _gemini_semaphore


def _get_extraction_semaphore() -> asyncio.Semaphore:
    global _extraction_semaphore
    if _extraction_semaphore is None:
        _extraction_semaphore = asyncio.Semaphore(5)
    return _extraction_semaphore


def _get_extraction_queue() -> asyncio.Queue:
    global _extraction_queue
    if _extraction_queue is None:
        _extraction_queue = asyncio.Queue()
    return _extraction_queue


async def _process_and_release(
    sem: asyncio.Semaphore, upload_id: UUID, file_path: Path, user_id: UUID
) -> None:
    """Process one file then release the semaphore."""
    try:
        await _process_unstructured(upload_id, file_path, user_id)
    finally:
        sem.release()


async def _extraction_worker() -> None:
    """Background worker: pull files from queue, process with concurrency limit.

    Only creates tasks when a semaphore slot is available, preventing
    event loop starvation when many files are queued.
    """
    queue = _get_extraction_queue()
    sem = _get_extraction_semaphore()
    active: set[asyncio.Task] = set()

    while True:
        upload_id, file_path, user_id = await queue.get()
        await sem.acquire()
        task = asyncio.create_task(
            _process_and_release(sem, upload_id, file_path, user_id)
        )
        active.add(task)
        task.add_done_callback(active.discard)
        queue.task_done()


def _ensure_worker_running() -> None:
    """Start the extraction worker if it's not already running."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_extraction_worker())

from app.database import get_db
from app.dependencies import get_authenticated_user_id
from app.middleware.audit import log_audit_event
from app.models.record import HealthRecord
from app.models.uploaded_file import UploadedFile
from app.schemas.upload import (
    BatchUploadResponse,
    ConfirmExtractionRequest,
    ExtractedEntitySchema,
    ExtractionResultResponse,
    PendingExtractionFile,
    UnstructuredUploadResponse,
    UploadHistoryResponse,
    UploadResponse,
    UploadStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])


# --- Security helpers ---

MAGIC_BYTES = {
    ".pdf": b"%PDF",
    ".rtf": b"{\\rtf",
    ".tif": [b"\x49\x49\x2a\x00", b"\x4d\x4d\x00\x2a"],  # LE and BE TIFF
    ".tiff": [b"\x49\x49\x2a\x00", b"\x4d\x4d\x00\x2a"],
}


def _validate_magic_bytes(content: bytes, ext: str) -> bool:
    """Validate file content matches expected magic bytes for the extension."""
    expected = MAGIC_BYTES.get(ext)
    if expected is None:
        return True  # No magic bytes check for unknown types
    if isinstance(expected, list):
        return any(content[:len(sig)] == sig for sig in expected)
    return content[:len(expected)] == expected


def _safe_file_path(upload_dir: Path, user_id: UUID, original_filename: str) -> Path:
    """Generate a safe file path preventing path traversal attacks."""
    # Preserve original extension only
    ext = Path(original_filename).suffix.lower()
    safe_name = f"{user_id}_{uuid4().hex}{ext}"
    file_path = (upload_dir / safe_name).resolve()

    # Validate the resolved path is within the upload directory
    upload_dir_resolved = upload_dir.resolve()
    if not str(file_path).startswith(str(upload_dir_resolved)):
        raise HTTPException(status_code=400, detail="Invalid filename")

    return file_path


# --- Endpoints ---


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload a FHIR JSON or ZIP file for ingestion."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = _safe_file_path(upload_dir, user_id, file.filename)
    with open(file_path, "wb") as f:
        content = await file.read()
        if len(content) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large")
        f.write(content)

    # Run ingestion synchronously for now (small files)
    from app.services.ingestion.coordinator import ingest_file

    result = await ingest_file(
        db=db,
        user_id=user_id,
        file_path=file_path,
        original_filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
    )

    await log_audit_event(
        db,
        user_id=user_id,
        action="file.upload",
        resource_type="uploaded_file",
        resource_id=UUID(result["upload_id"]),
        details={"filename": file.filename, "records": result["records_inserted"]},
    )

    return UploadResponse(
        upload_id=result["upload_id"],
        status=result["status"],
        records_inserted=result["records_inserted"],
        errors=result.get("errors", []),
        unstructured_uploads=result.get("unstructured_uploads", []),
    )


@router.post("/epic-export", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_epic_export(
    file: UploadFile,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload an Epic EHI Tables export (ZIP)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = _safe_file_path(upload_dir, user_id, file.filename)
    with open(file_path, "wb") as f:
        content = await file.read()
        # C6: Size check for epic exports
        max_bytes = settings.max_epic_export_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Epic export too large. Maximum size: {settings.max_epic_export_size_mb}MB",
            )
        f.write(content)

    from app.services.ingestion.coordinator import ingest_file

    result = await ingest_file(
        db=db,
        user_id=user_id,
        file_path=file_path,
        original_filename=file.filename,
        mime_type=file.content_type or "application/zip",
    )

    return UploadResponse(
        upload_id=result["upload_id"],
        status=result["status"],
        records_inserted=result["records_inserted"],
        errors=result.get("errors", []),
    )


@router.get("/pending-extraction")
async def get_pending_extractions(
    statuses: str | None = None,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List files by extraction status for this user.

    Args:
        statuses: Comma-separated list of statuses to filter by.
                  Defaults to 'pending_extraction'.
    """
    status_list = [s.strip() for s in statuses.split(",")] if statuses else ["pending_extraction"]

    result = await db.execute(
        select(UploadedFile)
        .where(UploadedFile.user_id == user_id)
        .where(UploadedFile.ingestion_status.in_(status_list))
        .order_by(UploadedFile.created_at.desc())
    )
    files = result.scalars().all()

    await log_audit_event(
        db,
        user_id=user_id,
        action="upload.pending_extraction.list",
        resource_type="uploaded_file",
        resource_id=None,
        details={"count": len(files), "statuses": status_list},
    )

    return {
        "files": [
            PendingExtractionFile(
                id=str(f.id),
                filename=f.filename,
                mime_type=f.mime_type,
                file_category=f.file_category,
                file_size_bytes=f.file_size_bytes,
                created_at=f.created_at.isoformat() if f.created_at else None,
                ingestion_status=f.ingestion_status,
            ).model_dump()
            for f in files
        ],
        "total": len(files),
    }


@router.get("/extraction-progress")
async def extraction_progress(
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get extraction progress counts for the user's unstructured files."""
    from sqlalchemy import func, case

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(UploadedFile.ingestion_status == "completed").label("completed"),
            func.count().filter(UploadedFile.ingestion_status == "processing").label("processing"),
            func.count().filter(UploadedFile.ingestion_status == "failed").label("failed"),
            func.count().filter(UploadedFile.ingestion_status == "pending_extraction").label("pending"),
            func.coalesce(
                func.sum(
                    case(
                        (UploadedFile.ingestion_status == "completed", UploadedFile.record_count),
                        else_=0,
                    )
                ),
                0,
            ).label("records_created"),
        )
        .where(UploadedFile.user_id == user_id)
        .where(UploadedFile.file_category == "unstructured")
    )
    row = result.one()

    return {
        "total": row.total,
        "completed": row.completed,
        "processing": row.processing,
        "failed": row.failed,
        "pending": row.pending,
        "records_created": row.records_created,
    }


@router.post("/trigger-extraction")
async def trigger_extraction(
    body: dict,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger text+entity extraction for pending unstructured files."""
    from app.schemas.upload import TriggerExtractionRequest

    req = TriggerExtractionRequest(**body)
    upload_ids = [UUID(uid) for uid in req.upload_ids]

    # Bulk fetch only uploads owned by this user (HIPAA: row-level security)
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id.in_(upload_ids),
            UploadedFile.user_id == user_id,
        )
    )
    uploads = {u.id: u for u in result.scalars().all()}

    triggered = []
    failed = []

    for uid in upload_ids:
        upload = uploads.get(uid)
        if not upload:
            failed.append({"upload_id": str(uid), "status": "not_found"})
            continue
        if upload.ingestion_status not in ("pending_extraction", "processing", "failed", "awaiting_confirmation"):
            failed.append({"upload_id": str(uid), "status": upload.ingestion_status})
            continue

        upload.ingestion_status = "processing"
        triggered.append(upload)

    if triggered:
        await db.commit()

    # Enqueue files for the background worker (processes up to 5 concurrently,
    # without creating N idle coroutines that exhaust the DB connection pool)
    queue = _get_extraction_queue()
    _ensure_worker_running()
    for upload in triggered:
        await queue.put((upload.id, Path(upload.storage_path), user_id))

    await log_audit_event(
        db,
        user_id=user_id,
        action="upload.trigger_extraction",
        resource_type="uploaded_file",
        resource_id=None,
        details={"triggered": len(triggered), "failed": len(failed)},
    )

    return {
        "triggered": len(triggered),
        "failed": len(failed),
        "results": [
            {"upload_id": str(u.id), "status": "processing"} for u in triggered
        ] + failed,
    }


@router.get("/{upload_id}/status", response_model=UploadStatusResponse)
async def get_upload_status(
    upload_id: UUID,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> UploadStatusResponse:
    """Get ingestion job status."""
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == upload_id,
            UploadedFile.user_id == user_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    return UploadStatusResponse(
        upload_id=str(upload.id),
        filename=upload.filename,
        ingestion_status=upload.ingestion_status,
        record_count=upload.record_count,
        total_file_count=upload.total_file_count or 1,
        ingestion_progress=upload.ingestion_progress or {},
        ingestion_errors=upload.ingestion_errors or [],
        processing_started_at=upload.processing_started_at,
        processing_completed_at=upload.processing_completed_at,
    )


@router.get("/{upload_id}/errors")
async def get_upload_errors(
    upload_id: UUID,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get ingestion errors for a specific upload."""
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == upload_id,
            UploadedFile.user_id == user_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    return {"errors": upload.ingestion_errors or []}


@router.get("/history", response_model=UploadHistoryResponse)
async def get_upload_history(
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> UploadHistoryResponse:
    """Upload history with record counts."""
    result = await db.execute(
        select(UploadedFile)
        .where(UploadedFile.user_id == user_id)
        .order_by(UploadedFile.created_at.desc())
    )
    uploads = result.scalars().all()

    items = []
    for u in uploads:
        items.append({
            "id": str(u.id),
            "filename": u.filename,
            "ingestion_status": u.ingestion_status,
            "record_count": u.record_count,
            "file_size_bytes": u.file_size_bytes,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return UploadHistoryResponse(items=items, total=len(items))


ALLOWED_UNSTRUCTURED = {".pdf", ".rtf", ".tif", ".tiff"}


async def _process_unstructured(upload_id: UUID, file_path: Path, user_id: UUID) -> None:
    """Background task: extract text then entities from an unstructured file."""
    from app.database import async_session_factory
    from app.services.extraction.text_extractor import extract_text
    from app.services.extraction.entity_extractor import extract_entities_async
    from app.services.ai.phi_scrubber import scrub_phi

    async with async_session_factory() as db:
        result = await db.execute(
            select(UploadedFile).where(UploadedFile.id == upload_id)
        )
        upload = result.scalar_one_or_none()
        if not upload:
            return

        try:
            upload.processing_started_at = datetime.now(timezone.utc)
            upload.ingestion_status = "processing"
            await db.commit()

            sem = _get_gemini_semaphore()

            # Step 1: Extract text (Gemini for PDF/TIFF, local for RTF)
            async with sem:
                text, file_type = await extract_text(file_path, settings.gemini_api_key)
            upload.extracted_text = text
            await db.commit()

            # Step 2: Scrub PHI before entity extraction (C4) — local, no semaphore
            scrubbed_text, deident_report = scrub_phi(text)

            # Step 3: Extract entities from scrubbed text (Gemini via LangExtract)
            async with sem:
                extraction = await extract_entities_async(
                    scrubbed_text, upload.filename, settings.gemini_api_key
                )

            if extraction.error:
                upload.ingestion_status = "failed"
                # M2: Sanitize entity extraction error (include error_type for debugging)
                upload.ingestion_errors = [{"error": "Entity extraction failed. Please retry or contact support.", "error_type": "EntityExtractionError"}]
            else:
                entities_json = [
                    {
                        "entity_class": e.entity_class,
                        "text": e.text,
                        "attributes": e.attributes,
                        "start_pos": e.start_pos,
                        "end_pos": e.end_pos,
                        "confidence": e.confidence,
                    }
                    for e in extraction.entities
                ]
                upload.extraction_entities = entities_json

                # Auto-confirm: look up user's first patient and create records
                from app.models.patient import Patient
                from app.services.extraction.entity_extractor import ExtractedEntity
                from app.services.extraction.entity_to_fhir import entity_to_health_record_dict

                patient_result = await db.execute(
                    select(Patient)
                    .where(Patient.user_id == user_id)
                    .limit(1)
                )
                patient = patient_result.scalar_one_or_none()

                if patient:
                    created_count = 0
                    for entity_data in entities_json:
                        entity = ExtractedEntity(
                            entity_class=entity_data["entity_class"],
                            text=entity_data["text"],
                            attributes=entity_data["attributes"],
                            start_pos=entity_data.get("start_pos"),
                            end_pos=entity_data.get("end_pos"),
                            confidence=entity_data.get("confidence", 0.8),
                        )
                        record_dict = entity_to_health_record_dict(
                            entity=entity,
                            user_id=user_id,
                            patient_id=patient.id,
                            source_file_id=upload_id,
                        )
                        if record_dict is not None:
                            health_record = HealthRecord(**record_dict)
                            db.add(health_record)
                            created_count += 1

                    upload.ingestion_status = "completed"
                    upload.record_count = created_count
                else:
                    # No patient found — fall back to manual confirmation
                    upload.ingestion_status = "awaiting_confirmation"

            upload.processing_completed_at = datetime.now(timezone.utc)
            await db.commit()

        except Exception as e:
            # H4: Log full error internally, expose only error type to client
            logger.error("Unstructured processing failed for %s: %s", upload_id, e, exc_info=True)
            error_type = type(e).__name__
            upload.ingestion_status = "failed"
            upload.ingestion_errors = [{"error": f"Processing failed: {error_type}. Contact support if this persists.", "error_type": error_type}]
            upload.processing_completed_at = datetime.now(timezone.utc)
            await db.commit()


@router.post(
    "/unstructured",
    response_model=UnstructuredUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_unstructured(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> UnstructuredUploadResponse:
    """Upload a PDF, RTF, or TIFF for AI-powered text and entity extraction."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UNSTRUCTURED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_UNSTRUCTURED)}",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = _safe_file_path(upload_dir, user_id, file.filename)
    content = await file.read()
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    # M1: Validate magic bytes
    if not _validate_magic_bytes(content, ext):
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match expected format for {ext}",
        )

    with open(file_path, "wb") as f:
        f.write(content)

    file_hash = hashlib.sha256(content).hexdigest()

    upload_record = UploadedFile(
        id=uuid4(),
        user_id=user_id,
        filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=len(content),
        file_hash=file_hash,
        storage_path=str(file_path),
        ingestion_status="processing",
        file_category="unstructured",
    )
    db.add(upload_record)
    await db.commit()
    await db.refresh(upload_record)

    await log_audit_event(
        db,
        user_id=user_id,
        action="file.upload.unstructured",
        resource_type="uploaded_file",
        resource_id=upload_record.id,
        details={"filename": file.filename, "file_type": ext},
    )

    background_tasks.add_task(_process_unstructured, upload_record.id, file_path, user_id)

    from app.services.extraction.text_extractor import detect_file_type
    file_type = detect_file_type(file_path)

    return UnstructuredUploadResponse(
        upload_id=str(upload_record.id),
        status="processing",
        file_type=file_type.value,
    )


@router.post(
    "/unstructured-batch",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_unstructured_batch(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> BatchUploadResponse:
    """Upload multiple unstructured files for concurrent processing."""
    from app.services.extraction.text_extractor import detect_file_type

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for file in files:
        if not file.filename:
            continue

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_UNSTRUCTURED:
            continue

        file_path = _safe_file_path(upload_dir, user_id, file.filename)
        content = await file.read()
        if len(content) > settings.max_file_size_mb * 1024 * 1024:
            continue

        if not _validate_magic_bytes(content, ext):
            continue

        with open(file_path, "wb") as f:
            f.write(content)

        file_hash = hashlib.sha256(content).hexdigest()

        upload_record = UploadedFile(
            id=uuid4(),
            user_id=user_id,
            filename=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size_bytes=len(content),
            file_hash=file_hash,
            storage_path=str(file_path),
            ingestion_status="processing",
            file_category="unstructured",
        )
        db.add(upload_record)
        await db.flush()

        await log_audit_event(
            db,
            user_id=user_id,
            action="file.upload.unstructured",
            resource_type="uploaded_file",
            resource_id=upload_record.id,
            details={"filename": file.filename, "file_type": ext},
        )

        background_tasks.add_task(_process_unstructured, upload_record.id, file_path, user_id)

        file_type = detect_file_type(file_path)
        results.append(UnstructuredUploadResponse(
            upload_id=str(upload_record.id),
            status="processing",
            file_type=file_type.value,
        ))

    await db.commit()

    return BatchUploadResponse(uploads=results, total=len(results))


@router.get("/{upload_id}/extraction", response_model=ExtractionResultResponse)
async def get_extraction_results(
    upload_id: UUID,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> ExtractionResultResponse:
    """Get extraction results for an unstructured upload."""
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == upload_id,
            UploadedFile.user_id == user_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    entities = []
    if upload.extraction_entities:
        entities = [
            ExtractedEntitySchema(**e) for e in upload.extraction_entities
        ]

    preview = None
    if upload.extracted_text:
        preview = upload.extracted_text[:500]

    error = None
    if upload.ingestion_errors:
        errors = upload.ingestion_errors
        if errors and isinstance(errors, list) and len(errors) > 0:
            error = errors[0].get("error", str(errors[0])) if isinstance(errors[0], dict) else str(errors[0])

    return ExtractionResultResponse(
        upload_id=str(upload.id),
        status=upload.ingestion_status,
        extracted_text_preview=preview,
        entities=entities,
        error=error,
    )


@router.post("/{upload_id}/confirm-extraction")
async def confirm_extraction(
    upload_id: UUID,
    body: ConfirmExtractionRequest,
    request: Request,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Confirm extracted entities and save them as HealthRecords."""
    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == upload_id,
            UploadedFile.user_id == user_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    if not body.patient_id:
        raise HTTPException(status_code=400, detail="patient_id is required")

    from app.services.extraction.entity_extractor import ExtractedEntity
    from app.services.extraction.entity_to_fhir import entity_to_health_record_dict

    patient_uuid = UUID(body.patient_id)
    created_count = 0

    for entity_data in body.confirmed_entities:
        entity = ExtractedEntity(
            entity_class=entity_data.entity_class,
            text=entity_data.text,
            attributes=entity_data.attributes,
            start_pos=entity_data.start_pos,
            end_pos=entity_data.end_pos,
            confidence=entity_data.confidence,
        )

        record_dict = entity_to_health_record_dict(
            entity=entity,
            user_id=user_id,
            patient_id=patient_uuid,
            source_file_id=upload_id,
        )
        if record_dict is None:
            continue

        health_record = HealthRecord(**record_dict)
        db.add(health_record)
        created_count += 1

    upload.ingestion_status = "completed"
    upload.record_count = created_count
    upload.processing_completed_at = datetime.now(timezone.utc)
    await db.commit()

    await log_audit_event(
        db,
        user_id=user_id,
        action="extraction.confirm",
        resource_type="uploaded_file",
        resource_id=upload_id,
        details={"records_created": created_count, "patient_id": body.patient_id},
    )

    return {
        "upload_id": str(upload_id),
        "records_created": created_count,
        "status": "completed",
    }
