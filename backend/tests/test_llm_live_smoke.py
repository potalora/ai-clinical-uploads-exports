"""Live provider smoke tests.

Each test makes ONE real unary completion against a provider and asserts a
non-empty reply. Every test is gated on credential/server presence and SKIPS
when the provider isn't configured, so the suite stays green on machines
without keys or local servers. Marked ``slow`` so the fast suite never calls
out to the network.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.services.ai.llm.registry import _build
from app.services.ai.llm.types import LLMMessage, LLMRateLimitError, LLMRequest

pytestmark = pytest.mark.slow


def _server_up(base_url: str, path: str) -> bool:
    """Return True if a local OpenAI-compatible server answers at base_url+path."""
    try:
        url = base_url.rstrip("/").removesuffix("/v1") + path
        httpx.get(url, timeout=2.0)
        return True
    except Exception:
        return False


def _ollama_up() -> bool:
    return _server_up(settings.ollama_base_url, "/api/tags")


def _lmstudio_up() -> bool:
    try:
        httpx.get(settings.lmstudio_base_url.rstrip("/") + "/models", timeout=2.0)
        return True
    except Exception:
        return False


async def _smoke(name: str) -> None:
    provider = _build(name)
    try:
        response = await provider.complete(
            LLMRequest(
                messages=[LLMMessage("user", "Reply with the single word: ok")],
                model="",
                max_output_tokens=32,
                temperature=0.0,
            )
        )
    except LLMRateLimitError as exc:
        # A 429 (e.g. OpenAI ``insufficient_quota``) is returned only AFTER the
        # provider authenticates the request, so the integration is proven —
        # it's an account/billing state, not a code failure. Skip rather than
        # fail so the live smoke stays meaningful without paid quota.
        pytest.skip(f"{name}: provider reached but rate-limited/quota-exhausted ({exc})")
    assert response.text.strip(), f"{name} returned empty text"
    assert response.model, f"{name} returned no model id"


@pytest.mark.asyncio
@pytest.mark.skipif(not settings.gemini_api_key, reason="no GEMINI_API_KEY")
async def test_gemini_smoke() -> None:
    await _smoke("gemini")


@pytest.mark.asyncio
@pytest.mark.skipif(not settings.openai_api_key, reason="no OPENAI_API_KEY")
async def test_openai_smoke() -> None:
    await _smoke("openai")


@pytest.mark.asyncio
@pytest.mark.skipif(not settings.anthropic_api_key, reason="no ANTHROPIC_API_KEY")
async def test_anthropic_smoke() -> None:
    await _smoke("anthropic")


@pytest.mark.asyncio
@pytest.mark.skipif(not settings.openrouter_api_key, reason="no OPENROUTER_API_KEY")
async def test_openrouter_smoke() -> None:
    await _smoke("openrouter")


@pytest.mark.asyncio
@pytest.mark.skipif(not _ollama_up(), reason="ollama server not reachable")
async def test_ollama_smoke() -> None:
    await _smoke("ollama")


@pytest.mark.asyncio
@pytest.mark.skipif(not _lmstudio_up(), reason="lmstudio server not reachable")
async def test_lmstudio_smoke() -> None:
    await _smoke("lmstudio")
