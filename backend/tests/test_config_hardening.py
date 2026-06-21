"""W1 — fail-closed production config + secret-strength validation (SEC-CFG-01 / GOV-06 / CRYPTO-03).

The production secret validator must do more than reject the single literal default:
it must enforce JWT secret *strength* and a correctly-sized encryption key, and it must
treat any non-development APP_ENV (including unknown values) as production (fail-closed).
"""
from __future__ import annotations

import pytest

from app.config import Settings

# A 64-hex-char value decodes to exactly 32 bytes (AES-256).
VALID_KEY = "ab" * 32
STRONG_SECRET = "x" * 48


def test_production_rejects_default_secret():
    """Regression: the literal default secret is rejected in production."""
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            jwt_secret_key="change-me-in-production",
            database_encryption_key=VALID_KEY,
        )


def test_production_rejects_short_jwt_secret():
    """A non-default but too-short secret (< 32 chars) is rejected in production."""
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            jwt_secret_key="tooshort",
            database_encryption_key=VALID_KEY,
        )


def test_production_rejects_encryption_key_not_32_bytes():
    """A key that does not decode to exactly 32 bytes is rejected (no silent AES-128)."""
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            jwt_secret_key=STRONG_SECRET,
            database_encryption_key="abcd",  # 2 bytes
        )


def test_production_rejects_non_hex_encryption_key():
    """A non-hex key is rejected rather than silently truncated."""
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            jwt_secret_key=STRONG_SECRET,
            database_encryption_key="not-hex-at-all-zz",
        )


def test_production_accepts_strong_secrets():
    """Proper 32+ char secret and a 32-byte hex key are accepted."""
    s = Settings(
        app_env="production",
        jwt_secret_key=STRONG_SECRET,
        database_encryption_key=VALID_KEY,
    )
    assert s.is_production is True


def test_unknown_app_env_treated_as_production():
    """Fail-closed: an unrecognized APP_ENV runs the production checks."""
    with pytest.raises(ValueError):
        Settings(
            app_env="staging",
            jwt_secret_key="change-me-in-production",
            database_encryption_key=VALID_KEY,
        )


def test_development_allows_defaults():
    """Local development keeps its insecure-default ergonomics."""
    s = Settings(app_env="development", jwt_secret_key="change-me-in-production")
    assert s.is_production is False
    assert s.jwt_secret_key == "change-me-in-production"
