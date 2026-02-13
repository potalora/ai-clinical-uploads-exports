from __future__ import annotations

import io
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_test_patient

HAS_API_KEY = bool(os.environ.get("GEMINI_API_KEY"))

# Patch the background task to avoid event loop conflicts with the test DB session.
# The _process_unstructured function creates its own DB session via async_session_factory
# which uses the production engine — incompatible with the test session override.
PATCH_BG_TASK = patch(
    "app.api.upload._process_unstructured",
    new_callable=AsyncMock,
)


@pytest.mark.asyncio
async def test_upload_rtf_creates_record(client: AsyncClient, db_session: AsyncSession):
    """Upload an RTF file to the unstructured endpoint."""
    headers, user_id = await auth_headers(client)

    rtf_content = rb"""{\rtf1\ansi\deff0 Patient visit note. Assessment: Hypertension. Plan: Continue medication.}"""

    with PATCH_BG_TASK:
        resp = await client.post(
            "/api/v1/upload/unstructured",
            files={"file": ("note.rtf", io.BytesIO(rtf_content), "application/rtf")},
            headers=headers,
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["upload_id"]
    assert data["status"] == "processing"
    assert data["file_type"] == "rtf"


@pytest.mark.asyncio
async def test_reject_unsupported_file_type(client: AsyncClient, db_session: AsyncSession):
    """Verify .doc files are rejected with 400."""
    headers, user_id = await auth_headers(client)

    resp = await client.post(
        "/api/v1/upload/unstructured",
        files={"file": ("doc.doc", io.BytesIO(b"content"), "application/msword")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reject_txt_file(client: AsyncClient, db_session: AsyncSession):
    """Verify .txt files are rejected."""
    headers, user_id = await auth_headers(client)

    resp = await client.post(
        "/api/v1/upload/unstructured",
        files={"file": ("notes.txt", io.BytesIO(b"plain text"), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_extraction_results_endpoint_not_found(client: AsyncClient, db_session: AsyncSession):
    """Verify 404 for non-existent upload."""
    headers, user_id = await auth_headers(client)

    resp = await client.get(
        "/api/v1/upload/00000000-0000-0000-0000-000000000000/extraction",
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_extraction_results_for_uploaded_file(client: AsyncClient, db_session: AsyncSession):
    """Upload RTF, then check extraction endpoint returns valid response."""
    headers, user_id = await auth_headers(client)

    rtf_content = rb"""{\rtf1\ansi Patient has diabetes and takes Metformin.}"""
    with PATCH_BG_TASK:
        upload_resp = await client.post(
            "/api/v1/upload/unstructured",
            files={"file": ("note.rtf", io.BytesIO(rtf_content), "application/rtf")},
            headers=headers,
        )
    upload_id = upload_resp.json()["upload_id"]

    # Background task is mocked, so status will be "processing"
    resp = await client.get(
        f"/api/v1/upload/{upload_id}/extraction",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["upload_id"] == upload_id
    assert data["status"] in ("processing", "awaiting_confirmation", "completed", "failed")


@pytest.mark.asyncio
async def test_confirm_extraction_missing_patient(client: AsyncClient, db_session: AsyncSession):
    """Verify confirmation fails without patient_id."""
    headers, user_id = await auth_headers(client)

    rtf_content = rb"""{\rtf1\ansi Test note.}"""
    with PATCH_BG_TASK:
        upload_resp = await client.post(
            "/api/v1/upload/unstructured",
            files={"file": ("note.rtf", io.BytesIO(rtf_content), "application/rtf")},
            headers=headers,
        )
    upload_id = upload_resp.json()["upload_id"]

    resp = await client.post(
        f"/api/v1/upload/{upload_id}/confirm-extraction",
        json={"confirmed_entities": [], "patient_id": ""},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_confirm_extraction_creates_records(client: AsyncClient, db_session: AsyncSession):
    """Confirm extracted entities and verify HealthRecords are created."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)

    rtf_content = rb"""{\rtf1\ansi Test note.}"""
    with PATCH_BG_TASK:
        upload_resp = await client.post(
            "/api/v1/upload/unstructured",
            files={"file": ("note.rtf", io.BytesIO(rtf_content), "application/rtf")},
            headers=headers,
        )
    upload_id = upload_resp.json()["upload_id"]

    # Manually confirm with synthetic entities
    resp = await client.post(
        f"/api/v1/upload/{upload_id}/confirm-extraction",
        json={
            "confirmed_entities": [
                {
                    "entity_class": "condition",
                    "text": "Hypertension",
                    "attributes": {"status": "active"},
                    "confidence": 0.85,
                },
                {
                    "entity_class": "medication",
                    "text": "Lisinopril",
                    "attributes": {"medication_group": "Lisinopril"},
                    "confidence": 0.9,
                },
                {
                    "entity_class": "dosage",
                    "text": "10mg",
                    "attributes": {},
                    "confidence": 0.8,
                },
            ],
            "patient_id": str(patient.id),
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    # dosage should be skipped (non-storable), so 2 records
    assert data["records_created"] == 2
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_upload_pdf_accepted(client: AsyncClient, db_session: AsyncSession):
    """Verify PDF files are accepted by the unstructured endpoint."""
    headers, user_id = await auth_headers(client)

    # Minimal PDF-like content (won't actually parse but tests routing)
    with PATCH_BG_TASK:
        resp = await client.post(
            "/api/v1/upload/unstructured",
            files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["file_type"] == "pdf"
