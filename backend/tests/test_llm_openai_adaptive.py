from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import BadRequestError

from app.services.ai.llm.openai_compat import OpenAICompatProvider
from app.services.ai.llm.types import LLMMessage, LLMRequest


def _bad_request(msg: str) -> BadRequestError:
    req = httpx.Request("POST", "http://test/v1/chat/completions")
    return BadRequestError(msg, response=httpx.Response(400, request=req), body=None)


def _ok():
    choice = SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")
    return SimpleNamespace(
        choices=[choice],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        model="gpt-5.4-mini",
    )


@pytest.mark.asyncio
async def test_swaps_max_tokens_then_drops_temperature_for_newer_models():
    """gpt-5 / o-series reject ``max_tokens`` and non-default temperature; the
    provider adapts both, surgically, and retries."""
    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(dict(kwargs))
        if "max_tokens" in kwargs:
            raise _bad_request(
                "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens'.")
        if kwargs.get("temperature") not in (None, 1):
            raise _bad_request(
                "Unsupported value: 'temperature' does not support 0.0; only 1 is supported.")
        return _ok()

    fake = MagicMock()
    fake.chat.completions.create = create
    with patch("app.services.ai.llm.openai_compat.AsyncOpenAI", return_value=fake):
        # Construct under the patch so the mocked client is used (the client is
        # built eagerly in __init__).
        prov = OpenAICompatProvider(
            name="openai", api_key="k", base_url="https://api.openai.com/v1",
            model_default="gpt-5.4-mini",
        )
        resp = await prov.complete(LLMRequest(
            messages=[LLMMessage("user", "hi")], model="",
            max_output_tokens=16, temperature=0.0))

    assert resp.text == "ok"
    assert "max_tokens" in calls[0] and "max_completion_tokens" not in calls[0]
    assert "max_completion_tokens" in calls[1]      # swapped
    assert "temperature" not in calls[2]            # dropped on the next retry
