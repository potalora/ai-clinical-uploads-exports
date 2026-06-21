# LLM Settings Pane (Part 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user-facing settings pane (Admin → System) where each user enters/saves API keys (encrypted per-user in the DB), configures providers, picks default + per-operation provider, tests connections, and switches live — with the LLM registry resolving per-user config (falling back to `.env`).

**Architecture:** Two new per-user tables (`llm_provider_configs`, `user_llm_preferences`); a `LLMConfig` resolver that merges user DB rows over global `.env`; the registry gains `get_provider(operation, config)` and caches by `(name, base_url, model, key-hash)`; a `LLMConfig` is loaded once per request/job and threaded into the four LLM call sites; a `/settings/llm` API (keys encrypted, masked, never logged); an "AI providers" card in the Admin System tab.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, AES-256-GCM (`app/middleware/encryption.py`), pytest/pytest-asyncio, Next.js/TS.

## Global Constraints

- Keys encrypted at rest with `encrypt_field`/`decrypt_field` (AES-256-GCM, `DATABASE_ENCRYPTION_KEY`). **Never** return a key in plaintext (mask), **never** log a key, decrypt only server-side at call time.
- Every settings query MUST filter by `user_id` (row-level security). User B can never read/modify/test user A's config.
- De-identify before EVERY provider call — unchanged. Routing through config does not relax it.
- Back-compat: a user with no DB config behaves exactly as today (all fields fall back to `.env`; default provider `gemini`).
- New migration chains from Alembic head `e1f2a3b4c5d6`. Test DB is `create_all`-managed — also run the migration on dev + `psql medtimeline_test` (new tables are created by `create_all`, but ship the migration).
- Type hints + `from __future__ import annotations`; Google-style docstrings; no bare except; `logging` not print; Ruff 100-char.
- Audit every settings endpoint (action + provider name only; never the key).
- Run tests via `backend/.venv/bin/python -m pytest`. DB-touching tests run serially (not concurrent with other DB tests).

---

### Task 1: DB models + migration

**Files:**
- Create: `backend/app/models/llm_settings.py`
- Modify: `backend/app/models/__init__.py` (export new models so `Base.metadata` sees them)
- Create: `backend/alembic/versions/f2a3b4c5d6e7_add_llm_settings_tables.py`
- Test: `backend/tests/test_llm_settings_models.py`

**Interfaces:**
- Produces: `LLMProviderConfig(id, user_id, provider, api_key_encrypted: bytes|None, base_url: str|None, model: str|None, enabled: bool, created_at, updated_at)` with unique `(user_id, provider)`; `UserLLMPreferences(id, user_id unique, default_provider, summary_provider, section_provider, dedup_provider, extraction_provider, vision_provider, extraction_engine, created_at, updated_at)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_settings_models.py
from __future__ import annotations
import pytest
from uuid import uuid4
from sqlalchemy import select
from app.models.llm_settings import LLMProviderConfig, UserLLMPreferences
from app.models.user import User
from app.middleware.encryption import encrypt_field, decrypt_field


@pytest.mark.asyncio
async def test_provider_config_roundtrip_encrypted_key(db_session):
    user = User(email_encrypted=encrypt_field("a@b.com"), password_hash="x")
    db_session.add(user); await db_session.flush()
    row = LLMProviderConfig(user_id=user.id, provider="openai",
                            api_key_encrypted=encrypt_field("sk-secret"),
                            base_url=None, model="gpt-4o-mini", enabled=True)
    db_session.add(row); await db_session.commit()
    got = (await db_session.execute(
        select(LLMProviderConfig).where(LLMProviderConfig.user_id == user.id))
    ).scalar_one()
    assert got.api_key_encrypted != b"sk-secret"            # stored as ciphertext
    assert decrypt_field(got.api_key_encrypted) == "sk-secret"
    assert got.provider == "openai" and got.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_preferences_one_row_per_user(db_session):
    user = User(email_encrypted=encrypt_field("c@d.com"), password_hash="x")
    db_session.add(user); await db_session.flush()
    pref = UserLLMPreferences(user_id=user.id, default_provider="anthropic")
    db_session.add(pref); await db_session.commit()
    got = (await db_session.execute(
        select(UserLLMPreferences).where(UserLLMPreferences.user_id == user.id))
    ).scalar_one()
    assert got.default_provider == "anthropic"
    assert got.summary_provider is None
```

