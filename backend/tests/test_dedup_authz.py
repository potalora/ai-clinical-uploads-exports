"""Object-level authorization (IDOR) regression for the dedup mutation endpoints.

SEC-AUTHZ-01/-02 / HIPAA AUTH-01: ``POST /dedup/merge`` and ``POST /dedup/dismiss``
loaded the ``DedupCandidate`` by ``id`` with no ownership scoping, letting one user
mutate (and read back the record UUIDs of) another user's dedup-queue state. Every
other dedup endpoint joins through ``record_a``/``record_b`` to the owning user; these
two must do the same and return 404 for a candidate the caller does not own.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deduplication import DedupCandidate
from app.models.record import HealthRecord
from tests.conftest import auth_headers, create_test_patient


async def _create_pending_pair(
    db_session: AsyncSession, user_id: str, patient_id,
) -> tuple[HealthRecord, HealthRecord, DedupCandidate]:
    """Create two records owned by ``user_id`` and a pending dedup candidate."""
    uid = UUID(user_id)
    rec_a = HealthRecord(
        id=uuid4(),
        patient_id=patient_id,
        user_id=uid,
        record_type="medication",
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="fhir_r4",
        display_text="Lisinopril 10 MG Oral Tablet",
        code_value="197361",
        effective_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    rec_b = HealthRecord(
        id=uuid4(),
        patient_id=patient_id,
        user_id=uid,
        record_type="medication",
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="epic_ehi",
        display_text="LISINOPRIL 10MG TAB",
        code_value="197361",
        effective_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    db_session.add_all([rec_a, rec_b])
    await db_session.commit()

    candidate = DedupCandidate(
        id=uuid4(),
        record_a_id=rec_a.id,
        record_b_id=rec_b.id,
        similarity_score=0.92,
        match_reasons={"code_match": True},
        status="pending",
    )
    db_session.add(candidate)
    await db_session.commit()
    await db_session.refresh(rec_a)
    await db_session.refresh(rec_b)
    await db_session.refresh(candidate)
    return rec_a, rec_b, candidate


@pytest.mark.asyncio
async def test_merge_rejects_other_users_candidate(
    client: AsyncClient, db_session: AsyncSession
):
    """User B cannot merge User A's candidate (404, status unchanged)."""
    _headers_a, uid_a = await auth_headers(client, email="authz_merge_a@test.com")
    headers_b, _uid_b = await auth_headers(client, email="authz_merge_b@test.com")

    patient = await create_test_patient(db_session, uid_a)
    _rec_a, _rec_b, candidate = await _create_pending_pair(db_session, uid_a, patient.id)

    resp = await client.post(
        "/api/v1/dedup/merge",
        headers=headers_b,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 404

    await db_session.refresh(candidate)
    assert candidate.status == "pending"
    assert candidate.resolved_by is None
    assert candidate.resolved_at is None


@pytest.mark.asyncio
async def test_dismiss_rejects_other_users_candidate(
    client: AsyncClient, db_session: AsyncSession
):
    """User B cannot dismiss User A's candidate (404, status unchanged)."""
    _headers_a, uid_a = await auth_headers(client, email="authz_dismiss_a@test.com")
    headers_b, _uid_b = await auth_headers(client, email="authz_dismiss_b@test.com")

    patient = await create_test_patient(db_session, uid_a)
    _rec_a, _rec_b, candidate = await _create_pending_pair(db_session, uid_a, patient.id)

    resp = await client.post(
        "/api/v1/dedup/dismiss",
        headers=headers_b,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 404

    await db_session.refresh(candidate)
    assert candidate.status == "pending"
    assert candidate.resolved_by is None
    assert candidate.resolved_at is None


@pytest.mark.asyncio
async def test_merge_owner_still_succeeds(
    client: AsyncClient, db_session: AsyncSession
):
    """The owner can still merge their own candidate (happy path intact)."""
    headers, uid = await auth_headers(client, email="authz_merge_owner@test.com")
    patient = await create_test_patient(db_session, uid)
    rec_a, rec_b, candidate = await _create_pending_pair(db_session, uid, patient.id)

    resp = await client.post(
        "/api/v1/dedup/merge",
        headers=headers,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "merged"
    assert data["primary_record_id"] == str(rec_a.id)
    assert data["archived_record_id"] == str(rec_b.id)

    await db_session.refresh(candidate)
    assert candidate.status == "merged"


@pytest.mark.asyncio
async def test_dismiss_owner_still_succeeds(
    client: AsyncClient, db_session: AsyncSession
):
    """The owner can still dismiss their own candidate (happy path intact)."""
    headers, uid = await auth_headers(client, email="authz_dismiss_owner@test.com")
    patient = await create_test_patient(db_session, uid)
    _rec_a, _rec_b, candidate = await _create_pending_pair(db_session, uid, patient.id)

    resp = await client.post(
        "/api/v1/dedup/dismiss",
        headers=headers,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "dismissed"}

    await db_session.refresh(candidate)
    assert candidate.status == "dismissed"


@pytest.mark.asyncio
async def test_merge_unknown_candidate_returns_404(
    client: AsyncClient, db_session: AsyncSession
):
    """A nonexistent candidate id still returns 404."""
    headers, _uid = await auth_headers(client, email="authz_merge_missing@test.com")
    resp = await client.post(
        "/api/v1/dedup/merge",
        headers=headers,
        json={"candidate_id": str(uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_unknown_candidate_returns_404(
    client: AsyncClient, db_session: AsyncSession
):
    """A nonexistent candidate id still returns 404."""
    headers, _uid = await auth_headers(client, email="authz_dismiss_missing@test.com")
    resp = await client.post(
        "/api/v1/dedup/dismiss",
        headers=headers,
        json={"candidate_id": str(uuid4())},
    )
    assert resp.status_code == 404
