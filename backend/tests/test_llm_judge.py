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