(Check the real `User` constructor fields in `app/models/user.py` and adapt the user creation to match — the email column may be `email_encrypted` bytes; mirror `create_test_patient`/existing tests.)

- [ ] **Step 2: Run to verify it fails** → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement the models**

```python
# backend/app/models/llm_settings.py
from __future__ import annotations
from datetime import datetime
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_configs"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_llm_user_provider"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserLLMPreferences(Base):
    __tablename__ = "user_llm_preferences"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False)
    default_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    section_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dedup_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extraction_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vision_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extraction_engine: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

Add both to `backend/app/models/__init__.py` imports/`__all__` (match the existing export style there). Verify `base.Base` is the right import (mirror `app/models/patient.py`).

- [ ] **Step 4: Write the Alembic migration**

```python
# backend/alembic/versions/f2a3b4c5d6e7_add_llm_settings_tables.py
"""add llm settings tables

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "provider", name="uq_llm_user_provider"),
    )
    op.create_index("ix_llm_provider_configs_user_id", "llm_provider_configs", ["user_id"])
    op.create_table(
        "user_llm_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("default_provider", sa.String(32), nullable=True),
        sa.Column("summary_provider", sa.String(32), nullable=True),
        sa.Column("section_provider", sa.String(32), nullable=True),
        sa.Column("dedup_provider", sa.String(32), nullable=True),
        sa.Column("extraction_provider", sa.String(32), nullable=True),
        sa.Column("vision_provider", sa.String(32), nullable=True),
        sa.Column("extraction_engine", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_llm_preferences_user_id", "user_llm_preferences", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_llm_preferences_user_id", "user_llm_preferences")
    op.drop_table("user_llm_preferences")
    op.drop_index("ix_llm_provider_configs_user_id", "llm_provider_configs")
    op.drop_table("llm_provider_configs")
```

- [ ] **Step 5: Apply migration to dev + test DBs, run tests**

```bash
cd backend && .venv/bin/alembic upgrade head
# test DB: create_all makes the tables, but apply the migration too for parity
DATABASE_URL="${DATABASE_URL}_test" .venv/bin/alembic upgrade head 2>/dev/null || true
.venv/bin/python -m pytest tests/test_llm_settings_models.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/llm_settings.py backend/app/models/__init__.py \
        backend/alembic/versions/f2a3b4c5d6e7_add_llm_settings_tables.py backend/tests/test_llm_settings_models.py
git commit -m "feat(llm-settings): per-user provider config + preferences tables"
```

---

### Task 2: LLMConfig resolver

**Files:**
- Create: `backend/app/services/ai/llm/config.py`
- Test: `backend/tests/test_llm_config_resolver.py`

**Interfaces:**
- Consumes: `settings` (global); models from Task 1.
- Produces:
  - `@dataclass ProviderCreds(api_key: str = "", base_url: str = "", model: str = "", enabled: bool = True)`
  - `@dataclass LLMConfig(routing: dict[str, str], providers: dict[str, ProviderCreds])`
  - `LLMConfig.from_settings() -> LLMConfig` (classmethod; global `.env`)
  - `async def load_llm_config(db, user_id) -> LLMConfig`
  - `ROUTING_OPS = ("default","summary","section","dedup","extraction","vision")`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_config_resolver.py
from __future__ import annotations
import pytest
from uuid import uuid4
from app.services.ai.llm.config import LLMConfig, ProviderCreds, load_llm_config
from app.models.llm_settings import LLMProviderConfig, UserLLMPreferences
from app.models.user import User
from app.middleware.encryption import encrypt_field


def test_from_settings_has_gemini_default(monkeypatch):
    from app.services.ai.llm import config as cfg
    monkeypatch.setattr(cfg.settings, "llm_provider", "gemini")
    monkeypatch.setattr(cfg.settings, "gemini_api_key", "g-key")
    c = LLMConfig.from_settings()
    assert c.routing["default"] == "gemini"
    assert c.providers["gemini"].api_key == "g-key"


@pytest.mark.asyncio
async def test_user_row_overrides_env(db_session, monkeypatch):
    from app.services.ai.llm import config as cfg
    monkeypatch.setattr(cfg.settings, "llm_provider", "gemini")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "env-openai")
    user = User(email_encrypted=encrypt_field("z@z.com"), password_hash="x")
    db_session.add(user); await db_session.flush()
    db_session.add(LLMProviderConfig(user_id=user.id, provider="openai",
                                     api_key_encrypted=encrypt_field("user-openai"),
                                     model="gpt-4o", enabled=True))
    db_session.add(UserLLMPreferences(user_id=user.id, default_provider="openai",
                                      summary_provider="anthropic"))
    await db_session.commit()
    c = await load_llm_config(db_session, user.id)
    assert c.routing["default"] == "openai"          # user pref
    assert c.routing["summary"] == "anthropic"        # per-op override
    assert c.providers["openai"].api_key == "user-openai"   # decrypted user key
    assert c.providers["openai"].model == "gpt-4o"
    # provider with no user row falls back to env
    assert c.providers["gemini"].api_key == cfg.settings.gemini_api_key


@pytest.mark.asyncio
async def test_no_user_config_equals_settings(db_session):
    user = User(email_encrypted=encrypt_field("y@y.com"), password_hash="x")
    db_session.add(user); await db_session.flush(); await db_session.commit()
    c = await load_llm_config(db_session, user.id)
    base = LLMConfig.from_settings()
    assert c.routing["default"] == base.routing["default"]
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement config.py**

```python
# backend/app/services/ai/llm/config.py
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.middleware.encryption import decrypt_field
from app.models.llm_settings import LLMProviderConfig, UserLLMPreferences

logger = logging.getLogger(__name__)

ROUTING_OPS = ("default", "summary", "section", "dedup", "extraction", "vision")
_KNOWN = ("gemini", "vertex", "openai", "anthropic", "openrouter", "ollama", "lmstudio")


@dataclass
class ProviderCreds:
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    enabled: bool = True


@dataclass
class LLMConfig:
    routing: dict[str, str] = field(default_factory=dict)
    providers: dict[str, "ProviderCreds"] = field(default_factory=dict)

    @classmethod
    def from_settings(cls) -> "LLMConfig":
        routing = {"default": settings.llm_provider or "gemini"}
        for op in ("summary", "section", "dedup", "extraction"):
            routing[op] = getattr(settings, f"llm_{op}_provider", "") or routing["default"]
        routing["vision"] = routing["default"]  # vision pref added by user prefs only
        providers = {
            "gemini": ProviderCreds(settings.gemini_api_key, "", settings.gemini_model),
            "vertex": ProviderCreds("", "", settings.vertex_model),
            "openai": ProviderCreds(settings.openai_api_key, settings.openai_base_url,
                                    settings.openai_model),
            "anthropic": ProviderCreds(settings.anthropic_api_key, "", settings.anthropic_model),
            "openrouter": ProviderCreds(settings.openrouter_api_key, settings.openrouter_base_url,
                                        settings.openrouter_model),
            "ollama": ProviderCreds("", settings.ollama_base_url, settings.ollama_model),
            "lmstudio": ProviderCreds("", settings.lmstudio_base_url, settings.lmstudio_model),
        }
        return cls(routing=routing, providers=providers)


async def load_llm_config(db: AsyncSession, user_id: UUID) -> LLMConfig:
    """Merge a user's saved provider config + routing over the global .env defaults."""
    cfg = LLMConfig.from_settings()
    rows = (await db.execute(
        select(LLMProviderConfig).where(LLMProviderConfig.user_id == user_id))).scalars().all()
    for row in rows:
        if row.provider not in cfg.providers:
            continue
        base = cfg.providers[row.provider]
        key = base.api_key
        if row.api_key_encrypted:
            try:
                key = decrypt_field(row.api_key_encrypted)
            except Exception:
                logger.warning("failed to decrypt stored key for provider %s", row.provider)
        cfg.providers[row.provider] = ProviderCreds(
            api_key=key,
            base_url=row.base_url or base.base_url,
            model=row.model or base.model,
            enabled=row.enabled,
        )
    pref = (await db.execute(
        select(UserLLMPreferences).where(UserLLMPreferences.user_id == user_id))
    ).scalar_one_or_none()
    if pref:
        if pref.default_provider:
            cfg.routing["default"] = pref.default_provider
        for op in ("summary", "section", "dedup", "extraction", "vision"):
            val = getattr(pref, f"{op}_provider", None)
            cfg.routing[op] = val or cfg.routing.get(op) or cfg.routing["default"]
    return cfg
