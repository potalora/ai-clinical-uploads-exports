from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.llm.types import LLMResponse, LLMUsage
from app.services.extraction.section_parser import SectionType, parse_sections


@pytest.mark.asyncio
async def test_section_parser_uses_facade():
    payload = {
        "document_type": "note",
        "primary_visit_date": None,
        "provider": None,
        "facility": None,
        "sections": [{"type": "medications", "anchor": "MEDICATIONS"}],
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
    with patch("app.services.extraction.section_parser.get_provider", return_value=prov):
        doc = await parse_sections("MEDICATIONS\nlisinopril 10mg", api_key="unused")
    assert any(s.section_type == SectionType.MEDICATIONS for s in doc.sections)
    req = prov.complete.call_args.args[0]
    assert req.json_mode is True
