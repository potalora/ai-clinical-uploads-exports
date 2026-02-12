from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_authenticated_user_id
from app.models.record import HealthRecord
from app.schemas.timeline import TimelineEvent, TimelineResponse, TimelineStats

router = APIRouter(prefix="/timeline", tags=["timeline"])


@router.get("", response_model=TimelineResponse)
async def get_timeline(
    record_type: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    """Timeline data ordered by date, filterable by type."""
    query = select(HealthRecord).where(
        HealthRecord.user_id == user_id,
        HealthRecord.deleted_at.is_(None),
        HealthRecord.is_duplicate.is_(False),
        HealthRecord.effective_date.isnot(None),
    )

    if record_type:
        query = query.where(HealthRecord.record_type == record_type)

    query = query.order_by(HealthRecord.effective_date.desc()).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()

    events = [
        TimelineEvent(
            id=r.id,
            record_type=r.record_type,
            display_text=r.display_text,
            effective_date=r.effective_date,
            code_display=r.code_display,
            category=r.category,
        )
        for r in records
    ]

    return TimelineResponse(events=events, total=len(events))


@router.get("/stats", response_model=TimelineStats)
async def get_timeline_stats(
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
) -> TimelineStats:
    """Aggregated stats for dashboard."""
    base = select(HealthRecord).where(
        HealthRecord.user_id == user_id,
        HealthRecord.deleted_at.is_(None),
        HealthRecord.is_duplicate.is_(False),
    )

    # Total count
    total_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = total_result.scalar() or 0

    # Count by type
    type_result = await db.execute(
        select(HealthRecord.record_type, func.count())
        .where(
            HealthRecord.user_id == user_id,
            HealthRecord.deleted_at.is_(None),
            HealthRecord.is_duplicate.is_(False),
        )
        .group_by(HealthRecord.record_type)
    )
    records_by_type = {row[0]: row[1] for row in type_result.all()}

    # Date range
    date_result = await db.execute(
        select(
            func.min(HealthRecord.effective_date),
            func.max(HealthRecord.effective_date),
        ).where(
            HealthRecord.user_id == user_id,
            HealthRecord.deleted_at.is_(None),
            HealthRecord.effective_date.isnot(None),
        )
    )
    date_row = date_result.one()

    return TimelineStats(
        total_records=total,
        records_by_type=records_by_type,
        date_range_start=date_row[0],
        date_range_end=date_row[1],
    )