```

- [ ] **Step 4: Run tests** → PASS. **Step 5: Commit**

```bash
git add backend/app/services/ai/llm/config.py backend/tests/test_llm_config_resolver.py
git commit -m "feat(llm-settings): LLMConfig resolver (user DB over .env fallback)"
```

---

### Task 3: Registry reads per-user config

**Files:**
- Modify: `backend/app/services/ai/llm/registry.py`
- Modify: `backend/app/services/ai/llm/__init__.py` (export `LLMConfig`, `load_llm_config`, `ProviderCreds`)
- Test: `backend/tests/test_llm_registry_config.py` (existing `test_llm_registry.py` must still pass)

**Interfaces:**
- Consumes: `LLMConfig`, `ProviderCreds` (Task 2).
- Produces: `get_provider(operation=None, config: LLMConfig | None = None) -> LLMProvider`; `provider_name_for(operation, config=None) -> str`; `_build(name, config) -> LLMProvider`; `available_providers(config=None) -> list[dict]`. Cache keyed by `(name, base_url, model, sha256(api_key))`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_registry_config.py
from __future__ import annotations
from app.services.ai.llm import registry
from app.services.ai.llm.config import LLMConfig, ProviderCreds
from app.services.ai.llm.openai_compat import OpenAICompatProvider
from app.services.ai.llm.anthropic import AnthropicProvider


def _cfg(default, providers):
    routing = {"default": default}
    for op in ("summary", "section", "dedup", "extraction", "vision"):
        routing[op] = default
    return LLMConfig(routing=routing, providers=providers)


def test_get_provider_uses_config_routing_and_creds():
    cfg = _cfg("anthropic", {"anthropic": ProviderCreds(api_key="k", model="claude-x")})
    prov = registry.get_provider("summary", cfg)
    assert isinstance(prov, AnthropicProvider)


def test_cache_distinguishes_keys():
    registry.reset_cache()
    a = registry.get_provider("summary", _cfg("openai",
        {"openai": ProviderCreds(api_key="k1", base_url="http://x/v1", model="m")}))
    b = registry.get_provider("summary", _cfg("openai",
        {"openai": ProviderCreds(api_key="k2", base_url="http://x/v1", model="m")}))
    assert a is not b   # different key => different cached client (no cross-user leak)
    c = registry.get_provider("summary", _cfg("openai",
        {"openai": ProviderCreds(api_key="k1", base_url="http://x/v1", model="m")}))
    assert a is c       # identical creds reuse


def test_back_compat_no_config_uses_settings(monkeypatch):
    monkeypatch.setattr(registry.settings, "llm_provider", "gemini")
    registry.reset_cache()
    prov = registry.get_provider("summary")  # no config
    assert prov.name == "gemini"
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Rewrite registry.py to be config-driven**

Key changes (keep `KNOWN_PROVIDERS`, `_OPENAI_FAMILY`, error types):
```python
import hashlib
from app.services.ai.llm.config import LLMConfig, ProviderCreds

