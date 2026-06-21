from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# 1 year, applies to subdomains. Kept consistent with the value documented in
# HIPAA Compliance → Security headers.
HSTS_VALUE = "max-age=31536000; includeSubDomains"


def should_emit_hsts(
    is_production: bool, scheme: str, forwarded_proto: str | None = None
) -> bool:
    """Whether to emit the ``Strict-Transport-Security`` header (SEC-API-01).

    In production the app almost always runs behind a TLS-terminating proxy, so
    it observes a plain ``http`` scheme even though the browser connection is
    HTTPS. Gating HSTS on ``scheme == "https"`` (the old behavior) therefore
    meant the header was NEVER sent in that topology — the exact gap SEC-API-01
    flags. So in production we emit HSTS unconditionally.

    In development the app never terminates TLS itself, so HSTS stays effectively
    off: it is emitted only on an actual https request (or an https
    ``X-Forwarded-Proto``), preserving prior dev behavior.
    """
    if is_production:
        return True
    proto = (forwarded_proto or scheme or "").split(",")[0].strip().lower()
    return proto == "https"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"
        )
        if should_emit_hsts(
            settings.is_production,
            request.url.scheme,
            request.headers.get("x-forwarded-proto"),
        ):
            response.headers["Strict-Transport-Security"] = HSTS_VALUE
        return response
