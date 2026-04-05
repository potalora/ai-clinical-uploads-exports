# Phase B: Smart Deduplication — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-tier dedup engine (heuristic filter + LLM judge) that triggers after every upload type, with per-upload review API, bulk resolution, field-level merge with provenance, and a category-grouped review UI.

**Architecture:** Post-insert scoped scan compares new upload's records against existing patient records. Heuristic filter (threshold 0.5) buckets into auto-merged (>=0.95) and needs-LLM-review (0.5–0.95). LLM judge classifies as duplicate/update/related/distinct. Review API groups candidates by record type for bulk resolution. Field-level merge tracks provenance and supports undo.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, google-genai (Gemini Flash), pytest + pytest-asyncio, Next.js 15, TypeScript, Tailwind CSS 4

**Spec:** `docs/superpowers/specs/2026-04-05-phase-b-smart-dedup-design.md`

---

## Task Dependency Graph

```
Task 1 (DB Migration) ─────┐
                            ├──→ Task 3 (Heuristic Filter)
Task 2 (LLM Judge Service) ┘         │
                                      ├──→ Task 4 (Dedup Orchestrator)
                                      │         │
                                      │         ├──→ Task 5 (Ingestion Integration)
                                      │         │
                                      │         ├──→ Task 6 (Review API)
                                      │         │         │
                                      │         │         ├──→ Task 7 (Field-Level Merge)
                                      │         │         │         │
                                      │         │         │         ├──→ Task 8 (Review API Tests)
                                      │         │         │         │
                                      │         │         │         └──→ Task 9 (Frontend Review Page)
                                      │         │         │
                                      │         │         └──→ Task 10 (Full Suite Regression)
                                      │         │
                                      │         └──→ Task 11 (Smoke Test)
```

Tasks 1 and 2 are independent and can run in parallel.

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `backend/app/services/dedup/llm_judge.py` | Gemini-powered duplicate classification |
| `backend/app/services/dedup/orchestrator.py` | `run_upload_dedup()` — ties heuristic + LLM judge + auto-resolution |
| `backend/app/services/dedup/field_merger.py` | Field-level FHIR merge with provenance |
| `backend/tests/test_llm_judge.py` | LLM judge unit tests |
| `backend/tests/test_dedup_orchestrator.py` | Orchestrator + heuristic integration tests |
| `backend/tests/test_review_api.py` | Review endpoint tests |
| `backend/tests/test_field_merger.py` | Field merge unit tests |
| `frontend/src/app/(dashboard)/upload/[id]/review/page.tsx` | Review UI page |
| `frontend/src/components/retro/DedupReviewCard.tsx` | Category-grouped review card component |

### Modified files
| File | Changes |
|------|---------|
| `backend/app/models/deduplication.py` | Add 6 new columns (llm_classification, llm_confidence, llm_explanation, field_diff, auto_resolved, source_upload_id) |
| `backend/app/services/dedup/detector.py` | Add `detect_upload_duplicates()`, lower threshold to 0.5, add source_section bonus |
| `backend/app/api/upload.py` | Add review endpoints, integrate dedup into `_process_unstructured` and `confirm_extraction` |
| `backend/app/services/ingestion/coordinator.py` | Integrate dedup after structured ingestion |
| `backend/app/schemas/dedup.py` | Add review response schemas |
| `backend/tests/conftest.py` | No changes expected (dedup_candidates already in TRUNCATE) |
| `backend/alembic/versions/` | New migration for DedupCandidate columns |

---

### Task 1: Database Migration — DedupCandidate New Columns

**Files:**
- Create: `backend/alembic/versions/<auto>_add_dedup_llm_columns.py`
- Modify: `backend/app/models/deduplication.py`

- [ ] **Step 1: Add new columns to DedupCandidate model**

In `backend/app/models/deduplication.py`, add after the `resolved_at` column (line 30):

```python
    llm_classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    source_upload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=True
    )
```

Also add `Boolean` to the imports from `sqlalchemy`:

```python
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Text
```

- [ ] **Step 2: Generate migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add dedup LLM columns and source upload tracking"
```

- [ ] **Step 3: Add manual index to migration**

Open the generated migration file and add inside `upgrade()` after the autogenerated operations:

```python
    op.create_index(
        "ix_dedup_source_upload",
        "dedup_candidates",
        ["source_upload_id"],
        postgresql_where=sa.text("source_upload_id IS NOT NULL"),
    )
```

And in `downgrade()`:
```python
    op.drop_index("ix_dedup_source_upload", table_name="dedup_candidates")
```

- [ ] **Step 4: Run migration on test DB**

Run:
```bash
cd backend && DATABASE_URL=postgresql+asyncpg://localhost:5432/medtimeline_test alembic upgrade head
```

Expected: Migration applies cleanly.

- [ ] **Step 5: Verify model loads**

Run:
```bash
cd backend && python -c "from app.models.deduplication import DedupCandidate; print('llm_classification' in [c.key for c in DedupCandidate.__table__.columns])"
```

Expected: `True`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/deduplication.py backend/alembic/versions/
git commit -m "feat: add LLM classification columns to DedupCandidate model"
```

---

### Task 2: LLM Judge Service

**Files:**
- Create: `backend/app/services/dedup/llm_judge.py`
- Test: `backend/tests/test_llm_judge.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_llm_judge.py`:

```python
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.dedup.llm_judge import (
    judge_candidate_pair,
    judge_candidates_batch,
    JudgmentResult,
)


MOCK_FHIR_A = {
    "resourceType": "MedicationRequest",
    "status": "active",
    "medicationCodeableConcept": {"text": "Metformin 500mg"},
    "dosageInstruction": [{"text": "500mg daily"}],
}

MOCK_FHIR_B = {
    "resourceType": "MedicationRequest",
    "status": "active",
    "medicationCodeableConcept": {"text": "Metformin 1000mg"},
    "dosageInstruction": [{"text": "1000mg daily"}],
}


MOCK_LLM_DUPLICATE = {
    "classification": "duplicate",
    "confidence": 0.95,
    "explanation": "Same medication, same dose, same patient context",
    "field_diff": None,
}

MOCK_LLM_UPDATE = {
    "classification": "update",
    "confidence": 0.88,
    "explanation": "Same medication with dose increase from 500mg to 1000mg",
    "field_diff": {
        "dosageInstruction": {"old": "500mg daily", "new": "1000mg daily"},
        "medicationCodeableConcept": {"old": "Metformin 500mg", "new": "Metformin 1000mg"},
    },
}

MOCK_LLM_DISTINCT = {
    "classification": "distinct",
    "confidence": 0.92,
    "explanation": "Different medications entirely despite similar names",
    "field_diff": None,
}

MOCK_LLM_RELATED = {
    "classification": "related",
    "confidence": 0.75,
    "explanation": "Same drug class but different medications",
    "field_diff": None,
}


class TestJudgmentResult:
    """Tests for LLM judgment parsing."""

    def test_parse_duplicate(self):
        result = JudgmentResult.from_llm_response(MOCK_LLM_DUPLICATE)
        assert result.classification == "duplicate"
        assert result.confidence == 0.95
        assert result.field_diff is None

    def test_parse_update_with_diff(self):
        result = JudgmentResult.from_llm_response(MOCK_LLM_UPDATE)
        assert result.classification == "update"
        assert result.confidence == 0.88
        assert "dosageInstruction" in result.field_diff

    def test_parse_invalid_classification_defaults_to_related(self):
        bad_response = {"classification": "INVALID", "confidence": 0.5, "explanation": "test"}
        result = JudgmentResult.from_llm_response(bad_response)
        assert result.classification == "related"

    def test_parse_missing_fields_uses_defaults(self):
        minimal = {"classification": "duplicate"}
        result = JudgmentResult.from_llm_response(minimal)
        assert result.confidence == 0.5
        assert result.explanation == ""


class TestJudgeCandidatePair:
    """Tests for single pair judgment."""

    @pytest.mark.asyncio
    async def test_judge_returns_result(self):
        mock_response = MagicMock()
        mock_response.text = json.dumps(MOCK_LLM_UPDATE)

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("app.services.dedup.llm_judge.genai.Client", return_value=mock_client):
            result = await judge_candidate_pair(MOCK_FHIR_A, MOCK_FHIR_B, "medication", "fake-key")

        assert result.classification == "update"
        assert result.confidence == 0.88

    @pytest.mark.asyncio
    async def test_judge_handles_api_error(self):
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(side_effect=Exception("API error"))

        with patch("app.services.dedup.llm_judge.genai.Client", return_value=mock_client):
            result = await judge_candidate_pair(MOCK_FHIR_A, MOCK_FHIR_B, "medication", "fake-key")

        assert result.classification == "related"
        assert result.confidence == 0.0


class TestJudgeCandidatesBatch:
    """Tests for batch judgment with concurrency."""

    @pytest.mark.asyncio
    async def test_batch_processes_multiple_pairs(self):
        mock_response = MagicMock()
        mock_response.text = json.dumps(MOCK_LLM_DUPLICATE)

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        pairs = [
            (MOCK_FHIR_A, MOCK_FHIR_A, "medication"),
            (MOCK_FHIR_A, MOCK_FHIR_B, "medication"),
        ]

        with patch("app.services.dedup.llm_judge.genai.Client", return_value=mock_client):
            results = await judge_candidates_batch(pairs, "fake-key")

        assert len(results) == 2
        assert all(r.classification == "duplicate" for r in results)

    @pytest.mark.asyncio
    async def test_batch_handles_partial_failure(self):
        mock_success = MagicMock()
        mock_success.text = json.dumps(MOCK_LLM_DUPLICATE)

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=[mock_success, Exception("API error"), mock_success]
        )

        pairs = [
            (MOCK_FHIR_A, MOCK_FHIR_A, "medication"),
            (MOCK_FHIR_A, MOCK_FHIR_B, "medication"),
            (MOCK_FHIR_A, MOCK_FHIR_A, "medication"),
        ]

        with patch("app.services.dedup.llm_judge.genai.Client", return_value=mock_client):
            results = await judge_candidates_batch(pairs, "fake-key")

        assert len(results) == 3
        assert results[0].classification == "duplicate"
        assert results[1].classification == "related"  # fallback
        assert results[2].classification == "duplicate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_llm_judge.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.services.dedup.llm_judge'`

