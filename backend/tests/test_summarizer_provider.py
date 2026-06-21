from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.encryption import encrypt_field
from app.services.ai.llm.types import LLMResponse, LLMUsage
from app.services.ai.summarizer import generate_summary
from tests.conftest import auth_headers, create_test_patient, seed_test_records

# A distinctive, multi-token name so the deterministic known-patient scrubber
# (substring match, case-insensitive) has something unambiguous to strip.
PATIENT_NAME = "Bartholomew Quibblesworth"


@pytest.mark.asyncio
async def test_summary_uses_explicit_provider_and_scrubs_patient_name(
    client: AsyncClient, db_session: AsyncSession
):
    """``generate_summary(provider=...)`` routes to the chosen provider and the
    text it receives is de-identified (the patient's own name is stripped)."""
    headers, user_id = await auth_headers(client)
    patient = await create_test_patient(db_session, user_id)

    # Give the patient a known name so the deterministic scrubber can strip it,
    # and surface that name inside a record so it would otherwise reach the LLM.
    patient.name_encrypted = encrypt_field(PATIENT_NAME)
    await db_session.commit()

    records = await seed_test_records(db_session, user_id, patient.id, count=3)
    records[0].display_text = f"Office visit with {PATIENT_NAME} for follow-up"
    await db_session.commit()

    fake_resp = LLMResponse(
        text="A concise, de-identified records overview.",
        finish_reason="stop",
        model="claude-haiku-4-5-20251001",
        usage=LLMUsage(10, 5, 15),
        raw=None,
    )
    prov = AsyncMock()
    prov.name = "anthropic"
    prov.complete.return_value = fake_resp

    # The explicit-provider branch builds a one-off provider via
    # ``_provider_by_name``; ``get_provider`` is the routed seam used when no
    # provider is given. Patch both to the same mock so the request never
    # reaches a real SDK regardless of which seam fires.
    with patch(
        "app.services.ai.summarizer.get_provider", return_value=prov
    ), patch(
        "app.services.ai.summarizer._provider_by_name", return_value=prov
    ):
        out = await generate_summary(
            db_session, UUID(user_id), patient.id, provider="anthropic"
        )

    assert out["natural_language"] == fake_resp.text
    assert out["model_used"] == fake_resp.model

    # De-identification check: inspect the LLMRequest handed to the provider.
    # The patient's name must NOT appear in the user content; it should have
    # been replaced by the known-patient placeholder before send.
    sent_request = prov.complete.call_args.args[0]
    content = sent_request.messages[0].content
    assert "Bartholomew" not in content
    assert "Quibblesworth" not in content
    assert "[PATIENT]" in content
