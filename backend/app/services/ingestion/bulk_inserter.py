from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import HealthRecord

logger = logging.getLogger(__name__)


async def bulk_insert_records(
    db: AsyncSession,
    records: list[dict[str, Any]],
) -> int:
    """Insert a batch of mapped records into the health_records table.

    Returns the number of records inserted.
    """
    if not records:
        return 0

    objects = []
    for rec in records:
        obj = HealthRecord(
            id=uuid.uuid4(),
            patient_id=rec["patient_id"],
            user_id=rec["user_id"],
            record_type=rec["record_type"],
            fhir_resource_type=rec["fhir_resource_type"],
            fhir_resource=rec["fhir_resource"],
            source_format=rec["source_format"],
            source_file_id=rec.get("source_file_id"),
            effective_date=rec.get("effective_date"),
            effective_date_end=rec.get("effective_date_end"),
            status=rec.get("status"),
            category=rec.get("category"),
            code_system=rec.get("code_system"),
            code_value=rec.get("code_value"),
            code_display=rec.get("code_display"),
            display_text=rec["display_text"],
            confidence_score=rec.get("confidence_score"),
            ai_extracted=rec.get("ai_extracted", False),
        )
        objects.append(obj)

    db.add_all(objects)
    logger.debug("Bulk inserted %d records", len(objects))
    return len(objects)