def provider_name_for(operation: str | None, config: LLMConfig | None = None) -> str:
    cfg = config or LLMConfig.from_settings()
    if operation and operation in cfg.routing and cfg.routing[operation]:
        return cfg.routing[operation]
    return cfg.routing.get("default", "gemini")

def _creds(name: str, config: LLMConfig) -> ProviderCreds:
    return config.providers.get(name, ProviderCreds())

def _build(name: str, config: LLMConfig) -> LLMProvider:
    creds = _creds(name, config)
    if name == "gemini":
        return GeminiProvider(api_key=creds.api_key, model_default=creds.model or settings.gemini_model)
    if name == "vertex":
        return GeminiProvider(vertexai=True, project=settings.vertex_project,
                              location=settings.vertex_location,
                              model_default=creds.model or settings.vertex_model)
    if name == "anthropic":
        return AnthropicProvider(api_key=creds.api_key,
                                 model_default=creds.model or settings.anthropic_model)
    if name in _OPENAI_FAMILY:
        return OpenAICompatProvider(name=name, api_key=creds.api_key or "local",
                                    base_url=creds.base_url, model_default=creds.model)
    raise LLMBadRequestError(f"Unknown LLM provider: {name!r}")

def _cache_key(name: str, creds: ProviderCreds) -> str:
    h = hashlib.sha256((creds.api_key or "").encode()).hexdigest()[:16]
    return f"{name}|{creds.base_url}|{creds.model}|{h}"

