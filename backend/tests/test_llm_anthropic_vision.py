# backend/tests/test_llm_anthropic_vision.py
from __future__ import annotations
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.ai.llm.anthropic import AnthropicProvider
from app.services.ai.llm.types import (
    DocumentPart, ImagePart, LLMMessage, LLMRequest, TextPart,
)


def _fake_resp(text="ok"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="claude-x")


@pytest.mark.asyncio
async def test_anthropic_sends_pdf_document_block():
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=_fake_resp())
    with patch("app.services.ai.llm.anthropic.AsyncAnthropic", return_value=fake):
        prov = AnthropicProvider(api_key="k", model_default="claude-x")
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("Extract"),
                                          DocumentPart(b"%PDF-1.4", "application/pdf")])],
            model="claude-x", max_output_tokens=64))
    blocks = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    doc = next(b for b in blocks if b["type"] == "document")
    assert doc["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(doc["source"]["data"]) == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_anthropic_sends_image_block():
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=_fake_resp())
    with patch("app.services.ai.llm.anthropic.AsyncAnthropic", return_value=fake):
        prov = AnthropicProvider(api_key="k", model_default="claude-x")
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("Describe"),
                                          ImagePart(b"\x89PNG", "image/png")])],
            model="claude-x", max_output_tokens=64))
    blocks = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    text = next(b for b in blocks if b["type"] == "text")
    assert text["text"] == "Describe"
    img = next(b for b in blocks if b["type"] == "image")
    assert img["source"]["media_type"] == "image/png"
    assert base64.b64decode(img["source"]["data"]) == b"\x89PNG"


@pytest.mark.asyncio
async def test_anthropic_plain_str_stays_string():
    """Text-only calls remain byte-identical: content is a plain string, not blocks."""
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=_fake_resp())
    with patch("app.services.ai.llm.anthropic.AsyncAnthropic", return_value=fake):
        prov = AnthropicProvider(api_key="k", model_default="claude-x")
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", "hello")], model="claude-x", max_output_tokens=64))
    content = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    assert content == "hello"


@pytest.mark.asyncio
async def test_anthropic_single_textpart_stays_string():
    """A single TextPart collapses to a plain string for parity with str content."""
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=_fake_resp())
    with patch("app.services.ai.llm.anthropic.AsyncAnthropic", return_value=fake):
        prov = AnthropicProvider(api_key="k", model_default="claude-x")
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("hello")])],
            model="claude-x", max_output_tokens=64))
    content = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    assert content == "hello"


@pytest.mark.asyncio
async def test_anthropic_json_mode_prefill_preserved_with_parts():
    """json_mode still appends the assistant '{' prefill turn alongside part content."""
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=_fake_resp(text='"a": 1}'))
    with patch("app.services.ai.llm.anthropic.AsyncAnthropic", return_value=fake):
        prov = AnthropicProvider(api_key="k", model_default="claude-x")
        resp = await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("give json"),
                                          ImagePart(b"IMG", "image/png")])],
            model="claude-x", max_output_tokens=64, json_mode=True))
    assert resp.text.startswith("{")
    sent = fake.messages.create.call_args.kwargs
    assert sent["messages"][-1] == {"role": "assistant", "content": "{"}
    assert sent["system"].endswith("opening brace.")
