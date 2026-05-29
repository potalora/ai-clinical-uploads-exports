from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.record import HealthRecord
from app.models.record_version import RecordVersion
from app.services.ingestion.idempotent_inserter import idempotent_insert_records
from tests.conftest import auth_headers, create_test_patient


def _cond(patient, rid: str, code: str = "active") -> dict:
    """Build a minimal Condition record dict for a given patient."""
    return {
        "user_id": patient.user_id,
        "patient_id": patient.id,
        "source_file_id": None,
        "record_type": "condition",
        "fhir_resource_type": "Condition",
        "fhir_resource": {
            "resourceType": "Condition",
            "id": rid,
            "clinicalStatus": {"coding": [{"code": code}]},
        },
        "source_format": "fhir_r4",
        "display_text": f"Cond {rid}",
        "status": code,
    }


@pytest.mark.asyncio
async def test_reingesting_same_extract_converges(client, db_session):
    """Ingesting the identical 5-record batch twice produces no duplicates."""
    _, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    batch = [_cond(patient, f"c{i}") for i in range(5)]

    # First ingest — everything is new.
    s1 = await idempotent_insert_records(db_session, batch)
    await db_session.commit()

    assert s1["inserted"] == 5
    assert s1["unchanged"] == 0
    assert s1["updated"] == 0
    assert s1["inserted"] == len(s1["inserted_records"])

    # Second ingest with the IDENTICAL batch — nothing changes.
    s2 = await idempotent_insert_records(db_session, batch)
    await db_session.commit()

    assert s2["inserted"] == 0
    assert s2["unchanged"] == 5
    assert s2["updated"] == 0

    # DB must contain exactly 5 rows — no duplication.
    count = (
        await db_session.execute(
            select(func.count()).select_from(HealthRecord).where(
                HealthRecord.patient_id == patient.id
            )
        )
    ).scalar_one()
    assert count == 5


@pytest.mark.asyncio
async def test_reingest_with_one_correction(client, db_session):
    """Correcting a single record in the cumulative batch yields exactly one update."""
    _, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    # Initial ingest of 5 records, all "active".
    initial_batch = [_cond(patient, f"c{i}") for i in range(5)]
    s1 = await idempotent_insert_records(db_session, initial_batch)
    await db_session.commit()

    assert s1["inserted"] == 5
    assert s1["inserted"] == len(s1["inserted_records"])

    # Cumulative batch: c0 flipped to "resolved", c1-c4 identical.
    corrected_batch = [_cond(patient, "c0", "resolved")] + [
        _cond(patient, f"c{i}") for i in range(1, 5)
    ]
    s2 = await idempotent_insert_records(db_session, corrected_batch)
    await db_session.commit()

    assert s2["inserted"] == 0
    assert s2["updated"] == 1
    assert s2["unchanged"] == 4

    # c0 must be at version 2 with the corrected content.
    c0_row = (
        await db_session.execute(
            select(HealthRecord).where(
                HealthRecord.patient_id == patient.id,
                HealthRecord.external_id == "Condition/c0",
            )
        )
    ).scalars().one()

    assert c0_row.version == 2
    assert c0_row.fhir_resource["clinicalStatus"]["coding"][0]["code"] == "resolved"

    # Exactly one RecordVersion must exist (the prior "active" snapshot for c0).
    versions = (
        await db_session.execute(
            select(RecordVersion).join(
                HealthRecord, RecordVersion.record_id == HealthRecord.id
            ).where(
                HealthRecord.patient_id == patient.id
            )
        )
    ).scalars().all()

    assert len(versions) == 1
    assert versions[0].record_id == c0_row.id
    assert versions[0].version == 1
    assert versions[0].fhir_resource["clinicalStatus"]["coding"][0]["code"] == "active"
