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
from app.services.dedup.orchestrator import run_upload_dedup, DedupSummary


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
        a = FakeRecord(code_value="R14.0", status="active", display_text="Record A")
        b = FakeRecord(code_value="R14.0", status="resolved", display_text="Record B")
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
        a = FakeRecord(code_value="R14.0", source_section="medications", display_text="Record A")
        b = FakeRecord(code_value="R14.0", source_section="assessment", display_text="Record B")
        score, reasons = _compare_records(a, b)
        assert score == 0.4
        assert "section_match" not in reasons

    def test_source_section_no_bonus_when_none(self):
        """None source_section does not add bonus."""
        a = FakeRecord(code_value="R14.0", source_section=None, display_text="Record A")
        b = FakeRecord(code_value="R14.0", source_section="medications", display_text="Record B")
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
