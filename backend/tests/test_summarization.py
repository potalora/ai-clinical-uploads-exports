from __future__ import annotations

import os
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_test_patient, seed_test_records

HAS_API_KEY = bool(os.environ.get("GEMINI_API_KEY"))


# ---------- Unit tests (no API calls) ----------

@pytest.mark.asyncio
async def test_deduped_records_only(client: AsyncClient, db_session: AsyncSession):
    """Verify that duplicate records are excluded from summary."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)
    records = await seed_test_records(db_session, user_id, patient.id, count=5)

    # Mark one as duplicate
    records[0].is_duplicate = True
    await db_session.commit()

    from app.services.ai.summarizer import _fetch_deduped_records

    deduped = await _fetch_deduped_records(db_session, UUID(user_id), patient.id)
    assert len(deduped) == 4  # 5 total - 1 duplicate


@pytest.mark.asyncio
async def test_duplicate_warning_counts(client: AsyncClient, db_session: AsyncSession):
    """Verify duplicate warning math: total - deduped = excluded."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)
    records = await seed_test_records(db_session, user_id, patient.id, count=5)

    # Mark 2 as duplicates
    records[0].is_duplicate = True
    records[1].is_duplicate = True
    await db_session.commit()

    from app.services.ai.summarizer import _count_records

    total = await _count_records(db_session, UUID(user_id), patient.id, deduped_only=False)
    deduped = await _count_records(db_session, UUID(user_id), patient.id, deduped_only=True)

    assert total == 5
    assert deduped == 3
    assert total - deduped == 2


@pytest.mark.asyncio
async def test_phi_scrubbing_before_summary(client: AsyncClient, db_session: AsyncSession):
    """Verify that PHI is scrubbed from record text before summarization."""
    from app.services.ai.phi_scrubber import scrub_phi

    text = "Patient John Doe, SSN 123-45-6789, email john@example.com was seen for follow-up."
    scrubbed, report = scrub_phi(text)

    assert "123-45-6789" not in scrubbed
    assert "john@example.com" not in scrubbed
    assert "[SSN]" in scrubbed
    assert "[EMAIL]" in scrubbed


@pytest.mark.asyncio
async def test_generate_endpoint_no_api_key(client: AsyncClient, db_session: AsyncSession):
    """Verify generate returns error when API key is not configured."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)
    await seed_test_records(db_session, user_id, patient.id, count=3)

    # Temporarily clear the API key
    from app.config import settings
    original_key = settings.gemini_api_key
    settings.gemini_api_key = ""
    try:
        resp = await client.post(
            "/api/v1/summary/generate",
            json={"patient_id": str(patient.id), "summary_type": "full", "output_format": "natural_language"},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "GEMINI_API_KEY" in resp.json()["detail"]
    finally:
        settings.gemini_api_key = original_key


@pytest.mark.asyncio
async def test_generate_endpoint_no_records(client: AsyncClient, db_session: AsyncSession):
    """Verify generate returns error when no records exist."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)

    from app.config import settings
    original_key = settings.gemini_api_key
    settings.gemini_api_key = "test-key"
    try:
        resp = await client.post(
            "/api/v1/summary/generate",
            json={"patient_id": str(patient.id), "summary_type": "full", "output_format": "natural_language"},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "No records" in resp.json()["detail"]
    finally:
        settings.gemini_api_key = original_key


@pytest.mark.asyncio
async def test_generate_patient_not_found(client: AsyncClient, db_session: AsyncSession):
    """Verify generate returns 404 for non-existent patient."""
    headers, user_id = await auth_headers(client)

    resp = await client.post(
        "/api/v1/summary/generate",
        json={
            "patient_id": "00000000-0000-0000-0000-000000000000",
            "summary_type": "full",
            "output_format": "natural_language",
        },
        headers=headers,
    )
    assert resp.status_code == 404


# ---------- Integration tests with Gemini API (slow) ----------

@pytest.mark.slow
@pytest.mark.skipif(not HAS_API_KEY, reason="Requires GEMINI_API_KEY")
@pytest.mark.asyncio
async def test_generate_natural_language(client: AsyncClient, db_session: AsyncSession):
    """Generate NL summary via Gemini and verify response."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)
    await seed_test_records(db_session, user_id, patient.id, count=5)

    resp = await client.post(
        "/api/v1/summary/generate",
        json={
            "patient_id": str(patient.id),
            "summary_type": "full",
            "output_format": "natural_language",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["natural_language"] is not None
    assert len(data["natural_language"]) > 50
    assert data["record_count"] == 5
    assert data["model_used"] is not None


@pytest.mark.slow
@pytest.mark.skipif(not HAS_API_KEY, reason="Requires GEMINI_API_KEY")
@pytest.mark.asyncio
async def test_generate_json_format(client: AsyncClient, db_session: AsyncSession):
    """Generate JSON summary via Gemini and verify valid JSON returned."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)
    await seed_test_records(db_session, user_id, patient.id, count=3)

    resp = await client.post(
        "/api/v1/summary/generate",
        json={
            "patient_id": str(patient.id),
            "summary_type": "full",
            "output_format": "json",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["json_data"] is not None
    assert isinstance(data["json_data"], dict)


@pytest.mark.slow
@pytest.mark.skipif(not HAS_API_KEY, reason="Requires GEMINI_API_KEY")
@pytest.mark.asyncio
async def test_generate_both_formats(client: AsyncClient, db_session: AsyncSession):
    """Generate both NL + JSON summary via Gemini."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)
    await seed_test_records(db_session, user_id, patient.id, count=3)

    resp = await client.post(
        "/api/v1/summary/generate",
        json={
            "patient_id": str(patient.id),
            "summary_type": "full",
            "output_format": "both",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    # At least one of the two should be populated
    assert data["natural_language"] is not None or data["json_data"] is not None
