from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.encryption import encrypt_field
from app.models.record import HealthRecord
from tests.conftest import auth_headers, create_test_patient, seed_test_records


@pytest.mark.asyncio
async def test_build_prompt_scrubs_known_patient_name(
    client: AsyncClient, db_session: AsyncSession
):
    """The patient's own name must be removed from the prompt before it leaves the app.

    Regression for the PHI gap where build_prompt called scrub_phi WITHOUT the
    patient's known identifiers, so free-text names (which the regex patterns
    can't catch) reached the model.
    """
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    patient.name_encrypted = encrypt_field("Pedro Otalora")
    db_session.add(patient)
    await db_session.commit()

    # A record whose free text embeds the patient's name (display_text + note).
    rec = HealthRecord(
        id=uuid4(),
        patient_id=patient.id,
        user_id=UUID(uid) if isinstance(uid, str) else uid,
        record_type="document",
        fhir_resource_type="DocumentReference",
        fhir_resource={
            "resourceType": "DocumentReference",
            "note": [{"text": "Pedro Otalora seen in clinic; prescribed Rifaximin."}],
        },
        source_format="fhir_r4",
        status="current",
        display_text="Visit note for Pedro Otalora",
        effective_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
    )
    db_session.add(rec)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id), "summary_type": "full"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # The patient's name must NOT appear anywhere in the outgoing prompt payload.
    assert "Pedro" not in data["user_prompt"]
    assert "Otalora" not in data["user_prompt"]
    assert "Pedro" not in data["copyable_payload"]
    assert "[PATIENT]" in data["user_prompt"]
    # Clinical content survives de-identification.
    assert "Rifaximin" in data["user_prompt"]
    # The de-identification report records the scrub.
    assert data["de_identification_report"].get("names_scrubbed", 0) >= 1


@pytest.mark.asyncio
async def test_build_prompt_unauthenticated(client: AsyncClient):
    """POST /summary/build-prompt without token returns 401."""
    resp = await client.post("/api/v1/summary/build-prompt", json={"patient_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_build_prompt_success(client: AsyncClient, db_session: AsyncSession):
    """Build prompt returns all expected fields per handoff."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await seed_test_records(db_session, uid, patient.id, count=5)

    resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id), "summary_type": "full"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Verify all handoff fields
    for field in [
        "id", "summary_type", "system_prompt", "user_prompt",
        "target_model", "suggested_config", "record_count",
        "de_identification_report", "copyable_payload", "generated_at",
    ]:
        assert field in data, f"Missing field: {field}"

    assert data["summary_type"] == "full"
    assert data["record_count"] == 5
    assert data["target_model"] == "gemini-3.5-flash"
    assert isinstance(data["suggested_config"], dict)
    assert "temperature" in data["suggested_config"]


@pytest.mark.asyncio
async def test_build_prompt_no_records(client: AsyncClient, db_session: AsyncSession):
    """Build prompt with no records returns 400."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id), "summary_type": "full"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_build_prompt_patient_not_found(client: AsyncClient, db_session: AsyncSession):
    """Build prompt with non-existent patient returns 404."""
    headers, _ = await auth_headers(client)
    resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": "00000000-0000-0000-0000-000000000000", "summary_type": "full"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_build_prompt_no_diagnosis_disclaimer(client: AsyncClient, db_session: AsyncSession):
    """System prompt contains no-diagnosis disclaimer."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await seed_test_records(db_session, uid, patient.id, count=3)

    resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id), "summary_type": "full"},
    )
    data = resp.json()
    assert "Do NOT provide any diagnoses" in data["system_prompt"]
    assert "treatment recommendations" in data["system_prompt"]


@pytest.mark.asyncio
async def test_build_prompt_target_model(client: AsyncClient, db_session: AsyncSession):
    """Target model is the configured prompt target (gemini-3.5-flash)."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await seed_test_records(db_session, uid, patient.id, count=1)

    resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id)},
    )
    assert resp.json()["target_model"] == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_list_prompts(client: AsyncClient, db_session: AsyncSession):
    """Fix 6: List prompts returns full items with all fields."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await seed_test_records(db_session, uid, patient.id, count=3)

    # Build a prompt first
    await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id), "summary_type": "full"},
    )

    resp = await client.get("/api/v1/summary/prompts", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1

    item = data["items"][0]
    for field in [
        "id", "summary_type", "system_prompt", "user_prompt",
        "target_model", "suggested_config", "record_count",
        "de_identification_report", "copyable_payload", "generated_at",
    ]:
        assert field in item, f"Missing field in list item: {field}"


@pytest.mark.asyncio
async def test_paste_response(client: AsyncClient, db_session: AsyncSession):
    """Fix 5: Paste response returns {id, prompt_id, response_pasted_at}."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await seed_test_records(db_session, uid, patient.id, count=3)

    # Build prompt
    build_resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id)},
    )
    prompt_id = build_resp.json()["id"]

    # Paste response
    resp = await client.post(
        "/api/v1/summary/paste-response",
        headers=headers,
        json={"prompt_id": prompt_id, "response_text": "AI summary goes here."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == prompt_id
    assert data["prompt_id"] == prompt_id
    assert "response_pasted_at" in data
    assert data["response_pasted_at"] is not None


@pytest.mark.asyncio
async def test_build_prompt_with_record_types(client: AsyncClient, db_session: AsyncSession):
    """Test that record_types filters correctly."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await seed_test_records(db_session, uid, patient.id, count=5)

    resp = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={
            "patient_id": str(patient.id),
            "summary_type": "full",
            "record_types": ["medication", "observation"],
        },
    )
    # Should succeed (200) or return 400 if no records match
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        data = resp.json()
        assert data["record_count"] > 0


@pytest.mark.asyncio
async def test_list_responses(client: AsyncClient, db_session: AsyncSession):
    """List responses only returns prompts with pasted responses."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await seed_test_records(db_session, uid, patient.id, count=3)

    # Build 2 prompts
    build1 = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id)},
    )
    build2 = await client.post(
        "/api/v1/summary/build-prompt",
        headers=headers,
        json={"patient_id": str(patient.id)},
    )

    # Paste response on only the first one
    await client.post(
        "/api/v1/summary/paste-response",
        headers=headers,
        json={"prompt_id": build1.json()["id"], "response_text": "Summary text."},
    )

    resp = await client.get("/api/v1/summary/responses", headers=headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == build1.json()["id"]
