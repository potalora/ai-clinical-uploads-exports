from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_authenticated_user_id
from app.middleware.audit import log_audit_event
from app.models.uploaded_file import UploadedFile
from app.schemas.upload import UploadHistoryResponse, UploadResponse, UploadStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])


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

    file_path = upload_dir / f"{user_id}_{file.filename}"
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

    file_path = upload_dir / f"{user_id}_{file.filename}"
    with open(file_path, "wb") as f:
        content = await file.read()
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