def get_provider(operation: str | None = None, config: LLMConfig | None = None) -> LLMProvider:
    cfg = config or LLMConfig.from_settings()
    name = provider_name_for(operation, cfg)
    if name not in KNOWN_PROVIDERS:
        raise LLMBadRequestError(f"Unknown LLM provider: {name!r}")
    key = _cache_key(name, _creds(name, cfg))
    if key not in _cache:
        _cache[key] = _build(name, cfg)
    return _cache[key]

def available_providers(config: LLMConfig | None = None) -> list[dict]:
    cfg = config or LLMConfig.from_settings()
    out = []
    for name in ("gemini", "openai", "anthropic", "openrouter", "vertex", "ollama", "lmstudio"):
        creds = cfg.providers.get(name, ProviderCreds())
        is_local = name in ("ollama", "lmstudio")
        configured = bool(creds.api_key) or is_local or (name == "vertex" and bool(settings.vertex_project))
        out.append({"name": name, "model": creds.model or "(default)",
                    "supports_vision": name in ("gemini", "vertex", "anthropic", "openai", "openrouter"),
                    "is_local": is_local, "configured": configured})
    return out
```

Keep `resolve_model` for any external callers (have it read settings as before, or mark legacy). Update `__init__.py` to export `LLMConfig`, `ProviderCreds`, `load_llm_config`.

- [ ] **Step 4: Update existing `test_llm_registry.py`**

The old tests call `get_provider(op)` with global settings + monkeypatch — those still work (no-config path uses `from_settings()`), but tests that monkeypatch `settings.llm_summary_provider` etc. still pass because `from_settings()` reads them. Run it; fix only what breaks (likely the unknown-provider test still works since `from_settings()` carries the bogus `llm_provider`). Verify.

- [ ] **Step 5: Run tests** → PASS (`tests/test_llm_registry.py tests/test_llm_registry_config.py`). **Step 6: Commit**

```bash
git add backend/app/services/ai/llm/registry.py backend/app/services/ai/llm/__init__.py backend/tests/test_llm_registry_config.py backend/tests/test_llm_registry.py
git commit -m "feat(llm-settings): registry resolves per-user LLMConfig (cache keyed by creds)"
```

---

### Task 4: Thread LLMConfig into the four call sites

**Files:**
- Modify: `backend/app/services/ai/summarizer.py` (load config, pass to get_provider)
- Modify: `backend/app/services/extraction/section_parser.py` (+`config` param)
- Modify: `backend/app/services/extraction/entity_extractor.py` + `generic_entity_extractor.py` (+`config`)
- Modify: `backend/app/services/dedup/llm_judge.py` (+`config`) + `orchestrator.py` (load + thread)
- Modify: `backend/app/api/upload.py` (load config in the two extraction engines; pass to parse_sections + extract_entities_async)
- Test: `backend/tests/test_provider_config_threading.py`

**Interfaces:**
- Consumes: `load_llm_config`, `LLMConfig`, `get_provider(op, config)`.
- Produces: each operation accepts an optional `config: LLMConfig | None = None`; when None it falls back to `from_settings()` (back-compat). `get_provider` always called with the config.

- [ ] **Step 1: Write the failing test** (config selects the provider end-to-end through summarizer)

```python
# backend/tests/test_provider_config_threading.py
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
from app.services.ai.llm.config import LLMConfig, ProviderCreds
from app.services.ai.llm.types import LLMResponse, LLMUsage


