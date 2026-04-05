from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deduplication import DedupCandidate
from app.models.record import HealthRecord
from app.models.uploaded_file import UploadedFile
from tests.conftest import auth_headers, create_test_patient


async def _create_upload_with_candidates(
    db: AsyncSession, user_id, patient_id, *, auto_merged: int = 0, pending: int = 0
) -> tuple:
    """Helper: create an upload with dedup candidates."""
    uid = UUID(user_id) if isinstance(user_id, str) else user_id

    upload = UploadedFile(
        id=uuid4(),
        user_id=uid,
        filename="test_export.json",
        mime_type="application/json",
        file_size_bytes=1000,
        file_hash="abc123",
        storage_path="/tmp/test.json",
        ingestion_status="awaiting_review" if pending else "completed_with_merges",
        dedup_summary={
            "total_candidates": auto_merged + pending,
            "auto_merged": auto_merged,
            "needs_review": pending,
            "dismissed": 0,
            "by_type": {"medication": auto_merged + pending},
        },
    )
    db.add(upload)
    await db.flush()

    candidates = []
    for i in range(auto_merged + pending):
        rec_a = HealthRecord(
            id=uuid4(),
            patient_id=patient_id,
            user_id=uid,
            record_type="medication",
            fhir_resource_type="MedicationRequest",
            fhir_resource={
                "resourceType": "MedicationRequest",
                "medicationCodeableConcept": {"text": f"Med A{i}"},
            },
            source_format="fhir_r4",
            display_text=f"Med A{i}",
            source_file_id=None,
        )
        rec_b = HealthRecord(
            id=uuid4(),
            patient_id=patient_id,
            user_id=uid,
            record_type="medication",
            fhir_resource_type="MedicationRequest",
            fhir_resource={
                "resourceType": "MedicationRequest",
                "medicationCodeableConcept": {"text": f"Med B{i}"},
            },
            source_format="fhir_r4",
            display_text=f"Med B{i}",
            source_file_id=upload.id,
        )
        db.add(rec_a)
        db.add(rec_b)
        await db.flush()

        is_auto = i < auto_merged
        candidate = DedupCandidate(
            id=uuid4(),
            record_a_id=rec_a.id,
            record_b_id=rec_b.id,
            similarity_score=0.98 if is_auto else 0.72,
            match_reasons={"code_match": True},
            status="merged" if is_auto else "pending",
            source_upload_id=upload.id,
            auto_resolved=is_auto,
            llm_classification="duplicate" if is_auto else "update",
            llm_confidence=0.95 if is_auto else 0.85,
            llm_explanation="Test explanation",
            resolved_at=datetime.now(timezone.utc) if is_auto else None,
        )
        if is_auto:
            rec_b.is_duplicate = True
            rec_b.merged_into_id = rec_a.id
        db.add(candidate)
        candidates.append(candidate)

    await db.flush()
    return upload, candidates


@pytest.mark.asyncio
async def test_review_unauthenticated(client: AsyncClient):
    """GET /upload/<id>/review without token returns 401."""
    resp = await client.get(f"/api/v1/upload/{uuid4()}/review")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_not_found(client: AsyncClient, db_session: AsyncSession):
    """GET /upload/<id>/review for unknown upload returns 404."""
    headers, _ = await auth_headers(client, email="review_notfound@test.com")
    resp = await client.get(f"/api/v1/upload/{uuid4()}/review", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_review_returns_grouped_candidates(
    client: AsyncClient, db_session: AsyncSession
):
    """Review endpoint groups candidates into auto_merged and needs_review."""
    headers, uid = await auth_headers(client, email="review_grouped@test.com")
    patient = await create_test_patient(db_session, uid)

    upload, candidates = await _create_upload_with_candidates(
        db_session, uid, patient.id, auto_merged=2, pending=1
    )

    resp = await client.get(f"/api/v1/upload/{upload.id}/review", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["upload"]["status"] == "awaiting_review"
    assert len(data["auto_merged"]) == 2
    assert "medication" in data["needs_review"]
    assert len(data["needs_review"]["medication"]) == 1


@pytest.mark.asyncio
async def test_resolve_merge(client: AsyncClient, db_session: AsyncSession):
    """Resolving a pending candidate with action=merge marks it merged."""
    headers, uid = await auth_headers(client, email="review_merge@test.com")
    patient = await create_test_patient(db_session, uid)

    upload, candidates = await _create_upload_with_candidates(
        db_session, uid, patient.id, pending=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/resolve",
        headers=headers,
        json={
            "resolutions": [
                {"candidate_id": str(candidates[0].id), "action": "merge"}
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] == 1
    assert data["remaining"] == 0


@pytest.mark.asyncio
async def test_resolve_dismiss(client: AsyncClient, db_session: AsyncSession):
    """Resolving a pending candidate with action=dismiss marks it dismissed."""
    headers, uid = await auth_headers(client, email="review_dismiss@test.com")
    patient = await create_test_patient(db_session, uid)

    upload, candidates = await _create_upload_with_candidates(
        db_session, uid, patient.id, pending=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/resolve",
        headers=headers,
        json={
            "resolutions": [
                {"candidate_id": str(candidates[0].id), "action": "dismiss"}
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] == 1


@pytest.mark.asyncio
async def test_undo_merge(client: AsyncClient, db_session: AsyncSession):
    """Undoing an auto-merged candidate restores pending status."""
    headers, uid = await auth_headers(client, email="review_undo@test.com")
    patient = await create_test_patient(db_session, uid)

    upload, candidates = await _create_upload_with_candidates(
        db_session, uid, patient.id, auto_merged=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/undo-merge",
        headers=headers,
        json={"candidate_id": str(candidates[0].id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "undone"


@pytest.mark.asyncio
async def test_undo_merge_not_merged_returns_400(
    client: AsyncClient, db_session: AsyncSession
):
    """Attempting to undo a candidate that is not merged returns 400."""
    headers, uid = await auth_headers(client, email="review_undo400@test.com")
    patient = await create_test_patient(db_session, uid)

    upload, candidates = await _create_upload_with_candidates(
        db_session, uid, patient.id, pending=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/undo-merge",
        headers=headers,
        json={"candidate_id": str(candidates[0].id)},
    )
    assert resp.status_code == 400
