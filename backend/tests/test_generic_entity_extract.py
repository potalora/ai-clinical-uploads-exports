from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.llm.types import LLMResponse, LLMUsage
from app.services.extraction.generic_entity_extractor import generic_extract_entities_async


@pytest.mark.asyncio
async def test_generic_extract_parses_entities():
    payload = {
        "entities": [
            {
                "entity_class": "medication",
                "text": "lisinopril",
                "attributes": {"dosage": "10mg", "confidence": 0.9},
            },
            {"entity_class": "condition", "text": "hypertension", "attributes": {}},
        ]
    }
    resp = LLMResponse(
        text=json.dumps(payload),
        finish_reason="stop",
        model="m",
        usage=LLMUsage(1, 1, 2),
        raw=None,
    )
    prov = AsyncMock()
    prov.complete.return_value = resp
    with patch(
        "app.services.extraction.generic_entity_extractor.get_provider", return_value=prov
    ):
        result = await generic_extract_entities_async(
            "lisinopril 10mg for hypertension", "f.txt"
        )
    classes = {e.entity_class for e in result.entities}
    assert {"medication", "condition"} <= classes
    med = next(e for e in result.entities if e.entity_class == "medication")
    assert med.text == "lisinopril" and med.confidence == 0.9


@pytest.mark.asyncio
async def test_generic_extract_handles_bad_json():
    resp = LLMResponse(
        text="not json",
        finish_reason="stop",
        model="m",
        usage=LLMUsage(1, 1, 2),
        raw=None,
    )
    prov = AsyncMock()
    prov.complete.return_value = resp
    with patch(
        "app.services.extraction.generic_entity_extractor.get_provider", return_value=prov
    ):
        result = await generic_extract_entities_async("x", "f.txt")
    assert result.entities == [] and result.error is not None