@pytest.mark.asyncio
async def test_summary_loads_user_config(db_session, monkeypatch):
    # A user with an anthropic default should route summary to anthropic.
    from app.services.ai import summarizer
    fake = AsyncMock()
    fake.complete.return_value = LLMResponse(text="ok", finish_reason="stop",
                                             model="claude-x", usage=LLMUsage(1,1,2), raw=None)
    # seed a user + patient + records (reuse conftest helpers), set anthropic config
    # ... (mirror tests/test_summarizer_provider.py setup) ...
    async def fake_load(db, uid):
        return LLMConfig(routing={"default":"anthropic","summary":"anthropic"},
                         providers={"anthropic": ProviderCreds(api_key="k", model="claude-x")})
    with patch.object(summarizer, "load_llm_config", fake_load), \
         patch.object(summarizer, "get_provider", return_value=fake):
        out = await summarizer.generate_summary(db_session, user_id, patient_id)
    assert out["model_used"] == "claude-x"
    # get_provider was called WITH a config object
    assert summarizer.get_provider.call_args.args[0] == "summary"
```

(Adapt user/patient/record seeding from `tests/test_summarizer_provider.py`.)

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement threading**

- `summarizer.generate_summary`: at the top of the provider section, `config = await load_llm_config(db, user_id)`; `llm = get_provider("summary", config) if provider is None else _provider_by_name(provider, config)`. Import `load_llm_config`, `LLMConfig`. `_provider_by_name` gains a `config` param (build via `_build(name, config)`).
- `section_parser.parse_sections(text, api_key, config=None)`; inside, `get_provider("section", config or LLMConfig.from_settings())`.
- `entity_extractor.extract_entities_async(..., config=None)`: pass to `provider_name_for("extraction", config)` and `generic_extract_entities_async(..., config=config)`; the LangExtract branch keeps using `api_key` (Part 3 will route it).
- `generic_entity_extractor.generic_extract_entities_async(..., config=None)`: `get_provider("extraction", config or LLMConfig.from_settings())`.
- `llm_judge.judge_candidate_pair(..., api_key, config=None)` and `judge_candidates_batch(..., config=None)`: `get_provider("dedup", config or LLMConfig.from_settings())`.
- `orchestrator.run_upload_dedup`: `config = await load_llm_config(db, user_id)`; thread into `_run_llm_judge(db, candidates, config)` → `judge_candidates_batch(pairs, api_key, config=config)`.
- `api/upload.py` `_run_gemini_extraction_engine` / `_run_local_extraction_engine`: `config = await load_llm_config(db, user_id)` once; pass into `parse_sections(text, api_key, config=config)` and `extract_entities_async(..., config=config)`.

- [ ] **Step 4: Run tests** + the existing summarizer/section/judge/entity tests (they pass `config=None` → from_settings, unchanged behavior).

Run: `cd backend && .venv/bin/python -m pytest tests/test_provider_config_threading.py tests/test_summarizer_provider.py tests/test_section_parser_provider.py tests/test_llm_judge_provider.py tests/test_generic_entity_extract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/summarizer.py backend/app/services/extraction/section_parser.py \
  backend/app/services/extraction/entity_extractor.py backend/app/services/extraction/generic_entity_extractor.py \
  backend/app/services/dedup/llm_judge.py backend/app/services/dedup/orchestrator.py backend/app/api/upload.py \
  backend/tests/test_provider_config_threading.py
