from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_authenticated_user_id
from app.models.deduplication import DedupCandidate
from app.models.patient import Patient
from app.models.record import HealthRecord
from app.schemas.dedup import DedupCandidateResponse, DismissRequest, MergeRequest

router = APIRouter(prefix="/dedup", tags=["dedup"])


@router.get("/candidates")
async def list_candidates(
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List dedup candidates with record details."""
    # Get user's record IDs
    records_query = select(HealthRecord.id).where(HealthRecord.user_id == user_id)
    result = await db.execute(records_query)
    record_ids = {row[0] for row in result.all()}

    if not record_ids:
        return {"items": [], "total": 0}

    # Get candidates for user's records
    candidates_result = await db.execute(
        select(DedupCandidate)
        .where(
            DedupCandidate.record_a_id.in_(record_ids),
            DedupCandidate.status == "pending",
        )
        .order_by(DedupCandidate.similarity_score.desc())
    )
    candidates = candidates_result.scalars().all()

    items = []
    for c in candidates:
        # Fetch both records
        a_result = await db.execute(
            select(HealthRecord).where(HealthRecord.id == c.record_a_id)
        )
        b_result = await db.execute(
            select(HealthRecord).where(HealthRecord.id == c.record_b_id)
        )
        record_a = a_result.scalar_one_or_none()
        record_b = b_result.scalar_one_or_none()

        items.append({
            "id": str(c.id),
            "similarity_score": c.similarity_score,
            "match_reasons": c.match_reasons,
            "status": c.status,
            "record_a": {
                "id": str(record_a.id),
                "display_text": record_a.display_text,
                "record_type": record_a.record_type,
                "source_format": record_a.source_format,
                "effective_date": record_a.effective_date.isoformat()
                if record_a.effective_date
                else None,
            }
            if record_a
            else None,
            "record_b": {
                "id": str(record_b.id),
                "display_text": record_b.display_text,
                "record_type": record_b.record_type,
                "source_format": record_b.source_format,
                "effective_date": record_b.effective_date.isoformat()
                if record_b.effective_date
                else None,
            }
            if record_b
            else None,
        })

    return {"items": items, "total": len(items)}


@router.post("/merge")
async def merge_records(
    body: MergeRequest,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Merge two duplicate records."""
    result = await db.execute(
        select(DedupCandidate).where(DedupCandidate.id == body.candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Determine which record to mark as duplicate
    secondary_id = (
        candidate.record_b_id
        if body.primary_record_id == candidate.record_a_id
        else candidate.record_a_id
    )

    # Mark secondary as duplicate
    sec_result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == secondary_id,
            HealthRecord.user_id == user_id,
        )
    )
    secondary = sec_result.scalar_one_or_none()
    if secondary:
        secondary.is_duplicate = True
        secondary.merged_into_id = body.primary_record_id

    candidate.status = "merged"
    candidate.resolved_by = user_id
    candidate.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "merged", "candidate_id": str(candidate.id)}


@router.post("/dismiss")
async def dismiss_candidate(
    body: DismissRequest,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a dedup candidate pair."""
    result = await db.execute(
        select(DedupCandidate).where(DedupCandidate.id == body.candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate.status = "dismissed"
    candidate.resolved_by = user_id
    candidate.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "dismissed", "candidate_id": str(candidate.id)}


@router.post("/scan")
async def scan_for_duplicates(
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a duplicate scan for all patient records."""
    from app.services.dedup.detector import detect_duplicates

    result = await db.execute(
        select(Patient).where(Patient.user_id == user_id)
    )
    patients = result.scalars().all()

    total_found = 0
    for patient in patients:
        count = await detect_duplicates(db, user_id, patient.id)
        total_found += count

    return {"candidates_found": total_found}
