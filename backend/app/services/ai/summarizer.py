from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from google import genai
from google.genai import types
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.record import HealthRecord
from app.services.ai.phi_scrubber import scrub_phi
from app.services.ai.prompt_builder import _format_record

logger = logging.getLogger(__name__)

NL_SYSTEM_PROMPT = """You are a medical records summarizer. Your task is to organize and summarize the following de-identified health records into a clear, structured overview.

IMPORTANT RULES:
- Do NOT provide any diagnoses, treatment recommendations, medical advice, or clinical decision support.
- Summarize the factual medical information ONLY.
- If information is unclear or potentially conflicting, note this without interpretation.
- Organize information chronologically within each category.
- Use clear section headers.

OUTPUT FORMAT:
Use structured markdown with sections organized by category and chronological order."""

JSON_SYSTEM_PROMPT = """You are a medical records summarizer. Your task is to organize and summarize the following de-identified health records into structured JSON.

IMPORTANT RULES:
- Do NOT provide any diagnoses, treatment recommendations, medical advice, or clinical decision support.
- Summarize the factual medical information ONLY.
- If information is unclear or potentially conflicting, note this without interpretation.

OUTPUT FORMAT:
Return a JSON object with the following structure:
{
  "summary": "brief overall summary",
  "categories": {
    "conditions": [{"name": "...", "status": "...", "notes": "..."}],
    "medications": [{"name": "...", "dosage": "...", "status": "..."}],
    "labs": [{"test": "...", "value": "...", "unit": "...", "date": "...", "interpretation": "..."}],
    "encounters": [{"type": "...", "date": "...", "notes": "..."}],
    "procedures": [{"name": "...", "date": "...", "notes": "..."}],
    "immunizations": [{"vaccine": "...", "date": "...", "status": "..."}]
  },
  "timeline_highlights": ["key event 1", "key event 2"]
}"""

BOTH_SYSTEM_PROMPT = """You are a medical records summarizer. Your task is to organize and summarize the following de-identified health records.

IMPORTANT RULES:
- Do NOT provide any diagnoses, treatment recommendations, medical advice, or clinical decision support.
- Summarize the factual medical information ONLY.
- If information is unclear or potentially conflicting, note this without interpretation.

OUTPUT FORMAT:
Return a JSON object with exactly two keys:
{
  "natural_language": "A full markdown-formatted summary with section headers, organized chronologically by category.",
  "structured_data": {
    "summary": "brief overall summary",
    "categories": {
      "conditions": [...],
      "medications": [...],
      "labs": [...],
      "encounters": [...],
      "procedures": [...],
      "immunizations": [...]
    },
    "timeline_highlights": [...]
  }
}"""


