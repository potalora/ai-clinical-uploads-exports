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


# --- W3: logout must revoke the refresh token, not just the access token ---


async def _register_and_login(client: AsyncClient, email: str) -> tuple[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass123!", "display_name": "T"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SecurePass123!"}
    )
    body = login.json()
    return body["access_token"], body["refresh_token"]


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient):
    access, refresh = await _register_and_login(client, "logout-refresh@example.com")

    resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": refresh},
    )
    assert resp.status_code == 204

    # The refresh token must no longer mint new sessions.
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_body_still_revokes_access(client: AsyncClient):
    """Back-compat: logout with no body still revokes the access token."""
    access, _ = await _register_and_login(client, "logout-nobody@example.com")
    headers = {"Authorization": f"Bearer {access}"}

    resp = await client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 204

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_logout_ignores_another_users_refresh_token(client: AsyncClient):
    """A user cannot revoke a different user's refresh token via logout."""
    access_a, _ = await _register_and_login(client, "logout-a@example.com")
    _, refresh_b = await _register_and_login(client, "logout-b@example.com")

    resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_a}"},
        json={"refresh_token": refresh_b},
    )
    assert resp.status_code == 204

    # B's refresh token is untouched.
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_b})
    assert r2.status_code == 200