git commit -m "feat(llm-settings): thread per-user LLMConfig into all four call sites"
```

---

### Task 5: Settings API

**Files:**
- Create: `backend/app/api/llm_settings.py`
- Create: `backend/app/schemas/llm_settings.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/tests/test_llm_settings_api.py`

**Interfaces:**
- Routes under `/settings/llm` (full path `/api/v1/settings/llm`), auth `Depends(get_authenticated_user_id)`, db `Depends(get_db)`, audited via `log_audit_event` (mirror `api/summary.py`). Keys masked/never returned/never logged.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_llm_settings_api.py
from __future__ import annotations
import pytest
from sqlalchemy import select
from app.models.llm_settings import LLMProviderConfig
from app.middleware.encryption import decrypt_field
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_get_settings_masks_keys(client, db_session):
    headers, uid = await auth_headers(client)
    await client.put("/api/v1/settings/llm/providers/openai",
                     json={"api_key": "sk-supersecretvalue", "model": "gpt-4o"}, headers=headers)
    r = await client.get("/api/v1/settings/llm", headers=headers)
    assert r.status_code == 200
    assert "sk-supersecretvalue" not in r.text           # never returned plaintext
    openai = next(p for p in r.json()["providers"] if p["name"] == "openai")
    assert openai["has_key"] is True and openai["model"] == "gpt-4o"
    assert openai["key_masked"] and openai["key_masked"].endswith("alue") is False  # masked


@pytest.mark.asyncio
async def test_put_encrypts_key_in_db(client, db_session):
    headers, uid = await auth_headers(client)
    await client.put("/api/v1/settings/llm/providers/anthropic",
                     json={"api_key": "sk-ant-xyz"}, headers=headers)
    row = (await db_session.execute(
        select(LLMProviderConfig).where(LLMProviderConfig.provider == "anthropic"))).scalar_one()
    assert row.api_key_encrypted != b"sk-ant-xyz"
    assert decrypt_field(row.api_key_encrypted) == "sk-ant-xyz"


@pytest.mark.asyncio
async def test_routing_upsert_and_get(client):
    headers, uid = await auth_headers(client)
    await client.put("/api/v1/settings/llm/routing",
                     json={"default": "ollama", "summary": "anthropic"}, headers=headers)
    r = await client.get("/api/v1/settings/llm", headers=headers)
    routing = r.json()["routing"]
    assert routing["default"] == "ollama" and routing["summary"] == "anthropic"


@pytest.mark.asyncio
async def test_delete_reverts_provider(client, db_session):
    headers, uid = await auth_headers(client)
    await client.put("/api/v1/settings/llm/providers/openai",
                     json={"api_key": "sk-1"}, headers=headers)
    await client.delete("/api/v1/settings/llm/providers/openai", headers=headers)
    rows = (await db_session.execute(
        select(LLMProviderConfig).where(LLMProviderConfig.provider == "openai"))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_user_scoping(client):
    # user A saves a key; user B's GET must not see it
    ha, ua = await auth_headers(client, email="a-llm@example.com")
    await client.put("/api/v1/settings/llm/providers/openai", json={"api_key": "sk-A"}, headers=ha)
    hb, ub = await auth_headers(client, email="b-llm@example.com")
    rb = await client.get("/api/v1/settings/llm", headers=hb)
    openai = next(p for p in rb.json()["providers"] if p["name"] == "openai")
    assert openai["has_key"] is False
```

- [ ] **Step 2: Run to verify it fails** → FAIL (404).

- [ ] **Step 3: Implement schemas + router**

`schemas/llm_settings.py`: `ProviderUpdate(api_key: str | None = None, base_url: str | None = None, model: str | None = None, enabled: bool | None = None)`, `RoutingUpdate(default|summary|section|dedup|extraction|vision|extraction_engine: str | None = None)`.

`api/llm_settings.py` (mask helper + CRUD + test). Mask: `f"{k[:3]}…{k[-4:]}"` when len>8 else `"…"`. GET builds from `load_llm_config` + the raw rows to know `has_key`/`source`. PUT upserts `LLMProviderConfig` (encrypt non-empty `api_key`; leave key if `api_key` omitted/None). DELETE removes the row. PUT routing upserts `UserLLMPreferences`. POST test: `config = await load_llm_config(db, uid)`; `prov = get_provider(... )` for that provider via a one-off `_build(name, config)`; run a tiny `complete()`; catch `LLMRateLimitError` → `{ok:False,error_type:"rate_limit"}` (auth ok), `LLMAuthError` → `{ok:False,error_type:"auth"}`, else `{ok:True, model:...}`. Audit each with provider name only. Register router in `main.py` (mirror how `summary` router is included).

