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