- [ ] **Step 3: Implement LLM judge**

Create `backend/app/services/dedup/llm_judge.py`:

```python
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)

VALID_CLASSIFICATIONS = {"duplicate", "update", "related", "distinct"}

_JUDGE_PROMPT = """\
You are a clinical record deduplication judge. Given two FHIR resources of the same \
type, classify their relationship.

Return ONLY valid JSON with this schema:
{
  "classification": "duplicate" | "update" | "related" | "distinct",
  "confidence": 0.0 to 1.0,
  "explanation": "Brief human-readable reasoning",
  "field_diff": null or {"fieldName": {"old": "value from Record A", "new": "value from Record B"}}
}

Definitions:
- "duplicate": Same clinical event, same data. These are exact or near-exact copies.
- "update": Same clinical event, but Record B has newer/updated values (dose change, status change, new result). Provide field_diff showing what changed.
- "related": Clinically connected but represent different events (e.g., same medication at different time periods, same condition at different encounters).
- "distinct": False positive — these are different clinical concepts despite surface similarity.

Rules:
- Compare clinical meaning, not just text similarity.
- A medication with a changed dose is an "update", not a "duplicate".
- A condition that changed from "active" to "resolved" is an "update".
- Two readings of the same lab on different dates are "related", not duplicates.
- Prefer "related" over "distinct" when records share the same clinical concept.
- Always provide field_diff for "update" classifications.
"""


@dataclass
class JudgmentResult:
    """Result of LLM judgment on a candidate pair."""

    classification: str
    confidence: float
    explanation: str
    field_diff: dict | None

    @classmethod
    def from_llm_response(cls, data: dict) -> JudgmentResult:
        classification = data.get("classification", "related")
        if classification not in VALID_CLASSIFICATIONS:
            classification = "related"
        return cls(
            classification=classification,
            confidence=data.get("confidence", 0.5),
            explanation=data.get("explanation", ""),
            field_diff=data.get("field_diff"),
        )

    @classmethod
    def error_fallback(cls) -> JudgmentResult:
        return cls(
            classification="related",
            confidence=0.0,
            explanation="LLM judgment failed — flagged for manual review",
            field_diff=None,
        )


async def judge_candidate_pair(
    fhir_a: dict,
    fhir_b: dict,
    record_type: str,
    api_key: str,
) -> JudgmentResult:
    """Judge a single candidate pair using Gemini.

    Returns a JudgmentResult. On failure, returns a safe fallback
    that flags the pair for manual review.
    """
    try:
        client = genai.Client(api_key=api_key)
        content = (
            f"{_JUDGE_PROMPT}\n\n"
            f"Record type: {record_type}\n\n"
            f"Record A:\n{json.dumps(fhir_a, indent=2)}\n\n"
            f"Record B:\n{json.dumps(fhir_b, indent=2)}"
        )
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=content,
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        data = json.loads(response.text)
        return JudgmentResult.from_llm_response(data)
    except Exception:
        logger.exception("LLM judge failed for %s pair", record_type)
        return JudgmentResult.error_fallback()


async def judge_candidates_batch(
    pairs: list[tuple[dict, dict, str]],
    api_key: str,
    max_concurrent: int = 3,
) -> list[JudgmentResult]:
    """Judge multiple candidate pairs with bounded concurrency.

    Each entry in pairs is (fhir_a, fhir_b, record_type).
    Returns results in the same order as input pairs.
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def _judge_with_sem(fhir_a: dict, fhir_b: dict, record_type: str) -> JudgmentResult:
        async with sem:
            return await judge_candidate_pair(fhir_a, fhir_b, record_type, api_key)

    tasks = [_judge_with_sem(a, b, rt) for a, b, rt in pairs]
    return await asyncio.gather(*tasks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_llm_judge.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dedup/llm_judge.py backend/tests/test_llm_judge.py
git commit -m "feat: add LLM judge service for dedup classification"
```

---

### Task 3: Upgrade Heuristic Filter

**Files:**
- Modify: `backend/app/services/dedup/detector.py`
- Test: `backend/tests/test_dedup_orchestrator.py` (heuristic portion)

- [ ] **Step 1: Write failing tests for upload-scoped detection**