- [ ] **Step 4: Run tests** → PASS. **Step 5: Commit**

```bash
git add backend/app/api/llm_settings.py backend/app/schemas/llm_settings.py backend/app/main.py backend/tests/test_llm_settings_api.py
git commit -m "feat(llm-settings): /settings/llm API (encrypted keys, masked, user-scoped, test-connection)"
```

---

### Task 6: Frontend — AI providers card (Admin → System)

**Files:**
- Modify: `frontend/src/lib/api.ts` (settings client fns)
- Modify: `frontend/src/app/(dashboard)/admin/page.tsx` (`SystemTab`, new card ~between lines 2112–2114)
- Test: `frontend/e2e/llm-settings.spec.ts` (mocked)

**Interfaces:** `getLlmSettings()`, `saveProvider(name, body)`, `clearProvider(name)`, `saveRouting(body)`, `testProvider(name)`.

- [ ] **Step 1 (invoke frontend-design skill first):** add the API client functions to `lib/api.ts` (GET `/settings/llm`, PUT `/settings/llm/providers/:name`, DELETE same, PUT `/settings/llm/routing`, POST `/settings/llm/providers/:name/test`).
- [ ] **Step 2:** add an "AI providers" `card-surface pad` block in `SystemTab` between the Preferences card and "Your data" card. Theme-native (`.selectbox`, existing field/label styles). Contents: a default-provider select + Advanced disclosure with per-op selects; per-provider rows (masked key, password input + Save, Clear, Test with inline result, base-URL/model inputs for local/openrouter, enabled toggle); per-op + cloud/local data-handling copy. Load via `getLlmSettings` on tab mount.
- [ ] **Step 3:** `cd frontend && npm run build` → typechecks.
- [ ] **Step 4: e2e (mocked, console-gate):** `frontend/e2e/llm-settings.spec.ts` — inject auth, stub `/settings/llm` GET (providers + routing) + PUT (capture body) + test; assert the card renders, saving a key posts it and shows masked on reload (re-stub GET with has_key), switching default posts routing, Test shows a result. Run `npx playwright test llm-settings --workers=1`.
- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts "frontend/src/app/(dashboard)/admin/page.tsx" frontend/e2e/llm-settings.spec.ts
git commit -m "feat(llm-settings): AI providers settings card in Admin System tab"
```

---

### Task 7: Regression, docs, PR

**Files:** `.env.example` (note the pane manages keys per-user), `CLAUDE.local.md` (settings-pane gotchas — at ship).

- [ ] **Step 1: Backend fast suite** — `cd backend && .venv/bin/python -m pytest -m "not slow" -q`. Expected: all pass (prior + new). Fix any test that constructed `get_provider`/call sites with the old signatures.
- [ ] **Step 2:** Grep for direct `settings.llm_provider`/`settings.*_api_key` reads outside `config.py`/`registry.py` legacy paths — ensure provider resolution goes through `LLMConfig`.
- [ ] **Step 3:** Update `.env.example` note. Push branch, open PR (`feat/llm-settings-pane` → main). Update `CLAUDE.local.md` via the ship flow.

---

## Self-Review

**Spec coverage:** tables (Task 1), resolver (2), registry per-user + cache-by-creds (3), call-site threading all four (4), API with mask/encrypt/user-scope/test (5), pane (6), regression+docs (7). De-id-unchanged asserted in Task 4 path + Task 5 (keys never logged). User-scoping asserted in Task 5. Vision routing field (`vision`) is carried in routing now (Part 2 consumes it). All Part-1 spec sections map to a task.

**Placeholders:** none — concrete code/tests in each backend step; frontend (Task 6) is interface-level by necessity (UI varies with the live component) and gated on the frontend-design skill + a mocked e2e.

**Type consistency:** `LLMConfig(routing, providers)`, `ProviderCreds(api_key, base_url, model, enabled)`, `load_llm_config(db, user_id)`, `get_provider(operation, config)`, `_build(name, config)`, `provider_name_for(operation, config)`, `available_providers(config)` consistent across Tasks 2–6. Models `LLMProviderConfig`/`UserLLMPreferences` consistent Tasks 1–5.
