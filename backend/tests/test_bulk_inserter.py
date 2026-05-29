from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.record import HealthRecord
from app.services.ingestion.bulk_inserter import bulk_insert_records
from tests.conftest import auth_headers, create_test_patient


@pytest.mark.asyncio
async def test_bulk_insert_empty_returns_zero(db_session):
    """bulk_insert_records with no records returns 0 without touching the DB."""
    result = await bulk_insert_records(db_session, [])
    assert result == 0


@pytest.mark.asyncio
async def test_bulk_insert_count_and_persistence(client, db_session):
    """bulk_insert_records inserts all records and persists them to the DB."""
    _, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    records = [
        {
            "user_id": patient.user_id,
            "patient_id": patient.id,
            "source_file_id": None,
            "record_type": "condition",
            "fhir_resource_type": "Condition",
            "fhir_resource": {"resourceType": "Condition", "id": f"b{i}"},
            "source_format": "fhir_r4",
            "display_text": f"C{i}",
        }
        for i in range(3)
    ]

    inserted = await bulk_insert_records(db_session, records)
    await db_session.commit()

    assert inserted == 3

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(HealthRecord)
            .where(HealthRecord.patient_id == patient.id)
        )
    ).scalar_one()
    assert count == 3
