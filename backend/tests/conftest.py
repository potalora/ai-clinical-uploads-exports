from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.main import app as fastapi_app
from app.database import get_db
from app.models.base import Base

# Import all models so metadata is populated
import app.models  # noqa: F401

FIXTURES_DIR = Path(__file__).parent / "fixtures"

TEST_DB_URL = settings.database_url


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session with table creation and cleanup."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Clean up any leftover data from prior runs
    async with engine.begin() as conn:
        for table in [
            "provenance", "dedup_candidates", "health_records",
            "ai_summary_prompts", "uploaded_files", "patients",
            "audit_log", "users",
        ]:
            await conn.execute(text(f"DELETE FROM {table}"))

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    # Clean up all data after each test (reverse FK order)
    async with engine.begin() as conn:
        for table in [
            "provenance", "dedup_candidates", "health_records",
            "ai_summary_prompts", "uploaded_files", "patients",
            "audit_log", "users",
        ]:
            await conn.execute(text(f"DELETE FROM {table}"))

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP test client with DB dependency override."""

    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def fhir_bundle():
    """Load user-provided FHIR JSON, fall back to synthetic."""
    user_file = FIXTURES_DIR / "user_provided_fhir.json"
    synthetic_file = FIXTURES_DIR / "sample_fhir_bundle.json"
    path = user_file if user_file.exists() else synthetic_file
    return json.loads(path.read_text())


@pytest.fixture
def epic_export_dir():
    """Load user-provided Epic export dir, fall back to synthetic."""
    user_dir = FIXTURES_DIR / "epic_export"
    synthetic_dir = FIXTURES_DIR / "sample_epic_tsv"
    return user_dir if user_dir.exists() else synthetic_dir
