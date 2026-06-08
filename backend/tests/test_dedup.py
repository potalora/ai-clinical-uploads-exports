from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deduplication import DedupCandidate
from app.models.record import HealthRecord
from tests.conftest import auth_headers, create_test_patient


async def _create_duplicate_pair(
    db_session: AsyncSession, user_id: str, patient_id,
) -> tuple[HealthRecord, HealthRecord, DedupCandidate]:
    """Create two similar records and a dedup candidate."""
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
        match_reasons={"code_match": True, "date_proximity": True},
        status="pending",
    )
    db_session.add(candidate)
    await db_session.commit()
    await db_session.refresh(rec_a)
    await db_session.refresh(rec_b)
    await db_session.refresh(candidate)
    return rec_a, rec_b, candidate


@pytest.mark.asyncio
async def test_candidates_unauthenticated(client: AsyncClient):
    """GET /dedup/candidates without token returns 401."""
    resp = await client.get("/api/v1/dedup/candidates")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_candidates_empty(client: AsyncClient, db_session: AsyncSession):
    """GET /dedup/candidates with no data returns empty."""
    headers, _ = await auth_headers(client)
    resp = await client.get("/api/v1/dedup/candidates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_candidates_with_data(client: AsyncClient, db_session: AsyncSession):
    """Candidates include record_a and record_b objects."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, _, candidate = await _create_duplicate_pair(db_session, uid, patient.id)

    resp = await client.get("/api/v1/dedup/candidates", headers=headers)
    data = resp.json()
    assert data["total"] >= 1

    item = data["items"][0]
    assert "record_a" in item
    assert "record_b" in item
    assert item["record_a"]["display_text"] == "Lisinopril 10 MG Oral Tablet"
    assert item["record_b"]["display_text"] == "LISINOPRIL 10MG TAB"
    assert item["similarity_score"] == 0.92


@pytest.mark.asyncio
async def test_merge_without_primary(client: AsyncClient, db_session: AsyncSession):
    """Fix 1 & 2: Merge with only candidate_id defaults record_a as primary."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    rec_a, rec_b, candidate = await _create_duplicate_pair(db_session, uid, patient.id)

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


@pytest.mark.asyncio
async def test_merge_with_primary(client: AsyncClient, db_session: AsyncSession):
    """Merge with explicit primary_record_id."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    rec_a, rec_b, candidate = await _create_duplicate_pair(db_session, uid, patient.id)

    resp = await client.post(
        "/api/v1/dedup/merge",
        headers=headers,
        json={"candidate_id": str(candidate.id), "primary_record_id": str(rec_b.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["primary_record_id"] == str(rec_b.id)
    assert data["archived_record_id"] == str(rec_a.id)


@pytest.mark.asyncio
async def test_merge_marks_secondary_as_duplicate(client: AsyncClient, db_session: AsyncSession):
    """After merge, secondary record is marked is_duplicate=True."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    rec_a, rec_b, candidate = await _create_duplicate_pair(db_session, uid, patient.id)

    await client.post(
        "/api/v1/dedup/merge",
        headers=headers,
        json={"candidate_id": str(candidate.id)},
    )

    # Verify secondary is excluded from records list (is_duplicate=True)
    resp = await client.get("/api/v1/records", headers=headers)
    ids = [item["id"] for item in resp.json()["items"]]
    assert str(rec_a.id) in ids
    assert str(rec_b.id) not in ids


@pytest.mark.asyncio
async def test_dismiss(client: AsyncClient, db_session: AsyncSession):
    """Fix 3: Dismiss returns only {status: 'dismissed'}."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, _, candidate = await _create_duplicate_pair(db_session, uid, patient.id)

    resp = await client.post(
        "/api/v1/dedup/dismiss",
        headers=headers,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "dismissed"}


@pytest.mark.asyncio
async def test_scan_creates_candidates(client: AsyncClient, db_session: AsyncSession):
    """Scan queues a PENDING candidate when the pair scores 0.70–0.95.

    Same code/text/status but the same source format and dates a few days apart
    -> 0.4 + 0.3 + 0.1 = 0.8, below the auto-merge threshold.
    """
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    uid_uuid = UUID(uid)
    rec1 = HealthRecord(
        id=uuid4(),
        patient_id=patient.id,
        user_id=uid_uuid,
        record_type="medication",
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="fhir_r4",
        display_text="Metformin 500mg",
        code_value="860975",
        effective_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        status="active",
    )
    rec2 = HealthRecord(
        id=uuid4(),
        patient_id=patient.id,
        user_id=uid_uuid,
        record_type="medication",
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="fhir_r4",
        display_text="Metformin 500mg",
        code_value="860975",
        effective_date=datetime(2024, 1, 18, tzinfo=timezone.utc),
        status="active",
    )
    db_session.add_all([rec1, rec2])
    await db_session.commit()

    resp = await client.post("/api/v1/dedup/scan", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates_found"] >= 1
    assert data["auto_merged"] == 0


@pytest.mark.asyncio
async def test_scan_auto_merges_exact_duplicates(client: AsyncClient, db_session: AsyncSession):
    """Scan auto-merges a pair scoring >= 0.95 instead of queueing it.

    Identical code/text/status, same day, cross-source -> capped at 1.0.
    """
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    uid_uuid = UUID(uid)
    rec1 = HealthRecord(
        id=uuid4(),
        patient_id=patient.id,
        user_id=uid_uuid,
        record_type="medication",
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="fhir_r4",
        display_text="Metformin 500mg",
        code_value="860975",
        effective_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        status="active",
    )
    rec2 = HealthRecord(
        id=uuid4(),
        patient_id=patient.id,
        user_id=uid_uuid,
        record_type="medication",
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="epic_ehi",
        display_text="Metformin 500mg",
        code_value="860975",
        effective_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        status="active",
    )
    db_session.add_all([rec1, rec2])
    await db_session.commit()

    resp = await client.post("/api/v1/dedup/scan", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_merged"] >= 1
    assert data["candidates_found"] == 0

    # The auto-merge candidate is recorded as resolved, not pending.
    cand_result = await db_session.execute(
        select(DedupCandidate).where(DedupCandidate.status == "merged")
    )
    candidate = cand_result.scalars().first()
    assert candidate is not None
    assert candidate.auto_resolved is True
    assert candidate.resolved_by == uid_uuid
    assert candidate.resolved_at is not None

    # Exactly one of the pair survives; the other is archived (is_duplicate).
    # Which one wins is the DB ordering of equal-dated rows, so don't assume.
    list_resp = await client.get("/api/v1/records", headers=headers)
    ids = [item["id"] for item in list_resp.json()["items"]]
    survivors = {i for i in ids if i in (str(rec1.id), str(rec2.id))}
    assert len(survivors) == 1
    assert candidate.record_a_id in (rec1.id, rec2.id)
    # The surviving record is the candidate's primary (record_a).
    assert str(candidate.record_a_id) in survivors


@pytest.mark.asyncio
async def test_user_isolation(client: AsyncClient, db_session: AsyncSession):
    """User A's dedup candidates don't appear for User B."""
    headers_a, uid_a = await auth_headers(client, email="dedup_a@test.com")
    headers_b, _ = await auth_headers(client, email="dedup_b@test.com")

    patient = await create_test_patient(db_session, uid_a)
    await _create_duplicate_pair(db_session, uid_a, patient.id)

    resp = await client.get("/api/v1/dedup/candidates", headers=headers_b)
    data = resp.json()
    assert data["total"] == 0


async def _make_candidate(
    db_session: AsyncSession,
    user_id: str,
    patient_id,
    score: float,
    code: str,
    status: str = "pending",
) -> tuple[HealthRecord, HealthRecord, DedupCandidate]:
    """Create a record pair + a pending dedup candidate with a fixed score."""
    uid = UUID(user_id)
    rec_a = HealthRecord(
        id=uuid4(),
        patient_id=patient_id,
        user_id=uid,
        record_type="medication",
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="fhir_r4",
        display_text=f"Drug {code}",
        code_value=code,
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
        display_text=f"Drug {code}",
        code_value=code,
        effective_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    db_session.add_all([rec_a, rec_b])
    await db_session.commit()

    candidate = DedupCandidate(
        id=uuid4(),
        record_a_id=rec_a.id,
        record_b_id=rec_b.id,
        similarity_score=score,
        match_reasons={"code_match": True},
        status=status,
    )
    db_session.add(candidate)
    await db_session.commit()
    await db_session.refresh(rec_a)
    await db_session.refresh(rec_b)
    await db_session.refresh(candidate)
    return rec_a, rec_b, candidate


# ---------------------------------------------------------------------------
# Summary (band histogram)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidates_summary(client: AsyncClient, db_session: AsyncSession):
    """Summary buckets pending candidates into descending 10-point bands."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    for i, score in enumerate([0.92, 0.93, 0.83, 0.81, 0.85, 0.72]):
        await _make_candidate(db_session, uid, patient.id, score, code=f"S{i}")

    resp = await client.get("/api/v1/dedup/candidates/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 6
    assert data["bands"] == [
        {"band": 90, "count": 2},
        {"band": 80, "count": 3},
        {"band": 70, "count": 1},
    ]


@pytest.mark.asyncio
async def test_candidates_summary_excludes_resolved(
    client: AsyncClient, db_session: AsyncSession
):
    """Resolved (merged/dismissed) candidates are not counted in the summary."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    await _make_candidate(db_session, uid, patient.id, 0.92, code="P1")
    await _make_candidate(db_session, uid, patient.id, 0.88, code="M1", status="merged")

    resp = await client.get("/api/v1/dedup/candidates/summary", headers=headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["bands"] == [{"band": 90, "count": 1}]


@pytest.mark.asyncio
async def test_candidates_summary_user_isolation(
    client: AsyncClient, db_session: AsyncSession
):
    """Summary only counts the requesting user's candidates."""
    headers_a, uid_a = await auth_headers(client, email="sum_a@test.com")
    headers_b, _ = await auth_headers(client, email="sum_b@test.com")
    patient = await create_test_patient(db_session, uid_a)
    await _make_candidate(db_session, uid_a, patient.id, 0.92, code="A1")

    resp = await client.get("/api/v1/dedup/candidates/summary", headers=headers_b)
    data = resp.json()
    assert data["total"] == 0
    assert data["bands"] == []


# ---------------------------------------------------------------------------
# score_min / score_max filter on GET /dedup/candidates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidates_score_filter(client: AsyncClient, db_session: AsyncSession):
    """score_min/score_max restrict the candidate list to [min, max)."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    await _make_candidate(db_session, uid, patient.id, 0.92, code="H1")
    await _make_candidate(db_session, uid, patient.id, 0.93, code="H2")
    await _make_candidate(db_session, uid, patient.id, 0.83, code="M1")
    await _make_candidate(db_session, uid, patient.id, 0.72, code="L1")

    resp = await client.get(
        "/api/v1/dedup/candidates?score_min=0.9&score_max=1.0", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert 0.9 <= item["similarity_score"] < 1.0


@pytest.mark.asyncio
async def test_candidates_score_max_is_exclusive(
    client: AsyncClient, db_session: AsyncSession
):
    """score_max is an exclusive upper bound."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    await _make_candidate(db_session, uid, patient.id, 0.80, code="B1")
    await _make_candidate(db_session, uid, patient.id, 0.85, code="B2")

    resp = await client.get(
        "/api/v1/dedup/candidates?score_min=0.8&score_max=0.85", headers=headers
    )
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["similarity_score"] == 0.80


# ---------------------------------------------------------------------------
# POST /dedup/resolve-bulk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_bulk_by_ids_merge(client: AsyncClient, db_session: AsyncSession):
    """Bulk merge by explicit candidate_ids marks each secondary duplicate."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, rec_b1, cand1 = await _make_candidate(db_session, uid, patient.id, 0.92, code="C1")
    _, rec_b2, cand2 = await _make_candidate(db_session, uid, patient.id, 0.91, code="C2")

    resp = await client.post(
        "/api/v1/dedup/resolve-bulk",
        headers=headers,
        json={"action": "merge", "candidate_ids": [str(cand1.id), str(cand2.id)]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"action": "merge", "count": 2}

    for cand, sec in ((cand1, rec_b1), (cand2, rec_b2)):
        await db_session.refresh(cand)
        await db_session.refresh(sec)
        assert cand.status == "merged"
        assert cand.resolved_by == UUID(uid)
        assert sec.is_duplicate is True
        assert sec.merged_into_id == cand.record_a_id


@pytest.mark.asyncio
async def test_resolve_bulk_by_score_dismiss(client: AsyncClient, db_session: AsyncSession):
    """Bulk dismiss by score band only touches candidates in [min, max)."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, _, low = await _make_candidate(db_session, uid, patient.id, 0.72, code="D1")
    _, _, high = await _make_candidate(db_session, uid, patient.id, 0.92, code="D2")

    resp = await client.post(
        "/api/v1/dedup/resolve-bulk",
        headers=headers,
        json={"action": "dismiss", "score_min": 0.7, "score_max": 0.8},
    )
    assert resp.status_code == 200
    assert resp.json() == {"action": "dismiss", "count": 1}

    await db_session.refresh(low)
    await db_session.refresh(high)
    assert low.status == "dismissed"
    assert low.resolved_by == UUID(uid)
    assert high.status == "pending"  # outside the band, untouched


@pytest.mark.asyncio
async def test_resolve_bulk_invalid_action(client: AsyncClient, db_session: AsyncSession):
    """An action other than merge/dismiss is rejected with 422."""
    headers, _ = await auth_headers(client)
    resp = await client.post(
        "/api/v1/dedup/resolve-bulk",
        headers=headers,
        json={"action": "frobnicate", "candidate_ids": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_resolve_bulk_user_isolation(client: AsyncClient, db_session: AsyncSession):
    """User B's bulk resolve never touches User A's candidates."""
    headers_a, uid_a = await auth_headers(client, email="bulk_a@test.com")
    headers_b, _ = await auth_headers(client, email="bulk_b@test.com")
    patient = await create_test_patient(db_session, uid_a)
    _, _, cand = await _make_candidate(db_session, uid_a, patient.id, 0.92, code="X1")

    resp = await client.post(
        "/api/v1/dedup/resolve-bulk",
        headers=headers_b,
        json={"action": "merge", "score_min": 0.0, "score_max": 1.0},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0

    await db_session.refresh(cand)
    assert cand.status == "pending"


# ---------------------------------------------------------------------------
# Float-imprecision band boundaries (regression)
#
# _compare_records returns sums like 0.4+0.3+0.1 = 0.7999999999999999 ("80%")
# and 0.4+0.3+0.2 = 0.8999999999999999 ("90%"). The summary band, the
# /candidates score filter, and /resolve-bulk must all agree on the band by
# rounding to integer percent — never comparing the raw float, which would put
# a "80%" score below 0.80.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_band_filter_matches_summary_on_imprecise_scores(
    client: AsyncClient, db_session: AsyncSession
):
    """Summary banding and the /candidates score filter agree at boundaries."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)

    _, _, c70 = await _make_candidate(db_session, uid, patient.id, 0.75, code="B70")
    _, _, c80 = await _make_candidate(db_session, uid, patient.id, 0.4 + 0.3 + 0.1, code="B80")
    _, _, c90 = await _make_candidate(db_session, uid, patient.id, 0.4 + 0.3 + 0.2, code="B90")

    # The imprecise values the bug hinges on.
    assert c80.similarity_score == 0.7999999999999999
    assert c90.similarity_score == 0.8999999999999999

    # (a) Summary buckets by rounded percent: 0.75->70, 0.79999->80, 0.89999->90.
    summary = (
        await client.get("/api/v1/dedup/candidates/summary", headers=headers)
    ).json()
    assert summary["bands"] == [
        {"band": 90, "count": 1},
        {"band": 80, "count": 1},
        {"band": 70, "count": 1},
    ]
    assert summary["total"] == 3

    # (b) band 80 = [0.80, 0.90) must list ONLY the 0.79999 record (not c90).
    band80 = (
        await client.get(
            "/api/v1/dedup/candidates?score_min=0.80&score_max=0.90", headers=headers
        )
    ).json()
    assert band80["total"] == 1
    assert band80["items"][0]["id"] == str(c80.id)

    # band 90 = [0.90, 1.00) must list ONLY the 0.89999 record.
    band90 = (
        await client.get(
            "/api/v1/dedup/candidates?score_min=0.90&score_max=1.00", headers=headers
        )
    ).json()
    assert band90["total"] == 1
    assert band90["items"][0]["id"] == str(c90.id)


@pytest.mark.asyncio
async def test_resolve_bulk_float_boundary(client: AsyncClient, db_session: AsyncSession):
    """resolve-bulk score bands round to percent: a 0.79999 score is band 80."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, _, c70 = await _make_candidate(db_session, uid, patient.id, 0.75, code="R70")
    _, _, c80 = await _make_candidate(db_session, uid, patient.id, 0.4 + 0.3 + 0.1, code="R80")
    _, _, c90 = await _make_candidate(db_session, uid, patient.id, 0.4 + 0.3 + 0.2, code="R90")

    # Dismiss band 70 = [0.70, 0.80): touches ONLY c70, never the 0.79999/0.89999.
    resp = await client.post(
        "/api/v1/dedup/resolve-bulk",
        headers=headers,
        json={"action": "dismiss", "score_min": 0.70, "score_max": 0.80},
    )
    assert resp.json() == {"action": "dismiss", "count": 1}
    for cand in (c70, c80, c90):
        await db_session.refresh(cand)
    assert c70.status == "dismissed"
    assert c80.status == "pending"
    assert c90.status == "pending"

    # Merge band 80 = [0.80, 0.90): catches the 0.79999 record, not c90.
    resp = await client.post(
        "/api/v1/dedup/resolve-bulk",
        headers=headers,
        json={"action": "merge", "score_min": 0.80, "score_max": 0.90},
    )
    assert resp.json() == {"action": "merge", "count": 1}
    for cand in (c80, c90):
        await db_session.refresh(cand)
    assert c80.status == "merged"
    assert c90.status == "pending"


@pytest.mark.asyncio
async def test_resolve_bulk_dismiss_band_80_float_boundary(
    client: AsyncClient, db_session: AsyncSession
):
    """dismiss {0.80, 0.90} catches the 0.79999 ("80%") record, not the 70/90 ones."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, _, c70 = await _make_candidate(db_session, uid, patient.id, 0.70, code="D70")
    _, _, c80 = await _make_candidate(db_session, uid, patient.id, 0.4 + 0.3 + 0.1, code="D80")
    _, _, c90 = await _make_candidate(db_session, uid, patient.id, 0.4 + 0.3 + 0.2, code="D90")

    resp = await client.post(
        "/api/v1/dedup/resolve-bulk",
        headers=headers,
        json={"action": "dismiss", "score_min": 0.80, "score_max": 0.90},
    )
    assert resp.json() == {"action": "dismiss", "count": 1}
    for cand in (c70, c80, c90):
        await db_session.refresh(cand)
    assert c80.status == "dismissed"
    assert c70.status == "pending"
    assert c90.status == "pending"


# ---------------------------------------------------------------------------
# POST /dedup/undo-merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_merge(client: AsyncClient, db_session: AsyncSession):
    """Undo restores the archived record and DISMISSES the candidate.

    Unmerge is a deliberate "these are NOT duplicates" override, so the pair
    must NOT boomerang back into the pending review queue — it is dismissed,
    not returned to pending.
    """
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    rec_a, rec_b, candidate = await _create_duplicate_pair(db_session, uid, patient.id)

    merge_resp = await client.post(
        "/api/v1/dedup/merge",
        headers=headers,
        json={"candidate_id": str(candidate.id)},
    )
    assert merge_resp.status_code == 200

    resp = await client.post(
        "/api/v1/dedup/undo-merge",
        headers=headers,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "dismissed"}

    await db_session.refresh(rec_b)
    await db_session.refresh(candidate)
    assert rec_b.is_duplicate is False
    assert rec_b.merged_into_id is None
    assert candidate.status == "dismissed"
    assert candidate.status != "pending"
    # The reversal is attributed to the acting user, not cleared.
    assert candidate.resolved_by == UUID(uid)
    assert candidate.resolved_at is not None
    assert candidate.auto_resolved is False

    # And it must NOT reappear in the pending review queue.
    pending = (await client.get("/api/v1/dedup/candidates", headers=headers)).json()
    assert pending["total"] == 0


@pytest.mark.asyncio
async def test_undo_merge_requires_merged_status(
    client: AsyncClient, db_session: AsyncSession
):
    """Undo on a candidate that isn't merged returns 404."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, _, candidate = await _create_duplicate_pair(db_session, uid, patient.id)

    resp = await client.post(
        "/api/v1/dedup/undo-merge",
        headers=headers,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_undo_merge_user_isolation(client: AsyncClient, db_session: AsyncSession):
    """User B cannot undo User A's merge."""
    headers_a, uid_a = await auth_headers(client, email="undo_a@test.com")
    headers_b, _ = await auth_headers(client, email="undo_b@test.com")
    patient = await create_test_patient(db_session, uid_a)
    _, _, candidate = await _create_duplicate_pair(db_session, uid_a, patient.id)

    await client.post(
        "/api/v1/dedup/merge",
        headers=headers_a,
        json={"candidate_id": str(candidate.id)},
    )

    resp = await client.post(
        "/api/v1/dedup/undo-merge",
        headers=headers_b,
        json={"candidate_id": str(candidate.id)},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /dedup/merges  &  POST /dedup/undo-bulk
# ---------------------------------------------------------------------------


async def _create_merged_candidate(
    db_session: AsyncSession,
    user_id: str,
    patient_id,
    *,
    code: str,
    auto_resolved: bool = False,
    record_type: str = "medication",
    survivor_text: str | None = None,
    archived_text: str | None = None,
    score: float = 0.97,
    resolved_at: datetime | None = None,
) -> tuple[HealthRecord, HealthRecord, DedupCandidate]:
    """Create a record pair already merged: record_a survives, record_b archived.

    Returns ``(survivor, archived, candidate)`` with the candidate in
    ``status="merged"`` and the archived record flagged ``is_duplicate``.
    """
    uid = UUID(user_id)
    survivor_text = survivor_text if survivor_text is not None else f"Survivor {code}"
    archived_text = archived_text if archived_text is not None else f"Archived {code}"
    survivor = HealthRecord(
        id=uuid4(),
        patient_id=patient_id,
        user_id=uid,
        record_type=record_type,
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="fhir_r4",
        display_text=survivor_text,
        code_value=code,
        effective_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    archived = HealthRecord(
        id=uuid4(),
        patient_id=patient_id,
        user_id=uid,
        record_type=record_type,
        fhir_resource_type="MedicationRequest",
        fhir_resource={"resourceType": "MedicationRequest"},
        source_format="epic_ehi",
        display_text=archived_text,
        code_value=code,
        effective_date=datetime(2024, 1, 16, tzinfo=timezone.utc),
        is_duplicate=True,
        merged_into_id=survivor.id,
    )
    db_session.add_all([survivor, archived])
    await db_session.commit()

    candidate = DedupCandidate(
        id=uuid4(),
        record_a_id=survivor.id,
        record_b_id=archived.id,
        similarity_score=score,
        match_reasons={"code_match": True},
        status="merged",
        auto_resolved=auto_resolved,
        resolved_by=uid,
        resolved_at=resolved_at or datetime.now(timezone.utc),
    )
    db_session.add(candidate)
    await db_session.commit()
    await db_session.refresh(survivor)
    await db_session.refresh(archived)
    await db_session.refresh(candidate)
    return survivor, archived, candidate


@pytest.mark.asyncio
async def test_merges_empty(client: AsyncClient, db_session: AsyncSession):
    """No merges → empty items, zero total, zero counts."""
    headers, _ = await auth_headers(client)
    resp = await client.get("/api/v1/dedup/merges", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"items": [], "total": 0, "counts": {"auto": 0, "manual": 0}}


@pytest.mark.asyncio
async def test_merges_unauthenticated(client: AsyncClient):
    """GET /dedup/merges without token returns 401."""
    resp = await client.get("/api/v1/dedup/merges")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_merges_item_shape(client: AsyncClient, db_session: AsyncSession):
    """A merged candidate is returned with survivor/archived correctly split."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    survivor, archived, candidate = await _create_merged_candidate(
        db_session, uid, patient.id, code="MG1", auto_resolved=False,
        survivor_text="Lisinopril 10 MG Oral Tablet", archived_text="LISINOPRIL 10MG TAB",
    )

    resp = await client.get("/api/v1/dedup/merges", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["counts"] == {"auto": 0, "manual": 1}

    item = data["items"][0]
    assert item["candidate_id"] == str(candidate.id)
    assert item["similarity_score"] == 0.97
    assert item["match_reasons"] == {"code_match": True}
    assert item["auto_resolved"] is False
    assert item["resolved_at"] is not None

    assert item["survivor"]["id"] == str(survivor.id)
    assert item["survivor"]["display_text"] == "Lisinopril 10 MG Oral Tablet"
    assert item["survivor"]["record_type"] == "medication"
    assert item["survivor"]["source_format"] == "fhir_r4"
    assert item["survivor"]["effective_date"] == survivor.effective_date.isoformat()

    assert item["archived"]["id"] == str(archived.id)
    assert item["archived"]["display_text"] == "LISINOPRIL 10MG TAB"
    assert item["archived"]["source_format"] == "epic_ehi"


@pytest.mark.asyncio
async def test_merges_excludes_pending(client: AsyncClient, db_session: AsyncSession):
    """Pending (un-merged) candidates never appear in /merges."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await _make_candidate(db_session, uid, patient.id, 0.82, code="PEND")

    resp = await client.get("/api/v1/dedup/merges", headers=headers)
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_merges_source_filter(client: AsyncClient, db_session: AsyncSession):
    """source=auto/manual filters total+items but counts ignore source."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await _create_merged_candidate(db_session, uid, patient.id, code="A1", auto_resolved=True)
    await _create_merged_candidate(db_session, uid, patient.id, code="A2", auto_resolved=True)
    await _create_merged_candidate(db_session, uid, patient.id, code="M1", auto_resolved=False)

    auto = (await client.get("/api/v1/dedup/merges?source=auto", headers=headers)).json()
    assert auto["total"] == 2
    assert all(i["auto_resolved"] is True for i in auto["items"])
    # counts ALWAYS reflect both kinds within scope, regardless of source filter.
    assert auto["counts"] == {"auto": 2, "manual": 1}

    manual = (await client.get("/api/v1/dedup/merges?source=manual", headers=headers)).json()
    assert manual["total"] == 1
    assert all(i["auto_resolved"] is False for i in manual["items"])
    assert manual["counts"] == {"auto": 2, "manual": 1}


@pytest.mark.asyncio
async def test_merges_record_type_filter(client: AsyncClient, db_session: AsyncSession):
    """record_type filter restricts items AND the counts scope."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    await _create_merged_candidate(
        db_session, uid, patient.id, code="MED1", record_type="medication", auto_resolved=True
    )
    await _create_merged_candidate(
        db_session, uid, patient.id, code="CON1", record_type="condition", auto_resolved=False
    )

    resp = await client.get("/api/v1/dedup/merges?record_type=condition", headers=headers)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["survivor"]["record_type"] == "condition"
    # counts scoped to record_type=condition only → one manual, zero auto.
    assert data["counts"] == {"auto": 0, "manual": 1}


@pytest.mark.asyncio
async def test_merges_search_filter(client: AsyncClient, db_session: AsyncSession):
    """search matches case-insensitively on either record's display_text."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    # survivor text matches, archived doesn't
    await _create_merged_candidate(
        db_session, uid, patient.id, code="S1",
        survivor_text="Atorvastatin 40mg", archived_text="something else",
    )
    # archived text matches, survivor doesn't
    await _create_merged_candidate(
        db_session, uid, patient.id, code="S2",
        survivor_text="unrelated", archived_text="ATORVASTATIN tablet",
    )
    # neither matches
    await _create_merged_candidate(
        db_session, uid, patient.id, code="S3",
        survivor_text="Metformin", archived_text="Metformin 500",
    )

    resp = await client.get("/api/v1/dedup/merges?search=atorvastatin", headers=headers)
    data = resp.json()
    assert data["total"] == 2
    assert data["counts"] == {"auto": 0, "manual": 2}


@pytest.mark.asyncio
async def test_merges_pagination(client: AsyncClient, db_session: AsyncSession):
    """page/limit paginate, ordered by resolved_at desc."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    base = datetime(2024, 5, 1, tzinfo=timezone.utc)
    # newest resolved_at first when ordered desc
    await _create_merged_candidate(
        db_session, uid, patient.id, code="P1", resolved_at=base, survivor_text="oldest"
    )
    await _create_merged_candidate(
        db_session, uid, patient.id, code="P2",
        resolved_at=base + timedelta(days=1), survivor_text="middle",
    )
    await _create_merged_candidate(
        db_session, uid, patient.id, code="P3",
        resolved_at=base + timedelta(days=2), survivor_text="newest",
    )

    page1 = (
        await client.get("/api/v1/dedup/merges?page=1&limit=2", headers=headers)
    ).json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2
    assert page1["items"][0]["survivor"]["display_text"] == "newest"
    assert page1["items"][1]["survivor"]["display_text"] == "middle"

    page2 = (
        await client.get("/api/v1/dedup/merges?page=2&limit=2", headers=headers)
    ).json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["survivor"]["display_text"] == "oldest"


@pytest.mark.asyncio
async def test_merges_user_isolation(client: AsyncClient, db_session: AsyncSession):
    """User B never sees User A's merges."""
    headers_a, uid_a = await auth_headers(client, email="merges_a@test.com")
    headers_b, _ = await auth_headers(client, email="merges_b@test.com")
    patient = await create_test_patient(db_session, uid_a)
    await _create_merged_candidate(db_session, uid_a, patient.id, code="ISO1")

    resp = await client.get("/api/v1/dedup/merges", headers=headers_b)
    data = resp.json()
    assert data["total"] == 0
    assert data["counts"] == {"auto": 0, "manual": 0}


@pytest.mark.asyncio
async def test_undo_bulk(client: AsyncClient, db_session: AsyncSession):
    """Bulk undo reverses each merged candidate: restore archived + dismiss."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, arch1, cand1 = await _create_merged_candidate(db_session, uid, patient.id, code="UB1")
    _, arch2, cand2 = await _create_merged_candidate(db_session, uid, patient.id, code="UB2")

    resp = await client.post(
        "/api/v1/dedup/undo-bulk",
        headers=headers,
        json={"candidate_ids": [str(cand1.id), str(cand2.id)]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"count": 2}

    for cand, arch in ((cand1, arch1), (cand2, arch2)):
        await db_session.refresh(cand)
        await db_session.refresh(arch)
        assert cand.status == "dismissed"
        assert cand.resolved_by == UUID(uid)
        assert cand.resolved_at is not None
        assert arch.is_duplicate is False
        assert arch.merged_into_id is None


@pytest.mark.asyncio
async def test_undo_bulk_skips_non_merged(client: AsyncClient, db_session: AsyncSession):
    """Pending candidates in the batch are ignored, not reversed."""
    headers, uid = await auth_headers(client)
    patient = await create_test_patient(db_session, uid)
    _, _, merged = await _create_merged_candidate(db_session, uid, patient.id, code="OK1")
    _, _, pending = await _make_candidate(db_session, uid, patient.id, 0.82, code="PND1")

    resp = await client.post(
        "/api/v1/dedup/undo-bulk",
        headers=headers,
        json={"candidate_ids": [str(merged.id), str(pending.id)]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"count": 1}

    await db_session.refresh(merged)
    await db_session.refresh(pending)
    assert merged.status == "dismissed"
    assert pending.status == "pending"  # untouched


@pytest.mark.asyncio
async def test_undo_bulk_user_isolation(client: AsyncClient, db_session: AsyncSession):
    """User B cannot undo User A's merges via bulk."""
    headers_a, uid_a = await auth_headers(client, email="ub_a@test.com")
    headers_b, _ = await auth_headers(client, email="ub_b@test.com")
    patient = await create_test_patient(db_session, uid_a)
    _, arch, cand = await _create_merged_candidate(db_session, uid_a, patient.id, code="UBI1")

    resp = await client.post(
        "/api/v1/dedup/undo-bulk",
        headers=headers_b,
        json={"candidate_ids": [str(cand.id)]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"count": 0}

    await db_session.refresh(cand)
    await db_session.refresh(arch)
    assert cand.status == "merged"  # untouched
    assert arch.is_duplicate is True
