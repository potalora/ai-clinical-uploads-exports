"""W2 — token-revocation must not be bypassable by the Authorization scheme casing (SEC-AUTH-01).

HTTPBearer matches the scheme case-insensitively, so ``bearer <token>`` authenticates.
The revocation guard must check the blacklist on that same (single) decode path — a
revoked/ logged-out access token must be rejected regardless of ``Bearer`` vs ``bearer``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import decode_token
from app.models.token_blacklist import RevokedToken
from tests.conftest import auth_headers


async def _revoke(db_session: AsyncSession, token: str, user_id: str) -> None:
    payload = decode_token(token)
    db_session.add(
        RevokedToken(
            jti=payload["jti"],
            user_id=UUID(user_id),
            token_type="access",
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_revoked_token_rejected_with_lowercase_bearer(
    client: AsyncClient, db_session: AsyncSession
):
    headers, user_id = await auth_headers(client, "revoke-lower@example.com")
    token = headers["Authorization"].split(" ", 1)[1]
    await _revoke(db_session, token, user_id)

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"bearer {token}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_revoked_token_rejected_with_capital_bearer(
    client: AsyncClient, db_session: AsyncSession
):
    headers, user_id = await auth_headers(client, "revoke-capital@example.com")
    token = headers["Authorization"].split(" ", 1)[1]
    await _revoke(db_session, token, user_id)

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_accepted_with_lowercase_bearer(
    client: AsyncClient, db_session: AsyncSession
):
    """A non-revoked token still works under either casing (no false lockout)."""
    headers, _ = await auth_headers(client, "valid-lower@example.com")
    token = headers["Authorization"].split(" ", 1)[1]

    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"bearer {token}"}
    )
    assert resp.status_code == 200