async def generate_summary(
    db: AsyncSession,
    user_id: UUID,
    patient_id: UUID,
    summary_type: str = "full",
    category: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    output_format: str = "natural_language",
    custom_system_prompt: str | None = None,
    custom_user_prompt: str | None = None,
) -> dict:
    """Generate a summary by calling Gemini 3 Flash.

    Returns a dict with keys: natural_language, json_data, record_count,
    duplicate_warning, de_identification_report, model_used, system_prompt,
    user_prompt.
    """
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")

    # Count total vs deduped records
    total_count = await _count_records(db, user_id, patient_id, deduped_only=False)
    deduped_count = await _count_records(db, user_id, patient_id, deduped_only=True)
    duplicates_excluded = total_count - deduped_count

    duplicate_warning = None
    if duplicates_excluded > 0:
        duplicate_warning = {
            "total_records": total_count,
            "deduped_records": deduped_count,
            "duplicates_excluded": duplicates_excluded,
            "message": f"{duplicates_excluded} potential duplicate(s) detected and excluded from summary.",
        }

    # Fetch non-duplicate, non-deleted records
    records = await _fetch_deduped_records(
        db, user_id, patient_id, category, date_from, date_to
    )

    if not records:
        raise ValueError("No records found matching the criteria")

    # Format and de-identify
    record_texts = [_format_record(r) for r in records]
    combined_text = "\n\n---\n\n".join(record_texts)
    scrubbed_text, de_id_report = scrub_phi(combined_text)

    # Build prompts
    system_prompt = custom_system_prompt or _get_system_prompt(output_format)

    from app.services.ai.prompt_builder import CATEGORY_PROMPTS
    prompt_instruction = CATEGORY_PROMPTS.get(category or summary_type, CATEGORY_PROMPTS["full"])
    user_prompt = custom_user_prompt or f"""{prompt_instruction}

The following de-identified health records are provided for summarization:

{scrubbed_text}

Please provide a structured summary following the rules in the system prompt."""

    # Call Gemini
    client = genai.Client(api_key=settings.gemini_api_key)

    config_kwargs: dict = {
        "system_instruction": system_prompt,
        "temperature": settings.gemini_summary_temperature,
        "max_output_tokens": settings.gemini_summary_max_tokens,
    }
    if output_format in ("json", "both"):
        config_kwargs["response_mime_type"] = "application/json"

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    response_text = response.text or ""

    # Parse response based on format
    natural_language = None
    json_data = None

    if output_format == "natural_language":
        natural_language = response_text
    elif output_format == "json":
        try:
            json_data = json.loads(response_text)
        except json.JSONDecodeError:
            json_data = {"raw_response": response_text}
    elif output_format == "both":
        try:
            parsed = json.loads(response_text)
            natural_language = parsed.get("natural_language", "")
            json_data = parsed.get("structured_data", parsed)
        except json.JSONDecodeError:
            natural_language = response_text

    # Token usage
    tokens_used = None
    if response.usage_metadata:
        tokens_used = (
            (response.usage_metadata.prompt_token_count or 0)
            + (response.usage_metadata.candidates_token_count or 0)
        )

    return {
        "natural_language": natural_language,
        "json_data": json_data,
        "record_count": len(records),
        "duplicate_warning": duplicate_warning,
        "de_identification_report": de_id_report,
        "model_used": settings.gemini_model,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "tokens_used": tokens_used,
    }


def _get_system_prompt(output_format: str) -> str:
    """Return the appropriate system prompt for the output format."""
    if output_format == "json":
        return JSON_SYSTEM_PROMPT
    if output_format == "both":
        return BOTH_SYSTEM_PROMPT
    return NL_SYSTEM_PROMPT


async def _count_records(
    db: AsyncSession, user_id: UUID, patient_id: UUID, deduped_only: bool
) -> int:
    """Count records, optionally filtering out duplicates."""
    query = (
        select(func.count(HealthRecord.id))
        .where(
            HealthRecord.user_id == user_id,
            HealthRecord.patient_id == patient_id,
            HealthRecord.deleted_at.is_(None),
        )
    )
    if deduped_only:
        query = query.where(HealthRecord.is_duplicate.is_(False))
    result = await db.execute(query)
    return result.scalar_one()


async def _fetch_deduped_records(
    db: AsyncSession,
    user_id: UUID,
    patient_id: UUID,
    category: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[HealthRecord]:
    """Fetch non-duplicate, non-deleted records."""
    query = (
        select(HealthRecord)
        .where(
            HealthRecord.user_id == user_id,
            HealthRecord.patient_id == patient_id,
            HealthRecord.deleted_at.is_(None),
            HealthRecord.is_duplicate.is_(False),
        )
        .order_by(HealthRecord.effective_date.asc().nullslast())
    )

    if category and category != "full":
        query = query.where(HealthRecord.record_type == category)
    if date_from:
        query = query.where(HealthRecord.effective_date >= date_from)
    if date_to:
        query = query.where(HealthRecord.effective_date <= date_to)

    result = await db.execute(query)
    return list(result.scalars().all())
