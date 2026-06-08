from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_authenticated_user_id
from app.middleware.audit import log_audit_event
from app.models.deduplication import DedupCandidate
from app.models.patient import Patient
from app.models.record import HealthRecord
from app.schemas.dedup import (
    BulkResolveRequest,
    DismissRequest,
    MergeRequest,
    UndoBulkRequest,
    UndoMergeRequest,
)
from app.services.dedup.detector import _apply_merge

router = APIRouter(prefix="/dedup", tags=["dedup"])


def _record_summary(record: HealthRecord) -> dict:
    """Compact record projection for the merges pane (survivor/archived).

    Args:
        record: The health record to project.

    Returns:
        A dict of ``id``, ``display_text``, ``record_type``, ``source_format``,
        and ISO ``effective_date`` (or ``None``).
    """
    return {
        "id": str(record.id),
        "display_text": record.display_text,
        "record_type": record.record_type,
        "source_format": record.source_format,
        "effective_date": record.effective_date.isoformat()
        if record.effective_date
        else None,
    }


@router.get("/candidates")
async def list_candidates(
    request: Request,
    page: int = 1,
    limit: int = 20,
    score_min: float | None = None,
    score_max: float | None = None,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List dedup candidates with record details (paginated).

    Optional ``score_min``/``score_max`` restrict pending candidates to
    ``score_min <= similarity_score < score_max`` (each bound applied only when
    supplied).
    """
    from sqlalchemy import func
    from sqlalchemy.orm import aliased

    RecordA = aliased(HealthRecord)
    RecordB = aliased(HealthRecord)

    # Base query with JOINs — filter by user through record_a
    base = (
        select(DedupCandidate, RecordA, RecordB)
        .join(RecordA, DedupCandidate.record_a_id == RecordA.id)
        .join(RecordB, DedupCandidate.record_b_id == RecordB.id)
        .where(
            RecordA.user_id == user_id,
            DedupCandidate.status == "pending",
        )
    )

    # Compare on rounded integer percent, never the raw float. _compare_records
    # sums produce e.g. 0.4+0.3+0.1 = 0.7999999999999999 (a "80%" match), so a
    # raw ``score < 0.80`` would wrongly drop it out of band 80. Rounding to
    # percent keeps this filter, the summary banding, and /resolve-bulk aligned.
    if score_min is not None:
        base = base.where(
            func.round(DedupCandidate.similarity_score * 100) >= round(score_min * 100)
        )
    if score_max is not None:
        base = base.where(
            func.round(DedupCandidate.similarity_score * 100) < round(score_max * 100)
        )

    # Count total pending candidates (use a subquery for efficiency)
    count_q = select(func.count()).select_from(base.subquery())
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    if total == 0:
        await log_audit_event(
            db, user_id=user_id, action="dedup.list_candidates",
            resource_type="dedup",
            ip_address=request.client.host if request.client else None,
            details={"total": 0, "page": page},
        )
        return {"items": [], "total": 0}

    # Paginated fetch with JOIN
    offset = (page - 1) * limit
    result = await db.execute(
        base.order_by(DedupCandidate.similarity_score.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    items = []
    for candidate, record_a, record_b in rows:
        items.append({
            "id": str(candidate.id),
            "similarity_score": candidate.similarity_score,
            "match_reasons": candidate.match_reasons,
            "status": candidate.status,
            "record_a": {
                "id": str(record_a.id),
                "display_text": record_a.display_text,
                "record_type": record_a.record_type,
                "source_format": record_a.source_format,
                "effective_date": record_a.effective_date.isoformat()
                if record_a.effective_date
                else None,
            },
            "record_b": {
                "id": str(record_b.id),
                "display_text": record_b.display_text,
                "record_type": record_b.record_type,
                "source_format": record_b.source_format,
                "effective_date": record_b.effective_date.isoformat()
                if record_b.effective_date
                else None,
            },
        })

    await log_audit_event(
        db, user_id=user_id, action="dedup.list_candidates",
        resource_type="dedup",
        ip_address=request.client.host if request.client else None,
        details={"total": total, "page": page},
    )

    return {"items": items, "total": total}


@router.get("/candidates/summary")
async def candidates_summary(
    request: Request,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Histogram of pending candidates bucketed into 10-point score bands.

    Bands are ``floor(similarity_score * 10) * 10`` over the user's pending
    candidates; only non-empty bands are returned, sorted descending.
    """
    from sqlalchemy.orm import aliased

    RecordA = aliased(HealthRecord)
    result = await db.execute(
        select(DedupCandidate.similarity_score)
        .join(RecordA, DedupCandidate.record_a_id == RecordA.id)
        .where(
            RecordA.user_id == user_id,
            DedupCandidate.status == "pending",
        )
    )
    scores = result.scalars().all()

    band_counts: dict[int, int] = {}
    for score in scores:
        # Round to integer percent first (same as the /candidates filter and
        # /resolve-bulk), so a 0.7999999999999999 ("80%") match buckets to 80,
        # not 70. Comparing the raw float would split the bands inconsistently.
        band = (round(score * 100) // 10) * 10
        band_counts[band] = band_counts.get(band, 0) + 1

    bands = [
        {"band": band, "count": count}
        for band, count in sorted(band_counts.items(), reverse=True)
    ]
    total = sum(band_counts.values())

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.candidates_summary",
        resource_type="dedup",
        ip_address=request.client.host if request.client else None,
        details={"total": total, "bands": len(bands)},
    )

    return {"bands": bands, "total": total}


@router.post("/merge")
async def merge_records(
    body: MergeRequest,
    request: Request,
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

    # Determine primary and secondary records
    primary_id = body.primary_record_id if body.primary_record_id else candidate.record_a_id
    secondary_id = (
        candidate.record_b_id
        if primary_id == candidate.record_a_id
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
        _apply_merge(secondary, primary_id)

    candidate.status = "merged"
    candidate.resolved_by = user_id
    candidate.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.merge",
        resource_type="dedup",
        resource_id=body.candidate_id,
        ip_address=request.client.host if request.client else None,
        details={"candidate_id": str(body.candidate_id), "primary_record_id": str(primary_id)},
    )

    return {
        "status": "merged",
        "primary_record_id": str(primary_id),
        "archived_record_id": str(secondary_id),
    }


@router.post("/dismiss")
async def dismiss_candidate(
    body: DismissRequest,
    request: Request,
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

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.dismiss",
        resource_type="dedup",
        resource_id=body.candidate_id,
        ip_address=request.client.host if request.client else None,
        details={"candidate_id": str(body.candidate_id)},
    )

    return {"status": "dismissed"}


@router.post("/scan")
async def scan_for_duplicates(
    request: Request,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a duplicate scan for all patient records."""
    from app.services.dedup.detector import detect_duplicates

    result = await db.execute(
        select(Patient).where(Patient.user_id == user_id)
    )
    patients = result.scalars().all()

    total_pending = 0
    total_auto_merged = 0
    for patient in patients:
        outcome = await detect_duplicates(db, user_id, patient.id)
        total_pending += outcome["candidates_found"]
        total_auto_merged += outcome["auto_merged"]

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.scan",
        resource_type="dedup",
        ip_address=request.client.host if request.client else None,
        details={"candidates_found": total_pending, "auto_merged": total_auto_merged},
    )

    return {"auto_merged": total_auto_merged, "candidates_found": total_pending}


@router.post("/resolve-bulk")
async def resolve_bulk(
    body: BulkResolveRequest,
    request: Request,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Bulk merge or dismiss pending candidates by ids or by score band.

    When ``candidate_ids`` is supplied those candidates are acted on (only the
    pending, user-owned ones); otherwise every pending candidate scoring in
    ``[score_min, score_max)`` is acted on. Merge folds ``record_b`` into
    ``record_a``; dismiss marks the pair dismissed. One commit for the batch.
    """
    from sqlalchemy import func
    from sqlalchemy.orm import aliased

    RecordA = aliased(HealthRecord)
    query = (
        select(DedupCandidate)
        .join(RecordA, DedupCandidate.record_a_id == RecordA.id)
        .where(
            RecordA.user_id == user_id,
            DedupCandidate.status == "pending",
        )
    )

    if body.candidate_ids:
        query = query.where(DedupCandidate.id.in_(body.candidate_ids))
    else:
        # Round to integer percent so the score band matches the summary and the
        # /candidates filter exactly (0.7999999999999999 is band 80, not 70).
        if body.score_min is not None:
            query = query.where(
                func.round(DedupCandidate.similarity_score * 100) >= round(body.score_min * 100)
            )
        if body.score_max is not None:
            query = query.where(
                func.round(DedupCandidate.similarity_score * 100) < round(body.score_max * 100)
            )

    result = await db.execute(query)
    candidates = result.scalars().all()

    now = datetime.now(timezone.utc)
    count = 0
    for candidate in candidates:
        if body.action == "merge":
            sec_result = await db.execute(
                select(HealthRecord).where(
                    HealthRecord.id == candidate.record_b_id,
                    HealthRecord.user_id == user_id,
                )
            )
            secondary = sec_result.scalar_one_or_none()
            if secondary is not None:
                _apply_merge(secondary, candidate.record_a_id)
            candidate.status = "merged"
        else:  # dismiss (action validated to merge|dismiss by the schema)
            candidate.status = "dismissed"
        candidate.resolved_by = user_id
        candidate.resolved_at = now
        count += 1

    await db.commit()

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.resolve_bulk",
        resource_type="dedup",
        ip_address=request.client.host if request.client else None,
        details={"action": body.action, "count": count},
    )

    return {"action": body.action, "count": count}


async def _reverse_merge(
    db: AsyncSession,
    candidate: DedupCandidate,
    user_id: UUID,
    now: datetime,
) -> None:
    """Reverse a merged candidate in place (caller commits).

    Restores the archived record (clears ``is_duplicate``/``merged_into_id``)
    and marks the candidate ``dismissed``. Unmerge is a deliberate "these are
    NOT duplicates" override, so the pair must not boomerang back into the
    pending review queue — it is dismissed, not returned to pending. The
    reversal stays attributed to the acting user.

    Args:
        db: Active async session (not committed here).
        candidate: The merged candidate being reversed.
        user_id: The owner performing the reversal.
        now: Timestamp to record as ``resolved_at``.
    """
    rec_result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id.in_([candidate.record_a_id, candidate.record_b_id]),
            HealthRecord.user_id == user_id,
        )
    )
    for record in rec_result.scalars().all():
        if record.is_duplicate or record.merged_into_id is not None:
            record.is_duplicate = False
            record.merged_into_id = None

    candidate.status = "dismissed"
    candidate.resolved_by = user_id
    candidate.resolved_at = now
    candidate.auto_resolved = False


