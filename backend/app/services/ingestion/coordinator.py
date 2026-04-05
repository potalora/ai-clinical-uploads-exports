from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.patient import Patient
from app.models.uploaded_file import UploadedFile
from app.services.ingestion.epic_parser import parse_epic_export
from app.services.ingestion.fhir_parser import parse_fhir_bundle

logger = logging.getLogger(__name__)


async def get_or_create_patient(
    db: AsyncSession, user_id: UUID, fhir_data: dict | None = None
) -> Patient:
    """Get existing patient for user or create a default one."""
    result = await db.execute(select(Patient).where(Patient.user_id == user_id))
    patient = result.scalar_one_or_none()
    if patient:
        return patient

    patient = Patient(
        id=uuid4(),
        user_id=user_id,
        fhir_id=fhir_data.get("id") if fhir_data else None,
        gender=fhir_data.get("gender") if fhir_data else None,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def detect_file_type(file_path: Path) -> str:
    """Detect whether a file is FHIR JSON, Epic TSV directory, or ZIP."""
    if file_path.is_dir():
        tsv_files = list(file_path.glob("*.tsv"))
        if tsv_files:
            return "epic_ehi"
        return "unknown"

    suffix = file_path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix == ".json":
        return "fhir_r4"
    if suffix == ".tsv":
        return "epic_ehi_single"
    return "unknown"


async def ingest_file(
    db: AsyncSession,
    user_id: UUID,
    file_path: Path,
    original_filename: str,
    mime_type: str = "application/octet-stream",
) -> dict:
    """Main ingestion entry point. Detects file type and routes to appropriate parser."""
    file_type = detect_file_type(file_path)
    file_hash = compute_file_hash(file_path) if file_path.is_file() else "directory"
    file_size = file_path.stat().st_size if file_path.is_file() else 0

    # Create upload record
    upload = UploadedFile(
        id=uuid4(),
        user_id=user_id,
        filename=original_filename,
        mime_type=mime_type,
        file_size_bytes=file_size,
        file_hash=file_hash,
        storage_path=str(file_path),
        ingestion_status="processing",
        processing_started_at=datetime.now(timezone.utc),
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    patient = await get_or_create_patient(db, user_id)

    try:
        if file_type == "fhir_r4":
            stats = await _ingest_fhir(db, user_id, patient.id, upload.id, file_path)
        elif file_type == "epic_ehi":
            stats = await _ingest_epic_dir(db, user_id, patient.id, upload.id, file_path)
        elif file_type == "zip":
            stats = await _ingest_zip(db, user_id, patient.id, upload.id, file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        upload.ingestion_status = "completed"
        upload.record_count = stats.get("records_inserted", 0)
        upload.ingestion_errors = stats.get("errors", [])
        upload.processing_completed_at = datetime.now(timezone.utc)
        upload.ingestion_progress = {
            "total_entries": stats.get("total_entries", 0),
            "records_inserted": stats.get("records_inserted", 0),
            "records_skipped": stats.get("records_skipped", 0),
        }
        await db.commit()

        return {
            "upload_id": str(upload.id),
            "status": "completed",
            "records_inserted": stats.get("records_inserted", 0),
            "errors": stats.get("errors", []),
            "unstructured_uploads": stats.get("unstructured_files", []),
        }

    except Exception as e:
        logger.error("Ingestion failed for %s: %s", original_filename, e)
        upload.ingestion_status = "failed"
        upload.ingestion_errors = [{"error": str(e)}]
        upload.processing_completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise


async def _ingest_fhir(
    db: AsyncSession,
    user_id: UUID,
    patient_id: UUID,
    upload_id: UUID,
    file_path: Path,
) -> dict:
    """Ingest a FHIR R4 JSON file."""
    # Check if bundle contains a Patient resource
    with open(file_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if data.get("resourceType") == "Bundle":
        for entry in data.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                patient = await get_or_create_patient(db, user_id, resource)
                patient_id = patient.id
                break

    return await parse_fhir_bundle(
        file_path=file_path,
        user_id=user_id,
        patient_id=patient_id,
        source_file_id=upload_id,
        db=db,
    )


async def _ingest_epic_dir(
    db: AsyncSession,
    user_id: UUID,
    patient_id: UUID,
    upload_id: UUID,
    dir_path: Path,
) -> dict:
    """Ingest an Epic EHI Tables export directory."""
    return await parse_epic_export(
        export_dir=dir_path,
        user_id=user_id,
        patient_id=patient_id,
        source_file_id=upload_id,
        db=db,
    )


async def _ingest_zip(
    db: AsyncSession,
    user_id: UUID,
    patient_id: UUID,
    upload_id: UUID,
    zip_path: Path,
) -> dict:
    """Extract and ingest a ZIP file with mixed content support."""
    temp_dir = Path(settings.temp_extract_dir) / str(upload_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)

        # Collect all files, excluding schema dirs and readme
        all_files = list(temp_dir.rglob("*"))

        tsv_files = []
        json_files = []
        unstructured_files = []

        for f in all_files:
            if not f.is_file():
                continue
            # Skip schema directories and readme files
            parts_lower = [p.lower() for p in f.parts]
            if any("schema" in p for p in parts_lower):
                continue
            if f.stem.lower() == "readme":
                continue

            suffix = f.suffix.lower()
            if suffix == ".tsv":
                tsv_files.append(f)
            elif suffix == ".json":
                json_files.append(f)
            elif suffix in (".pdf", ".rtf", ".tif", ".tiff"):
                unstructured_files.append(f)

        stats = {
            "total_entries": 0,
            "records_inserted": 0,
            "records_skipped": 0,
            "errors": [],
            "unstructured_files": [],
        }

        # Process structured content
        if tsv_files:
            tsv_dir = tsv_files[0].parent
            epic_stats = await _ingest_epic_dir(db, user_id, patient_id, upload_id, tsv_dir)
            stats["total_entries"] += epic_stats.get("total_files", 0)
            stats["records_inserted"] += epic_stats.get("records_inserted", 0)
            stats["records_skipped"] += epic_stats.get("records_skipped", 0)
            stats["errors"].extend(epic_stats.get("errors", []))

        if json_files:
            for jf in json_files:
                try:
                    result = await _ingest_fhir(db, user_id, patient_id, upload_id, jf)
                    stats["total_entries"] += result.get("total_entries", 0)
                    stats["records_inserted"] += result.get("records_inserted", 0)
                    stats["records_skipped"] += result.get("records_skipped", 0)
                    stats["errors"].extend(result.get("errors", []))
                except Exception as e:
                    stats["errors"].append({"file": jf.name, "error": str(e)})

        # Queue unstructured files for extraction
        if unstructured_files:
            for uf in unstructured_files:
                try:
                    # Copy to upload dir with UUID filename
                    dest_name = f"{uuid4()}{uf.suffix}"
                    dest_path = Path(settings.upload_dir) / dest_name
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(uf, dest_path)

                    # Determine mime type
                    suffix = uf.suffix.lower()
                    mime_map = {
                        ".pdf": "application/pdf",
                        ".rtf": "application/rtf",
                        ".tif": "image/tiff",
                        ".tiff": "image/tiff",
                    }

                    unstr_upload = UploadedFile(
                        id=uuid4(),
                        user_id=user_id,
                        filename=uf.name,
                        mime_type=mime_map.get(suffix, "application/octet-stream"),
                        file_size_bytes=uf.stat().st_size,
                        file_hash=compute_file_hash(uf),
                        storage_path=str(dest_path),
                        ingestion_status="pending_extraction",
                        file_category="unstructured",
                    )
                    db.add(unstr_upload)
                    stats["unstructured_files"].append({
                        "upload_id": str(unstr_upload.id),
                        "filename": uf.name,
                        "status": "pending_extraction",
                    })
                except Exception as e:
                    stats["errors"].append({"file": uf.name, "error": str(e)})

            await db.commit()

        if not tsv_files and not json_files and not unstructured_files:
            raise ValueError("ZIP contains no processable files")

        return stats
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
