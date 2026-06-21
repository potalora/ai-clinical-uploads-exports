from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.ai.llm.gemini import GeminiProvider
from app.services.ai.llm.types import ImagePart, LLMMessage, LLMRequest, TextPart


@pytest.mark.asyncio
async def test_gemini_sends_image_bytes():
    prov = GeminiProvider(api_key="k", model_default="gemini-3.5-flash")
    resp = SimpleNamespace(text="extracted", usage_metadata=None,
                           candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))])
    fake = MagicMock()
    fake.aio.models.generate_content = AsyncMock(return_value=resp)
    captured = {}

    def from_bytes(data, mime_type):
        captured["mime"] = mime_type
        captured["len"] = len(data)
        return f"PART({mime_type})"

    with patch("app.services.ai.llm.gemini.genai.Client", return_value=fake), \
         patch("app.services.ai.llm.gemini.gtypes.Part.from_bytes", side_effect=from_bytes):
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("Extract text"), ImagePart(b"IMG", "image/tiff")])],
            model="gemini-3.5-flash", max_output_tokens=64))
    assert captured["mime"] == "image/tiff" and captured["len"] == 3
    sent = fake.aio.models.generate_content.call_args.kwargs["contents"]
    assert "Extract text" in sent and 'PART(image/tiff)' in sent