@router.get("/merges")
async def list_merges(
    request: Request,
    source: str | None = None,
    record_type: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List resolved (``status=="merged"``) candidates for the merges pane.

    Each item splits the pair into the surviving record and the archived
    duplicate (flagged ``is_duplicate``/``merged_into_id``). Optional filters:
    ``source`` (``auto``/``manual`` → ``auto_resolved``), ``record_type`` (both
    records share it), and ``search`` (case-insensitive on either record's
    ``display_text``). ``counts`` reports the auto/manual split over the
    ``record_type``+``search`` scope but ignores ``source`` so the chips stay
    stable; ``total`` reflects all filters including ``source``.
    """
    from sqlalchemy import func, or_
    from sqlalchemy.orm import aliased

    RecordA = aliased(HealthRecord)
    RecordB = aliased(HealthRecord)

    # Conditions shared by counts (source-agnostic) and the item/total queries.
    conditions = [
        RecordA.user_id == user_id,
        DedupCandidate.status == "merged",
    ]
    if record_type:
        # Survivor and archived share record_type, so filtering record_a covers both.
        conditions.append(RecordA.record_type == record_type)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(RecordA.display_text.ilike(pattern), RecordB.display_text.ilike(pattern))
        )

    def _joined(stmt):
        # Anchor the left side to DedupCandidate explicitly — a bare
        # ``select(func.count())`` has no FROM entity for the join to infer.
        return (
            stmt.select_from(DedupCandidate)
            .join(RecordA, DedupCandidate.record_a_id == RecordA.id)
            .join(RecordB, DedupCandidate.record_b_id == RecordB.id)
        )

    # counts: auto/manual split over the filtered set, IGNORING source.
    counts_result = await db.execute(
        _joined(select(DedupCandidate.auto_resolved, func.count()))
        .where(*conditions)
        .group_by(DedupCandidate.auto_resolved)
    )
    counts = {"auto": 0, "manual": 0}
    for auto_resolved, count in counts_result.all():
        counts["auto" if auto_resolved else "manual"] = count

    # Apply the source filter only to the item/total queries.
    item_conditions = list(conditions)
    if source == "auto":
        item_conditions.append(DedupCandidate.auto_resolved.is_(True))
    elif source == "manual":
        item_conditions.append(DedupCandidate.auto_resolved.is_(False))

    total_result = await db.execute(
        _joined(select(func.count())).where(*item_conditions)
    )
    total = total_result.scalar() or 0

    items: list[dict] = []
    if total:
        offset = (page - 1) * limit
        rows = (
            await db.execute(
                _joined(select(DedupCandidate, RecordA, RecordB))
                .where(*item_conditions)
                .order_by(DedupCandidate.resolved_at.desc().nullslast())
                .offset(offset)
                .limit(limit)
            )
        ).all()

        for candidate, record_a, record_b in rows:
            if record_a.is_duplicate or record_a.merged_into_id is not None:
                archived, survivor = record_a, record_b
            else:
                archived, survivor = record_b, record_a
            items.append({
                "candidate_id": str(candidate.id),
                "similarity_score": candidate.similarity_score,
                "match_reasons": candidate.match_reasons,
                "auto_resolved": candidate.auto_resolved,
                "resolved_at": candidate.resolved_at.isoformat()
                if candidate.resolved_at
                else None,
                "survivor": _record_summary(survivor),
                "archived": _record_summary(archived),
            })

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.list_merges",
        resource_type="dedup",
        ip_address=request.client.host if request.client else None,
        details={"total": total, "page": page},
    )

    return {"items": items, "total": total, "counts": counts}


@router.post("/undo-merge")
async def undo_merge_candidate(
    body: UndoMergeRequest,
    request: Request,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Reverse a merged candidate, restoring the archived record to active.

    Loads the user-owned merged candidate, restores whichever record was
    archived, and dismisses the pair (so it does not return to the pending
    review queue). See ``_reverse_merge``.
    """
    from sqlalchemy.orm import aliased

    RecordA = aliased(HealthRecord)
    result = await db.execute(
        select(DedupCandidate)
        .join(RecordA, DedupCandidate.record_a_id == RecordA.id)
        .where(
            DedupCandidate.id == body.candidate_id,
            RecordA.user_id == user_id,
            DedupCandidate.status == "merged",
        )
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    await _reverse_merge(db, candidate, user_id, datetime.now(timezone.utc))
    await db.commit()

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.undo_merge",
        resource_type="dedup",
        resource_id=body.candidate_id,
        ip_address=request.client.host if request.client else None,
        details={"candidate_id": str(body.candidate_id)},
    )

    return {"status": "dismissed"}


@router.post("/undo-bulk")
async def undo_bulk(
    body: UndoBulkRequest,
    request: Request,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-reverse merged candidates by id in a single commit.

    Only ``status=="merged"`` candidates the user owns are reversed; any other
    id (pending, dismissed, not owned, or unknown) is silently skipped so one
    bad id never fails the batch. Returns the number actually reversed.
    """
    from sqlalchemy.orm import aliased

    RecordA = aliased(HealthRecord)
    result = await db.execute(
        select(DedupCandidate)
        .join(RecordA, DedupCandidate.record_a_id == RecordA.id)
        .where(
            DedupCandidate.id.in_(body.candidate_ids),
            RecordA.user_id == user_id,
            DedupCandidate.status == "merged",
        )
    )
    candidates = result.scalars().all()

    now = datetime.now(timezone.utc)
    for candidate in candidates:
        await _reverse_merge(db, candidate, user_id, now)
    count = len(candidates)
    await db.commit()

    await log_audit_event(
        db,
        user_id=user_id,
        action="dedup.undo_bulk",
        resource_type="dedup",
        ip_address=request.client.host if request.client else None,
        details={"count": count},
    )

    return {"count": count}
