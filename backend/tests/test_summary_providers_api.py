from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, create_test_patient


@pytest.mark.asyncio
async def test_list_providers_returns_known_providers(client: AsyncClient):
    """GET /summary/providers lists the selectable providers and a default."""
    headers, uid = await auth_headers(client)

    resp = await client.get("/api/v1/summary/providers", headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    names = {p["name"] for p in data["providers"]}
    assert {"gemini", "openai", "anthropic", "ollama", "lmstudio"} <= names

    assert isinstance(data["default"], str)
    assert data["default"]


@pytest.mark.asyncio
async def test_list_providers_never_leaks_api_keys(client: AsyncClient, db_session):
    """The provider list must never expose API keys in any form."""
    headers, uid = await auth_headers(client)
    # Make sure the user owns a patient (parity with other summary tests).
    await create_test_patient(db_session, uid)

    resp = await client.get("/api/v1/summary/providers", headers=headers)
    assert resp.status_code == 200

    text = resp.text
    assert "api_key" not in text
    assert "sk-" not in text


@pytest.mark.asyncio
async def test_list_providers_unauthenticated(client: AsyncClient):
    """GET /summary/providers without a token returns 401."""
    resp = await client.get("/api/v1/summary/providers")
    assert resp.status_code == 401
