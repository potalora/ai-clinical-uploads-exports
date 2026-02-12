from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deduplication import DedupCandidate
from app.models.record import HealthRecord

logger = logging.getLogger(__name__)


async def detect_duplicates(
    db: AsyncSession,
    user_id: UUID,
    patient_id: UUID,
) -> int:
    """Scan for duplicate records and create dedup candidates.

    Returns the number of new candidates found.
    """
    # Fetch all active records for patient
    result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.user_id == user_id,
            HealthRecord.patient_id == patient_id,
            HealthRecord.deleted_at.is_(None),
            HealthRecord.is_duplicate.is_(False),
        )
        .order_by(HealthRecord.effective_date.asc().nullslast())
    )
    records = result.scalars().all()

    if len(records) < 2:
        return 0

    # Group records by type for comparison
    by_type: dict[str, list[HealthRecord]] = {}
    for r in records:
        by_type.setdefault(r.record_type, []).append(r)

    candidates_found = 0

    for rtype, recs in by_type.items():
        for i, a in enumerate(recs):
            for b in recs[i + 1 :]:
                score, reasons = _compare_records(a, b)
                if score >= 0.7:
                    # Check if candidate already exists
                    existing = await db.execute(
                        select(DedupCandidate).where(
                            DedupCandidate.record_a_id == a.id,
                            DedupCandidate.record_b_id == b.id,
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    candidate = DedupCandidate(
                        id=uuid4(),
                        record_a_id=a.id,
                        record_b_id=b.id,
                        similarity_score=score,
                        match_reasons=reasons,
                    )
                    db.add(candidate)
                    candidates_found += 1

    if candidates_found:
        await db.commit()

    logger.info("Found %d dedup candidates for patient %s", candidates_found, patient_id)
    return candidates_found


def _compare_records(a: HealthRecord, b: HealthRecord) -> tuple[float, dict]:
    """Compare two records for similarity.

    Returns (score, reasons) where score is 0-1.
    """
    score = 0.0
    reasons = {}

    # Same code = strong match
    if a.code_value and b.code_value and a.code_value == b.code_value:
        score += 0.4
        reasons["code_match"] = True

    # Same display text
    if a.display_text and b.display_text:
        if a.display_text.lower() == b.display_text.lower():
            score += 0.3
            reasons["text_exact_match"] = True
        elif _fuzzy_match(a.display_text, b.display_text) > 0.8:
            score += 0.2
            reasons["text_fuzzy_match"] = True

    # Same date (within 24h)
    if a.effective_date and b.effective_date:
        delta = abs((a.effective_date - b.effective_date).total_seconds())
        if delta < 86400:  # 24 hours
            score += 0.2
            reasons["date_proximity"] = True

    # Same status
    if a.status and b.status and a.status == b.status:
        score += 0.1
        reasons["status_match"] = True

    # Cross-source is a strong signal
    if a.source_format != b.source_format:
        score += 0.1
        reasons["cross_source"] = True

    return min(score, 1.0), reasons


def _fuzzy_match(a: str, b: str) -> float:
    """Simple fuzzy string matching using character overlap."""
    a_lower = a.lower()
    b_lower = b.lower()
    if a_lower == b_lower:
        return 1.0

    # Use set intersection for quick similarity
    set_a = set(a_lower.split())
    set_b = set(b_lower.split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0