Create `backend/tests/test_dedup_orchestrator.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from app.services.dedup.detector import (
    detect_upload_duplicates,
    _compare_records,
    _fuzzy_match,
)


class FakeRecord:
    """Minimal stand-in for HealthRecord in unit tests."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.record_type = kwargs.get("record_type", "medication")
        self.code_value = kwargs.get("code_value")
        self.code_display = kwargs.get("code_display")
        self.display_text = kwargs.get("display_text", "Test Record")
        self.effective_date = kwargs.get("effective_date")
        self.status = kwargs.get("status")
        self.source_format = kwargs.get("source_format", "fhir_r4")
        self.source_section = kwargs.get("source_section")
        self.source_file_id = kwargs.get("source_file_id")
        self.fhir_resource = kwargs.get("fhir_resource", {})


class TestCompareRecordsUpgraded:
    """Tests for upgraded scoring with lower threshold and source_section bonus."""

    def test_threshold_at_0_5(self):
        """Records with code match (0.4) + status match (0.1) = 0.5 should pass."""
        a = FakeRecord(code_value="R14.0", status="active")
        b = FakeRecord(code_value="R14.0", status="active")
        score, reasons = _compare_records(a, b)
        assert score >= 0.5

    def test_threshold_below_0_5_rejected(self):
        """Records with only code match (0.4) and no other signals should be at boundary."""
        a = FakeRecord(code_value="R14.0", status="active")
        b = FakeRecord(code_value="R14.0", status="resolved")
        score, reasons = _compare_records(a, b)
        assert score == 0.4  # only code match

    def test_source_section_bonus(self):
        """Matching source_section adds +0.15 to score."""
        a = FakeRecord(code_value="R14.0", source_section="medications")
        b = FakeRecord(code_value="R14.0", source_section="medications")
        score, reasons = _compare_records(a, b)
        assert score >= 0.55  # 0.4 code + 0.15 section
        assert reasons.get("section_match") is True

    def test_source_section_no_bonus_when_different(self):
        """Different source_section does not add bonus."""
        a = FakeRecord(code_value="R14.0", source_section="medications")
        b = FakeRecord(code_value="R14.0", source_section="assessment")
        score, reasons = _compare_records(a, b)
        assert score == 0.4
        assert "section_match" not in reasons

    def test_source_section_no_bonus_when_none(self):
        """None source_section does not add bonus."""
        a = FakeRecord(code_value="R14.0", source_section=None)
        b = FakeRecord(code_value="R14.0", source_section="medications")
        score, reasons = _compare_records(a, b)
        assert score == 0.4

    def test_exact_match_scores_above_0_95(self):
        """Exact match with all signals should score >= 0.95."""
        now = datetime.now(timezone.utc)
        a = FakeRecord(code_value="R14.0", display_text="Abdominal distension", effective_date=now, status="active", source_section="assessment")
        b = FakeRecord(code_value="R14.0", display_text="Abdominal distension", effective_date=now, status="active", source_section="assessment")
        score, reasons = _compare_records(a, b)
        # code(0.4) + text_exact(0.3) + date(0.2) + status(0.1) + section(0.15) = 1.0 (capped)
        assert score >= 0.95

    def test_cross_source_bonus_still_works(self):
        """Cross-source bonus (+0.1) still applies."""
        a = FakeRecord(code_value="R14.0", source_format="fhir_r4")
        b = FakeRecord(code_value="R14.0", source_format="ai_extracted")
        score, reasons = _compare_records(a, b)
        assert score >= 0.5  # 0.4 + 0.1
        assert reasons.get("cross_source") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_dedup_orchestrator.py::TestCompareRecordsUpgraded -v 2>&1 | head -20
```

