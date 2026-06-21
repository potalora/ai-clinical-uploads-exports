from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.llm.openai_compat import OpenAICompatProvider
from app.services.ai.llm.types import ImagePart, LLMMessage, LLMRequest, TextPart


@pytest.mark.asyncio
async def test_openai_sends_image_url_data_uri():
    choice = SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")
    resp = SimpleNamespace(choices=[choice],
                           usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                           model="gpt-4o-mini")
    fake = MagicMock()
    fake.chat.completions.create = AsyncMock(return_value=resp)
    with patch("app.services.ai.llm.openai_compat.AsyncOpenAI", return_value=fake):
        # Construct under the patch so the client is the mock, not a real AsyncOpenAI.
        prov = OpenAICompatProvider(name="openai", api_key="k",
                                    base_url="https://api.openai.com/v1", model_default="gpt-4o-mini")
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("Extract"), ImagePart(b"IMG", "image/png")])],
            model="gpt-4o-mini", max_output_tokens=64))
    content = fake.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    img = next(p for p in content if p["type"] == "image_url")
    assert img["image_url"]["url"].startswith("data:image/png;base64,")
