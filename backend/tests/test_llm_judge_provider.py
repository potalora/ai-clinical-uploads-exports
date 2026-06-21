from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.llm.types import LLMResponse, LLMUsage
from app.services.dedup.llm_judge import judge_candidate_pair


@pytest.mark.asyncio
async def test_judge_uses_facade_and_strips_patient_fields():
    payload = {"classification": "duplicate", "confidence": 0.9,
               "explanation": "same", "field_diff": None}
    resp = LLMResponse(text=json.dumps(payload), finish_reason="stop",
                       model="m", usage=LLMUsage(1, 1, 2), raw=None)
    prov = AsyncMock()
    prov.complete.return_value = resp
    with patch("app.services.dedup.llm_judge.get_provider", return_value=prov):
        out = await judge_candidate_pair(
            {"resourceType": "Condition", "subject": {"display": "Jane Doe"}},
            {"resourceType": "Condition"}, "condition", api_key="unused")
    assert out.classification == "duplicate"
    sent = prov.complete.call_args.args[0].messages[0].content
    assert "Jane Doe" not in sent  # subject stripped before send