Expected: Failures on `source_section` tests (attribute doesn't exist on mock) and threshold tests.

- [ ] **Step 3: Update `_compare_records` in detector.py**

In `backend/app/services/dedup/detector.py`, update `_compare_records` to add the source_section bonus. Replace lines 96-135:

```python
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

    # Source section match bonus
    if (
        getattr(a, "source_section", None)
        and getattr(b, "source_section", None)
        and a.source_section == b.source_section
    ):
        score += 0.15
        reasons["section_match"] = True

    return min(score, 1.0), reasons
```

- [ ] **Step 4: Add `detect_upload_duplicates` function**

In `backend/app/services/dedup/detector.py`, add after the existing `detect_duplicates` function (after line 93):

```python
async def detect_upload_duplicates(
    db: AsyncSession,
    upload_id: UUID,
    patient_id: UUID,
    user_id: UUID,
) -> tuple[list[dict], list[dict]]:
    """Detect duplicates scoped to a specific upload.

    Compares records from this upload against all other records for the patient.
    Returns (auto_merged, needs_llm_review) — two lists of candidate dicts.
    auto_merged: score >= 0.95
    needs_llm_review: score 0.5–0.95
    """
    # Fetch records from this upload
    new_result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.user_id == user_id,
            HealthRecord.patient_id == patient_id,
            HealthRecord.source_file_id == upload_id,
            HealthRecord.deleted_at.is_(None),
            HealthRecord.is_duplicate.is_(False),
        )
    )
    new_records = new_result.scalars().all()

    if not new_records:
        return [], []

    # Fetch existing records (from other uploads)
    existing_result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.user_id == user_id,
            HealthRecord.patient_id == patient_id,
            HealthRecord.source_file_id != upload_id,
            HealthRecord.deleted_at.is_(None),
            HealthRecord.is_duplicate.is_(False),
        )
    )
    existing_records = existing_result.scalars().all()

    if not existing_records:
        return [], []

    # Pre-load existing candidate pairs
    existing_pairs_result = await db.execute(
        select(DedupCandidate.record_a_id, DedupCandidate.record_b_id)
    )
    existing_pairs: set[tuple[UUID, UUID]] = set()
    for r in existing_pairs_result.all():
        existing_pairs.add((r[0], r[1]))
        existing_pairs.add((r[1], r[0]))

    # Build lookup by (record_type, code/text) for existing records
    existing_buckets: dict[tuple, list[HealthRecord]] = {}
    for r in existing_records:
        key = (r.record_type, (r.code_value or (r.display_text or "")[:50].lower()))
        existing_buckets.setdefault(key, []).append(r)

    auto_merged: list[dict] = []
    needs_llm_review: list[dict] = []

    for new_rec in new_records:
        key = (new_rec.record_type, (new_rec.code_value or (new_rec.display_text or "")[:50].lower()))
        bucket = existing_buckets.get(key, [])

        for existing_rec in bucket:
            if (new_rec.id, existing_rec.id) in existing_pairs:
                continue

            score, reasons = _compare_records(new_rec, existing_rec)
            if score < 0.5:
                continue

            candidate = {
                "id": uuid4(),
                "record_a_id": existing_rec.id,
                "record_b_id": new_rec.id,
                "similarity_score": score,
                "match_reasons": reasons,
                "status": "pending",
                "source_upload_id": upload_id,
            }

            if score >= 0.95:
                auto_merged.append(candidate)
            else:
                needs_llm_review.append(candidate)

            existing_pairs.add((new_rec.id, existing_rec.id))
            existing_pairs.add((existing_rec.id, new_rec.id))

    logger.info(
        "Upload %s: %d auto-merged, %d need LLM review",
        upload_id, len(auto_merged), len(needs_llm_review),
    )
    return auto_merged, needs_llm_review
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_dedup_orchestrator.py::TestCompareRecordsUpgraded -v
```

Expected: All 7 tests PASS.

- [ ] **Step 6: Run existing dedup tests for regression**

Run:
```bash
cd backend && python -m pytest tests/test_dedup.py -v
```

Expected: All 9 existing tests still PASS (the old `detect_duplicates` function is unchanged, and `_compare_records` scoring changes shouldn't affect tests that create candidates directly).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dedup/detector.py backend/tests/test_dedup_orchestrator.py
git commit -m "feat: add upload-scoped dedup detection with source_section bonus"
```

---

### Task 4: Dedup Orchestrator

**Files:**
- Create: `backend/app/services/dedup/orchestrator.py`
- Test: `backend/tests/test_dedup_orchestrator.py` (append)

- [ ] **Step 1: Write failing tests for orchestrator**

Append to `backend/tests/test_dedup_orchestrator.py`:

```python
from app.services.dedup.orchestrator import run_upload_dedup, DedupSummary


class TestRunUploadDedup:
    """Tests for the full dedup orchestration flow."""

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty_summary(self):
        mock_db = AsyncMock()
        with patch(
            "app.services.dedup.orchestrator.detect_upload_duplicates",
            new_callable=AsyncMock,
            return_value=([], []),
        ):
            summary = await run_upload_dedup(uuid4(), uuid4(), uuid4(), mock_db)

        assert isinstance(summary, DedupSummary)
        assert summary.total_candidates == 0
        assert summary.auto_merged == 0
        assert summary.needs_review == 0

    @pytest.mark.asyncio
    async def test_auto_merge_exact_matches(self):
        mock_db = AsyncMock()
        auto_candidates = [
            {"id": uuid4(), "record_a_id": uuid4(), "record_b_id": uuid4(),
             "similarity_score": 0.98, "match_reasons": {"code_match": True, "text_exact_match": True},
             "status": "pending", "source_upload_id": uuid4()},
        ]

        with patch(
            "app.services.dedup.orchestrator.detect_upload_duplicates",
            new_callable=AsyncMock,
            return_value=(auto_candidates, []),
        ), patch(
            "app.services.dedup.orchestrator._apply_auto_merges",
            new_callable=AsyncMock,
        ) as mock_apply:
            summary = await run_upload_dedup(uuid4(), uuid4(), uuid4(), mock_db)

        assert summary.auto_merged == 1
        assert summary.needs_review == 0
        mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_judge_called_for_fuzzy_matches(self):
        mock_db = AsyncMock()
        fuzzy_candidates = [
            {"id": uuid4(), "record_a_id": uuid4(), "record_b_id": uuid4(),
             "similarity_score": 0.72, "match_reasons": {"code_match": True, "text_fuzzy_match": True},
             "status": "pending", "source_upload_id": uuid4()},
        ]

        mock_judgment = MagicMock()
        mock_judgment.classification = "update"
        mock_judgment.confidence = 0.85
        mock_judgment.explanation = "Dose changed"
        mock_judgment.field_diff = {"dosageInstruction": {"old": "500mg", "new": "1000mg"}}

        with patch(
            "app.services.dedup.orchestrator.detect_upload_duplicates",
            new_callable=AsyncMock,
            return_value=([], fuzzy_candidates),
        ), patch(
            "app.services.dedup.orchestrator._run_llm_judge",
            new_callable=AsyncMock,
            return_value=[mock_judgment],
        ), patch(
            "app.services.dedup.orchestrator._save_candidates",
            new_callable=AsyncMock,
        ):
            summary = await run_upload_dedup(uuid4(), uuid4(), uuid4(), mock_db)

        assert summary.needs_review == 1

    @pytest.mark.asyncio
    async def test_llm_duplicate_auto_merges(self):
        """LLM judge returning 'duplicate' with high confidence auto-merges."""
        mock_db = AsyncMock()
        fuzzy_candidates = [
            {"id": uuid4(), "record_a_id": uuid4(), "record_b_id": uuid4(),
             "similarity_score": 0.72, "match_reasons": {}, "status": "pending",
             "source_upload_id": uuid4()},
        ]

        mock_judgment = MagicMock()
        mock_judgment.classification = "duplicate"
        mock_judgment.confidence = 0.9
        mock_judgment.explanation = "Same record"
        mock_judgment.field_diff = None

        with patch(
            "app.services.dedup.orchestrator.detect_upload_duplicates",
            new_callable=AsyncMock,
            return_value=([], fuzzy_candidates),
        ), patch(
            "app.services.dedup.orchestrator._run_llm_judge",
            new_callable=AsyncMock,
            return_value=[mock_judgment],
        ), patch(
            "app.services.dedup.orchestrator._apply_auto_merges",
            new_callable=AsyncMock,
        ) as mock_apply, patch(
            "app.services.dedup.orchestrator._save_candidates",
            new_callable=AsyncMock,
        ):
            summary = await run_upload_dedup(uuid4(), uuid4(), uuid4(), mock_db)

        assert summary.auto_merged == 1
        mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_distinct_auto_dismisses(self):
        """LLM judge returning 'distinct' with high confidence auto-dismisses."""
        mock_db = AsyncMock()
        fuzzy_candidates = [
            {"id": uuid4(), "record_a_id": uuid4(), "record_b_id": uuid4(),
             "similarity_score": 0.55, "match_reasons": {}, "status": "pending",
             "source_upload_id": uuid4()},
        ]

        mock_judgment = MagicMock()
        mock_judgment.classification = "distinct"
        mock_judgment.confidence = 0.92
        mock_judgment.explanation = "Different concepts"
        mock_judgment.field_diff = None

        with patch(
            "app.services.dedup.orchestrator.detect_upload_duplicates",
            new_callable=AsyncMock,
            return_value=([], fuzzy_candidates),
        ), patch(
            "app.services.dedup.orchestrator._run_llm_judge",
            new_callable=AsyncMock,
            return_value=[mock_judgment],
        ), patch(
            "app.services.dedup.orchestrator._save_candidates",
            new_callable=AsyncMock,
        ):
            summary = await run_upload_dedup(uuid4(), uuid4(), uuid4(), mock_db)

        assert summary.auto_merged == 0
        assert summary.needs_review == 0
        assert summary.dismissed == 1
```

Also add the missing imports at the top of the file:

```python
from app.services.dedup.orchestrator import run_upload_dedup, DedupSummary
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_dedup_orchestrator.py::TestRunUploadDedup -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'app.services.dedup.orchestrator'`

- [ ] **Step 3: Implement orchestrator**

Create `backend/app/services/dedup/orchestrator.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.deduplication import DedupCandidate
from app.models.provenance import Provenance
from app.models.record import HealthRecord
from app.services.dedup.detector import detect_upload_duplicates
from app.services.dedup.llm_judge import judge_candidates_batch, JudgmentResult

logger = logging.getLogger(__name__)


@dataclass
class DedupSummary:
    """Summary of dedup results for an upload."""

    total_candidates: int = 0
    auto_merged: int = 0
    needs_review: int = 0
    dismissed: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_candidates": self.total_candidates,
            "auto_merged": self.auto_merged,
            "needs_review": self.needs_review,
            "dismissed": self.dismissed,
            "by_type": self.by_type,
        }


async def run_upload_dedup(
    upload_id: UUID,
    patient_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> DedupSummary:
    """Run the full dedup pipeline for a single upload.

    1. Heuristic filter: scoped comparison (new records vs existing)
    2. Auto-merge exact matches (score >= 0.95)
    3. LLM judge on fuzzy matches (score 0.5–0.95)
    4. Auto-resolve based on LLM output
    5. Return summary
    """
    summary = DedupSummary()

    # Step 1: Heuristic filter
    auto_merged_candidates, needs_llm_candidates = await detect_upload_duplicates(
        db, upload_id, patient_id, user_id
    )

    if not auto_merged_candidates and not needs_llm_candidates:
        return summary

    # Step 2: Auto-merge exact matches
    if auto_merged_candidates:
        for c in auto_merged_candidates:
            c["auto_resolved"] = True
            c["llm_classification"] = "duplicate"
            c["llm_confidence"] = 1.0
            c["llm_explanation"] = "Exact match (heuristic score >= 0.95)"
            c["status"] = "merged"
        await _save_candidates(db, auto_merged_candidates)
        await _apply_auto_merges(db, auto_merged_candidates, upload_id, user_id)
        summary.auto_merged = len(auto_merged_candidates)

    # Step 3: LLM judge on fuzzy matches
    if needs_llm_candidates:
        judgments = await _run_llm_judge(db, needs_llm_candidates)

        llm_auto_merge = []
        llm_dismissed = []
        llm_needs_review = []

        for candidate, judgment in zip(needs_llm_candidates, judgments):
            candidate["llm_classification"] = judgment.classification
            candidate["llm_confidence"] = judgment.confidence
            candidate["llm_explanation"] = judgment.explanation
            candidate["field_diff"] = judgment.field_diff

            # Auto-resolution rules
            if judgment.classification == "duplicate" and judgment.confidence >= 0.8:
                candidate["auto_resolved"] = True
                candidate["status"] = "merged"
                llm_auto_merge.append(candidate)
            elif judgment.classification == "distinct" and judgment.confidence >= 0.8:
                candidate["auto_resolved"] = True
                candidate["status"] = "dismissed"
                llm_dismissed.append(candidate)
            else:
                candidate["auto_resolved"] = False
                candidate["status"] = "pending"
                llm_needs_review.append(candidate)

        # Save all LLM-judged candidates
        all_llm = llm_auto_merge + llm_dismissed + llm_needs_review
        await _save_candidates(db, all_llm)

        # Apply auto-merges from LLM duplicates
        if llm_auto_merge:
            await _apply_auto_merges(db, llm_auto_merge, upload_id, user_id)
            summary.auto_merged += len(llm_auto_merge)

        summary.dismissed = len(llm_dismissed)
        summary.needs_review = len(llm_needs_review)

    summary.total_candidates = summary.auto_merged + summary.needs_review + summary.dismissed

    # Build by_type counts from all candidates
    all_candidates = auto_merged_candidates + needs_llm_candidates
    for c in all_candidates:
        # Look up record type from record_a
        rec = await db.get(HealthRecord, c["record_a_id"])
        if rec:
            rtype = rec.record_type
            summary.by_type[rtype] = summary.by_type.get(rtype, 0) + 1

    await db.commit()
    return summary


async def _save_candidates(db: AsyncSession, candidates: list[dict]) -> None:
    """Bulk insert dedup candidates."""
    if not candidates:
        return
    for batch_start in range(0, len(candidates), 100):
        batch = candidates[batch_start : batch_start + 100]
        await db.execute(insert(DedupCandidate), batch)
    await db.flush()


async def _apply_auto_merges(
    db: AsyncSession,
    candidates: list[dict],
    upload_id: UUID,
    user_id: UUID,
) -> None:
    """Auto-merge: mark secondary records as duplicates, create provenance."""
    for c in candidates:
        # record_a is existing (primary), record_b is new (secondary)
        await db.execute(
            update(HealthRecord)
            .where(HealthRecord.id == c["record_b_id"])
            .values(
                is_duplicate=True,
                merged_into_id=c["record_a_id"],
                merge_metadata={
                    "merged_from": str(c["record_b_id"]),
                    "merged_at": datetime.now(timezone.utc).isoformat(),
                    "merge_type": "duplicate",
                    "source_upload_id": str(upload_id),
                    "auto_resolved": True,
                },
            )
        )
        # Create provenance
        db.add(Provenance(
            record_id=c["record_a_id"],
            action="merge",
            agent=f"system/auto-merge",
            source_file_id=upload_id,
            details={
                "merged_record_id": str(c["record_b_id"]),
                "similarity_score": c["similarity_score"],
                "classification": c.get("llm_classification", "duplicate"),
            },
        ))
    await db.flush()


async def _run_llm_judge(
    db: AsyncSession,
    candidates: list[dict],
) -> list[JudgmentResult]:
    """Fetch FHIR resources and run LLM judge on candidate pairs."""
    pairs = []
    for c in candidates:
        rec_a = await db.get(HealthRecord, c["record_a_id"])
        rec_b = await db.get(HealthRecord, c["record_b_id"])
        if rec_a and rec_b:
            pairs.append((
                rec_a.fhir_resource or {},
                rec_b.fhir_resource or {},
                rec_a.record_type,
            ))
        else:
            pairs.append(({}, {}, "unknown"))

    return await judge_candidates_batch(pairs, settings.gemini_api_key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_dedup_orchestrator.py -v
```

Expected: All 12 tests PASS (7 heuristic + 5 orchestrator).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dedup/orchestrator.py backend/tests/test_dedup_orchestrator.py
git commit -m "feat: add dedup orchestrator with heuristic + LLM judge pipeline"
```

---

### Task 5: Ingestion Integration

**Files:**
- Modify: `backend/app/api/upload.py`
- Modify: `backend/app/services/ingestion/coordinator.py`

- [ ] **Step 1: Add dedup trigger to `_process_unstructured`**

In `backend/app/api/upload.py`, after the line `upload.record_count = len(created_records)` (around line 648), add dedup scanning before setting the final status. Replace lines 646-653:

```python
                await db.commit()

                # Run dedup scan on newly created records
                from app.services.dedup.orchestrator import run_upload_dedup
                upload.ingestion_status = "dedup_scanning"
                await db.commit()

                dedup_summary = await run_upload_dedup(
                    upload_id, patient.id, user_id, db
                )
                upload.dedup_summary = dedup_summary.to_dict()

                if dedup_summary.needs_review > 0:
                    upload.ingestion_status = "awaiting_review"
                elif dedup_summary.auto_merged > 0:
                    upload.ingestion_status = "completed_with_merges"
                else:
                    upload.ingestion_status = "completed"
                upload.record_count = len(created_records)
```

- [ ] **Step 2: Add dedup trigger to `coordinator.py`**

In `backend/app/services/ingestion/coordinator.py`, after `upload.ingestion_status = "completed"` (line 112), add dedup scanning. Replace lines 112-121:

```python
        # Run dedup scan on newly inserted records
        from app.services.dedup.orchestrator import run_upload_dedup
        upload.ingestion_status = "dedup_scanning"
        await db.commit()

        dedup_summary = await run_upload_dedup(
            upload.id, patient.id, user_id, db
        )
        upload.dedup_summary = dedup_summary.to_dict()

        if dedup_summary.needs_review > 0:
            upload.ingestion_status = "awaiting_review"
        elif dedup_summary.auto_merged > 0:
            upload.ingestion_status = "completed_with_merges"
        else:
            upload.ingestion_status = "completed"

        upload.record_count = stats.get("records_inserted", 0)
        upload.ingestion_errors = stats.get("errors", [])
        upload.processing_completed_at = datetime.now(timezone.utc)
        upload.ingestion_progress = {
            "total_entries": stats.get("total_entries", 0),
            "records_inserted": stats.get("records_inserted", 0),
            "records_skipped": stats.get("records_skipped", 0),
        }
        await db.commit()
```

- [ ] **Step 3: Add dedup trigger to `confirm_extraction`**

In `backend/app/api/upload.py`, in the `confirm_extraction` endpoint (around line 913), replace the status setting with dedup scanning. Replace lines 913-916:

```python
    await db.commit()

    # Run dedup on confirmed records
    from app.services.dedup.orchestrator import run_upload_dedup
    upload.ingestion_status = "dedup_scanning"
    await db.commit()

    dedup_summary = await run_upload_dedup(
        upload_id, patient_uuid, user_id, db
    )
    upload.dedup_summary = dedup_summary.to_dict()

    if dedup_summary.needs_review > 0:
        upload.ingestion_status = "awaiting_review"
    elif dedup_summary.auto_merged > 0:
        upload.ingestion_status = "completed_with_merges"
    else:
        upload.ingestion_status = "completed"
    upload.record_count = created_count
    upload.processing_completed_at = datetime.now(timezone.utc)
    await db.commit()
```

- [ ] **Step 4: Run existing tests**

Run:
```bash
cd backend && python -m pytest tests/test_upload.py tests/test_unstructured_upload.py tests/test_ingestion.py -v 2>&1 | tail -20
```

Expected: All existing tests pass. The unstructured upload tests mock `_process_unstructured` entirely. The ingestion tests may need `run_upload_dedup` patched if they use the real `ingest_file`. If failures occur, add:

```python
@patch("app.services.ingestion.coordinator.run_upload_dedup", new_callable=AsyncMock, return_value=DedupSummary())
```

to the affected test functions.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/upload.py backend/app/services/ingestion/coordinator.py
git commit -m "feat: integrate dedup pipeline into all upload paths"
```

---

### Task 6: Review API Endpoints

**Files:**
- Modify: `backend/app/api/upload.py`
- Modify: `backend/app/schemas/dedup.py`

- [ ] **Step 1: Add review schemas**

In `backend/app/schemas/dedup.py`, append:

```python
class ReviewRecordSummary(BaseModel):
    id: UUID
    display_text: str
    record_type: str
    fhir_resource: dict | None = None

    model_config = {"from_attributes": True}


class ReviewCandidateResponse(BaseModel):
    candidate_id: UUID
    primary: ReviewRecordSummary
    secondary: ReviewRecordSummary
    similarity_score: float
    llm_classification: str | None = None
    llm_confidence: float | None = None
    llm_explanation: str | None = None
    field_diff: dict | None = None
    merged_at: datetime | None = None


class ReviewResponse(BaseModel):
    upload: dict
    auto_merged: list[ReviewCandidateResponse]
    needs_review: dict[str, list[ReviewCandidateResponse]]


class ResolutionAction(BaseModel):
    candidate_id: UUID
    action: str  # merge, update, dismiss, keep_both
    field_overrides: list[str] | None = None


class BulkResolveRequest(BaseModel):
    resolutions: list[ResolutionAction]


class UndoMergeRequest(BaseModel):
    candidate_id: UUID
```

- [ ] **Step 2: Add GET review endpoint**

In `backend/app/api/upload.py`, add after the existing endpoints (before the end of the file):

```python
@router.get("/{upload_id}/review")
async def get_upload_review(
    upload_id: UUID,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get dedup review data for an upload."""
    from app.models.deduplication import DedupCandidate

    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == upload_id,
            UploadedFile.user_id == user_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Fetch all candidates for this upload
    candidates_result = await db.execute(
        select(DedupCandidate).where(
            DedupCandidate.source_upload_id == upload_id,
        )
    )
    candidates = candidates_result.scalars().all()

    auto_merged = []
    needs_review: dict[str, list] = {}

    for c in candidates:
        rec_a = await db.get(HealthRecord, c.record_a_id)
        rec_b = await db.get(HealthRecord, c.record_b_id)
        if not rec_a or not rec_b:
            continue

        entry = {
            "candidate_id": str(c.id),
            "primary": {
                "id": str(rec_a.id),
                "display_text": rec_a.display_text or "",
                "record_type": rec_a.record_type,
                "fhir_resource": rec_a.fhir_resource,
            },
            "secondary": {
                "id": str(rec_b.id),
                "display_text": rec_b.display_text or "",
                "record_type": rec_b.record_type,
                "fhir_resource": rec_b.fhir_resource,
            },
            "similarity_score": c.similarity_score,
            "llm_classification": c.llm_classification,
            "llm_confidence": c.llm_confidence,
            "llm_explanation": c.llm_explanation,
            "field_diff": c.field_diff,
            "merged_at": c.resolved_at.isoformat() if c.resolved_at else None,
        }

        if c.status == "merged" and c.auto_resolved:
            auto_merged.append(entry)
        elif c.status == "pending":
            rtype = rec_a.record_type
            needs_review.setdefault(rtype, []).append(entry)

    await log_audit_event(
        db,
        user_id=user_id,
        action="upload.review.view",
        resource_type="uploaded_file",
        resource_id=upload_id,
    )

    return {
        "upload": {
            "id": str(upload.id),
            "filename": upload.filename,
            "uploaded_at": upload.created_at.isoformat() if upload.created_at else None,
            "record_count": upload.record_count,
            "status": upload.ingestion_status,
            "dedup_summary": upload.dedup_summary,
        },
        "auto_merged": auto_merged,
        "needs_review": needs_review,
    }
```

- [ ] **Step 3: Add POST resolve endpoint**

In `backend/app/api/upload.py`, add after the review GET endpoint:

```python
@router.post("/{upload_id}/review/resolve")
async def resolve_review(
    upload_id: UUID,
    body: dict,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Bulk resolve dedup candidates for an upload."""
    from app.models.deduplication import DedupCandidate
    from app.models.provenance import Provenance
    from app.services.dedup.field_merger import apply_field_update

    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == upload_id,
            UploadedFile.user_id == user_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    resolutions = body.get("resolutions", [])
    resolved_count = 0

    for resolution in resolutions:
        candidate_id = UUID(resolution["candidate_id"])
        action = resolution["action"]
        field_overrides = resolution.get("field_overrides")

        candidate = await db.get(DedupCandidate, candidate_id)
        if not candidate or candidate.source_upload_id != upload_id:
            continue

        rec_a = await db.get(HealthRecord, candidate.record_a_id)
        rec_b = await db.get(HealthRecord, candidate.record_b_id)
        if not rec_a or not rec_b:
            continue

        now = datetime.now(timezone.utc)

        if action == "merge":
            rec_b.is_duplicate = True
            rec_b.merged_into_id = rec_a.id
            rec_b.merge_metadata = {
                "merged_from": str(rec_b.id),
                "merged_at": now.isoformat(),
                "merge_type": "duplicate",
                "source_upload_id": str(upload_id),
            }
            candidate.status = "merged"
            candidate.resolved_by = user_id
            candidate.resolved_at = now
            db.add(Provenance(
                record_id=rec_a.id,
                action="merge",
                agent=f"user/{user_id}",
                source_file_id=upload_id,
                details={"merged_record_id": str(rec_b.id), "action": "merge"},
            ))

        elif action == "update":
            merge_result = apply_field_update(rec_a, rec_b, field_overrides)
            rec_a.fhir_resource = merge_result["updated_resource"]
            rec_a.display_text = merge_result["display_text"]
            rec_a.merge_metadata = merge_result["merge_metadata"]
            rec_b.is_duplicate = True
            rec_b.merged_into_id = rec_a.id
            candidate.status = "merged"
            candidate.resolved_by = user_id
            candidate.resolved_at = now
            db.add(Provenance(
                record_id=rec_a.id,
                action="field_update",
                agent=f"user/{user_id}",
                source_file_id=upload_id,
                details={
                    "merged_record_id": str(rec_b.id),
                    "fields_updated": merge_result["merge_metadata"].get("fields_updated", []),
                },
            ))

        elif action in ("dismiss", "keep_both"):
            candidate.status = "dismissed"
            candidate.resolved_by = user_id
            candidate.resolved_at = now

        resolved_count += 1

    # Check if all candidates are resolved
    pending_result = await db.execute(
        select(DedupCandidate).where(
            DedupCandidate.source_upload_id == upload_id,
            DedupCandidate.status == "pending",
        )
    )
    remaining = pending_result.scalars().all()
    if not remaining:
        upload.ingestion_status = "completed"

    await db.commit()

    await log_audit_event(
        db,
        user_id=user_id,
        action="upload.review.resolve",
        resource_type="uploaded_file",
        resource_id=upload_id,
        details={"resolutions_count": resolved_count},
    )

    return {"resolved": resolved_count, "remaining": len(remaining)}
```

- [ ] **Step 4: Add POST undo-merge endpoint**

In `backend/app/api/upload.py`, add after the resolve endpoint:

```python
@router.post("/{upload_id}/review/undo-merge")
async def undo_merge(
    upload_id: UUID,
    body: dict,
    user_id: UUID = Depends(get_authenticated_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Undo an auto-merged dedup candidate."""
    from app.models.deduplication import DedupCandidate
    from app.services.dedup.field_merger import revert_field_update

    result = await db.execute(
        select(UploadedFile).where(
            UploadedFile.id == upload_id,
            UploadedFile.user_id == user_id,
        )
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    candidate_id = UUID(body["candidate_id"])
    candidate = await db.get(DedupCandidate, candidate_id)
    if not candidate or candidate.source_upload_id != upload_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.status != "merged":
        raise HTTPException(status_code=400, detail="Candidate is not merged")

    # Restore secondary record
    rec_b = await db.get(HealthRecord, candidate.record_b_id)
    if rec_b:
        rec_b.is_duplicate = False
        rec_b.merged_into_id = None

    # Revert field changes on primary if this was a field update
    rec_a = await db.get(HealthRecord, candidate.record_a_id)
    if rec_a and rec_a.merge_metadata and rec_a.merge_metadata.get("previous_values"):
        revert_field_update(rec_a)

    # Reset candidate
    candidate.status = "pending"
    candidate.resolved_by = None
    candidate.resolved_at = None

    # Update upload status if needed
    if upload.ingestion_status == "completed":
        upload.ingestion_status = "awaiting_review"

    await db.commit()

    await log_audit_event(
        db,
        user_id=user_id,
        action="upload.review.undo",
        resource_type="uploaded_file",
        resource_id=upload_id,
        details={"candidate_id": str(candidate_id)},
    )

    return {"status": "undone", "candidate_id": str(candidate_id)}
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/upload.py backend/app/schemas/dedup.py
git commit -m "feat: add review API endpoints (get, resolve, undo-merge)"
```

---

### Task 7: Field-Level Merge Service

**Files:**
- Create: `backend/app/services/dedup/field_merger.py`
- Test: `backend/tests/test_field_merger.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_field_merger.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.dedup.field_merger import apply_field_update, revert_field_update


def _make_record(fhir_resource: dict, record_type: str = "medication", display_text: str = "Test"):
    rec = MagicMock()
    rec.id = uuid4()
    rec.fhir_resource = fhir_resource.copy()
    rec.record_type = record_type
    rec.display_text = display_text
    rec.fhir_resource_type = fhir_resource.get("resourceType", "Unknown")
    rec.merge_metadata = None
    return rec


class TestApplyFieldUpdate:
    """Tests for field-level FHIR merge."""

    def test_update_all_changed_fields(self):
        primary = _make_record({
            "resourceType": "MedicationRequest",
            "status": "active",
            "dosageInstruction": [{"text": "500mg daily"}],
            "medicationCodeableConcept": {"text": "Metformin 500mg"},
        })
        secondary = _make_record({
            "resourceType": "MedicationRequest",
            "status": "active",
            "dosageInstruction": [{"text": "1000mg daily"}],
            "medicationCodeableConcept": {"text": "Metformin 1000mg"},
        })

        result = apply_field_update(primary, secondary, field_overrides=None)

        assert result["updated_resource"]["dosageInstruction"] == [{"text": "1000mg daily"}]
        assert result["updated_resource"]["medicationCodeableConcept"]["text"] == "Metformin 1000mg"
        assert "dosageInstruction" in result["merge_metadata"]["fields_updated"]
        assert result["merge_metadata"]["previous_values"]["dosageInstruction"] == [{"text": "500mg daily"}]

    def test_cherry_pick_specific_fields(self):
        primary = _make_record({
            "resourceType": "Condition",
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "code": {"text": "Hypertension"},
        })
        secondary = _make_record({
            "resourceType": "Condition",
            "clinicalStatus": {"coding": [{"code": "resolved"}]},
            "code": {"text": "Essential Hypertension"},
        })

        result = apply_field_update(primary, secondary, field_overrides=["clinicalStatus"])

        # Only clinicalStatus should be updated
        assert result["updated_resource"]["clinicalStatus"]["coding"][0]["code"] == "resolved"
        # code should remain unchanged
        assert result["updated_resource"]["code"]["text"] == "Hypertension"
        assert "clinicalStatus" in result["merge_metadata"]["fields_updated"]
        assert "code" in result["merge_metadata"]["fields_kept"]

    def test_preserves_resource_type_and_metadata(self):
        primary = _make_record({
            "resourceType": "Observation",
            "status": "final",
            "valueQuantity": {"value": 120},
            "_extraction_metadata": {"entity_class": "vital"},
        })
        secondary = _make_record({
            "resourceType": "Observation",
            "status": "final",
            "valueQuantity": {"value": 130},
            "_extraction_metadata": {"entity_class": "vital"},
        })

        result = apply_field_update(primary, secondary, field_overrides=None)
        assert result["updated_resource"]["resourceType"] == "Observation"
        assert "_extraction_metadata" in result["updated_resource"]

    def test_display_text_regenerated(self):
        primary = _make_record(
            {"resourceType": "MedicationRequest", "medicationCodeableConcept": {"text": "Old"}},
            display_text="Old",
        )
        secondary = _make_record(
            {"resourceType": "MedicationRequest", "medicationCodeableConcept": {"text": "New"}},
            display_text="New",
        )

        result = apply_field_update(primary, secondary, field_overrides=None)
        assert result["display_text"]  # Should have some display text


class TestRevertFieldUpdate:
    """Tests for undoing a field-level merge."""

    def test_revert_restores_previous_values(self):
        rec = _make_record({
            "resourceType": "MedicationRequest",
            "dosageInstruction": [{"text": "1000mg daily"}],
        })
        rec.merge_metadata = {
            "previous_values": {
                "dosageInstruction": [{"text": "500mg daily"}],
            },
            "fields_updated": ["dosageInstruction"],
        }

        revert_field_update(rec)

        assert rec.fhir_resource["dosageInstruction"] == [{"text": "500mg daily"}]
        assert rec.merge_metadata is None

    def test_revert_noop_when_no_previous_values(self):
        rec = _make_record({"resourceType": "Condition", "code": {"text": "Test"}})
        rec.merge_metadata = {"merge_type": "duplicate"}

        revert_field_update(rec)
        assert rec.fhir_resource["code"]["text"] == "Test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_field_merger.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement field merger**

Create `backend/app/services/dedup/field_merger.py`:

```python
from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone

from app.services.ingestion.fhir_parser import build_display_text

logger = logging.getLogger(__name__)

# Fields that should never be overwritten during merge
PROTECTED_FIELDS = {"resourceType", "_extraction_metadata", "id", "meta"}


def apply_field_update(
    primary,
    secondary,
    field_overrides: list[str] | None = None,
) -> dict:
    """Apply field-level updates from secondary record to primary.

    If field_overrides is None, all changed fields are applied.
    If field_overrides is a list of field names, only those fields are applied.

    Returns a dict with:
    - updated_resource: The new FHIR resource for the primary record
    - display_text: Regenerated display text
    - merge_metadata: Provenance metadata including previous values
    """
    old_resource = copy.deepcopy(primary.fhir_resource or {})
    new_resource = copy.deepcopy(old_resource)
    secondary_resource = secondary.fhir_resource or {}

    # Determine which fields differ
    all_keys = set(old_resource.keys()) | set(secondary_resource.keys())
    changed_fields = []
    for key in all_keys:
        if key in PROTECTED_FIELDS:
            continue
        if old_resource.get(key) != secondary_resource.get(key):
            changed_fields.append(key)

    # Determine which fields to update
    if field_overrides is not None:
        fields_to_update = [f for f in field_overrides if f in changed_fields]
    else:
        fields_to_update = changed_fields

    fields_kept = [f for f in changed_fields if f not in fields_to_update]

    # Build previous values for undo support
    previous_values = {}
    for field in fields_to_update:
        if field in old_resource:
            previous_values[field] = copy.deepcopy(old_resource[field])
        else:
            previous_values[field] = None

    # Apply updates
    for field in fields_to_update:
        if field in secondary_resource:
            new_resource[field] = copy.deepcopy(secondary_resource[field])
        else:
            new_resource.pop(field, None)

    # Regenerate display text
    resource_type = new_resource.get("resourceType", primary.fhir_resource_type)
    display_text = build_display_text(new_resource, resource_type)

    merge_metadata = {
        "merged_from": str(secondary.id),
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "merge_type": "update",
        "fields_updated": fields_to_update,
        "fields_kept": fields_kept,
        "previous_values": previous_values,
    }

    return {
        "updated_resource": new_resource,
        "display_text": display_text,
        "merge_metadata": merge_metadata,
    }


def revert_field_update(record) -> None:
    """Revert a field-level merge using previous_values from merge_metadata.

    Modifies the record in place.
    """
    metadata = record.merge_metadata
    if not metadata or not metadata.get("previous_values"):
        return

    resource = record.fhir_resource or {}
    for field, old_value in metadata["previous_values"].items():
        if old_value is None:
            resource.pop(field, None)
        else:
            resource[field] = copy.deepcopy(old_value)

    record.fhir_resource = resource
    record.merge_metadata = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_field_merger.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dedup/field_merger.py backend/tests/test_field_merger.py
git commit -m "feat: add field-level FHIR merge with undo support"
```

---

### Task 8: Review API Tests

**Files:**
- Create: `backend/tests/test_review_api.py`

- [ ] **Step 1: Write review API tests**

Create `backend/tests/test_review_api.py`:

```python
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deduplication import DedupCandidate
from app.models.record import HealthRecord
from app.models.uploaded_file import UploadedFile


async def _create_upload_with_candidates(
    db: AsyncSession, user_id, patient_id, *, auto_merged: int = 0, pending: int = 0
) -> tuple:
    """Helper: create an upload with dedup candidates."""
    upload = UploadedFile(
        id=uuid4(),
        user_id=user_id,
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

    candidates = []
    for i in range(auto_merged + pending):
        rec_a = HealthRecord(
            id=uuid4(), patient_id=patient_id, user_id=user_id,
            record_type="medication", fhir_resource_type="MedicationRequest",
            fhir_resource={"resourceType": "MedicationRequest", "medicationCodeableConcept": {"text": f"Med A{i}"}},
            source_format="fhir_r4", display_text=f"Med A{i}",
            source_file_id=uuid4(),
        )
        rec_b = HealthRecord(
            id=uuid4(), patient_id=patient_id, user_id=user_id,
            record_type="medication", fhir_resource_type="MedicationRequest",
            fhir_resource={"resourceType": "MedicationRequest", "medicationCodeableConcept": {"text": f"Med B{i}"}},
            source_format="fhir_r4", display_text=f"Med B{i}",
            source_file_id=upload.id,
        )
        db.add(rec_a)
        db.add(rec_b)

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

    await db.commit()
    return upload, candidates


@pytest.mark.asyncio
async def test_review_unauthenticated(client: AsyncClient):
    resp = await client.get(f"/api/v1/upload/{uuid4()}/review")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/v1/upload/{uuid4()}/review", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_review_returns_grouped_candidates(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, create_test_patient
):
    patient = await create_test_patient(db_session)
    # Extract user_id from auth flow
    from app.models.user import User
    from sqlalchemy import select
    users = (await db_session.execute(select(User))).scalars().all()
    user_id = users[0].id

    upload, candidates = await _create_upload_with_candidates(
        db_session, user_id, patient.id, auto_merged=2, pending=1
    )

    resp = await client.get(f"/api/v1/upload/{upload.id}/review", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["upload"]["status"] == "awaiting_review"
    assert len(data["auto_merged"]) == 2
    assert "medication" in data["needs_review"]
    assert len(data["needs_review"]["medication"]) == 1


@pytest.mark.asyncio
async def test_resolve_merge(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, create_test_patient
):
    patient = await create_test_patient(db_session)
    from app.models.user import User
    from sqlalchemy import select
    users = (await db_session.execute(select(User))).scalars().all()
    user_id = users[0].id

    upload, candidates = await _create_upload_with_candidates(
        db_session, user_id, patient.id, pending=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/resolve",
        headers=auth_headers,
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
async def test_resolve_dismiss(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, create_test_patient
):
    patient = await create_test_patient(db_session)
    from app.models.user import User
    from sqlalchemy import select
    users = (await db_session.execute(select(User))).scalars().all()
    user_id = users[0].id

    upload, candidates = await _create_upload_with_candidates(
        db_session, user_id, patient.id, pending=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/resolve",
        headers=auth_headers,
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
async def test_undo_merge(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, create_test_patient
):
    patient = await create_test_patient(db_session)
    from app.models.user import User
    from sqlalchemy import select
    users = (await db_session.execute(select(User))).scalars().all()
    user_id = users[0].id

    upload, candidates = await _create_upload_with_candidates(
        db_session, user_id, patient.id, auto_merged=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/undo-merge",
        headers=auth_headers,
        json={"candidate_id": str(candidates[0].id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "undone"


@pytest.mark.asyncio
async def test_undo_merge_not_merged_returns_400(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, create_test_patient
):
    patient = await create_test_patient(db_session)
    from app.models.user import User
    from sqlalchemy import select
    users = (await db_session.execute(select(User))).scalars().all()
    user_id = users[0].id

    upload, candidates = await _create_upload_with_candidates(
        db_session, user_id, patient.id, pending=1
    )

    resp = await client.post(
        f"/api/v1/upload/{upload.id}/review/undo-merge",
        headers=auth_headers,
        json={"candidate_id": str(candidates[0].id)},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_review_api.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_review_api.py
git commit -m "test: add review API endpoint tests"
```

---

### Task 9: Frontend Review Page

**Files:**
- Create: `frontend/src/app/(dashboard)/upload/[id]/review/page.tsx`
- Create: `frontend/src/components/retro/DedupReviewCard.tsx`

This task requires invoking the `superpowers:frontend-design` skill for UI implementation. The implementer should invoke that skill before writing any frontend code.

- [ ] **Step 1: Create DedupReviewCard component**

Create `frontend/src/components/retro/DedupReviewCard.tsx` — a category-grouped review card component with:
- Group header with record type, count, "Accept All" / "Decline All" buttons
- Expandable candidate rows showing: compact summary, LLM confidence badge, side-by-side diff
- Per-row Accept / Decline / Edit actions
- Checkbox selection for bulk operations

- [ ] **Step 2: Create review page**

Create `frontend/src/app/(dashboard)/upload/[id]/review/page.tsx` with:
- Header: upload filename, date, record count, status badge
- Summary bar: auto-merged count, needs-review count
- Collapsible auto-merged section (default collapsed) with undo buttons
- Needs-review section using DedupReviewCard grouped by record type
- Sticky bulk action bar at bottom
- API integration: `GET /upload/{id}/review`, `POST /upload/{id}/review/resolve`, `POST /upload/{id}/review/undo-merge`

- [ ] **Step 3: Add review link to upload history**

Modify the upload history page to show a "Review" link for uploads with status `completed_with_merges` or `awaiting_review`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\(dashboard\)/upload/\[id\]/review/ frontend/src/components/retro/DedupReviewCard.tsx
git commit -m "feat: add dedup review page with category-grouped bulk resolution"
```

---

### Task 10: Full Suite Regression Fix

**Files:**
- Various (depending on what breaks)

- [ ] **Step 1: Run the complete backend test suite**

Run:
```bash
cd backend && python -m pytest -x -v --ignore=tests/fidelity 2>&1 | tail -40
```

- [ ] **Step 2: Fix any regressions**

Common issues:
- Tests that call `ingest_file()` may need `run_upload_dedup` patched
- Upload status assertions may need updating for new statuses (`dedup_scanning`, `completed_with_merges`, `awaiting_review`)
- The `confirm_extraction` tests may need dedup mocked

For each failing test, patch `run_upload_dedup`:

```python
from unittest.mock import patch, AsyncMock
from app.services.dedup.orchestrator import DedupSummary

@patch("app.services.dedup.orchestrator.run_upload_dedup", new_callable=AsyncMock, return_value=DedupSummary())
```

- [ ] **Step 3: Run fidelity tests**

Run:
```bash
cd backend && python -m pytest tests/fidelity/ -v -k "not fidelity" 2>&1 | tail -10
```

- [ ] **Step 4: Commit fixes**

```bash
git add -u
git commit -m "fix: resolve test regressions from dedup integration"
```

---

### Task 11: Dev Migration and Smoke Test

**Files:**
- No file changes — validation only

- [ ] **Step 1: Run migration on dev database**

Run:
```bash
cd backend && DATABASE_URL=postgresql+asyncpg://localhost:5432/medtimeline alembic upgrade head
```

Expected: Migration applies cleanly.

- [ ] **Step 2: Verify app starts**

Run:
```bash
cd backend && python -c "
from app.main import app
from app.models.deduplication import DedupCandidate
from app.services.dedup.orchestrator import run_upload_dedup, DedupSummary
from app.services.dedup.llm_judge import judge_candidate_pair, JudgmentResult
from app.services.dedup.field_merger import apply_field_update, revert_field_update
print('All imports OK')
print('DedupCandidate columns:', [c.key for c in DedupCandidate.__table__.columns if c.key.startswith('llm')])
"
```

Expected: All imports OK, LLM columns listed.

- [ ] **Step 3: Verify review endpoints registered**

Run:
```bash
cd backend && python -c "
from app.main import app
routes = [r.path for r in app.routes if hasattr(r, 'path')]
assert '/api/v1/upload/{upload_id}/review' in routes or any('review' in r for r in routes)
print('Review endpoints registered')
"
```

Expected: `Review endpoints registered`

---

## Summary

| Task | Tests | Description |
|------|-------|-------------|
| 1 | 0 | DB migration — DedupCandidate LLM columns |
| 2 | 8 | LLM judge service |
| 3 | 7 | Heuristic filter upgrade (threshold, source_section, upload-scoped) |
| 4 | 5 | Dedup orchestrator (heuristic + LLM + auto-resolution) |
| 5 | 0 | Ingestion integration (3 trigger points) |
| 6 | 0 | Review API endpoints (get, resolve, undo-merge) |
| 7 | 6 | Field-level merge with undo |
| 8 | 7 | Review API tests |
| 9 | 0 | Frontend review page |
| 10 | 0 | Full suite regression fix |
| 11 | 0 | Dev migration and smoke test |
| **Total** | **~33 backend + frontend** | |

Parallelization: Tasks 1 and 2 are independent. Task 9 (frontend) can start once Task 6 is committed (API contract stable).
