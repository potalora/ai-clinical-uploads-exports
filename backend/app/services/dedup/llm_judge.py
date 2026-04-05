from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)

VALID_CLASSIFICATIONS = {"duplicate", "update", "related", "distinct"}

# Patient-level fields that must never be sent to LLM
_STRIP_FIELDS = {
    "subject", "patient", "performer", "author", "recorder",
    "requester", "asserter", "participant", "informant",
    "text",  # narrative may contain names
}


def _strip_patient_fields(resource: dict) -> dict:
    """Remove patient-identifying fields from a FHIR resource before LLM judgment."""
    return {k: v for k, v in resource.items() if k not in _STRIP_FIELDS}

_JUDGE_PROMPT = """\
You are a clinical record deduplication judge. Given two FHIR resources of the same \
type, classify their relationship.

Return ONLY valid JSON with this schema:
{
  "classification": "duplicate" | "update" | "related" | "distinct",
  "confidence": 0.0 to 1.0,
  "explanation": "Brief human-readable reasoning",
  "field_diff": null or {"fieldName": {"old": "value from Record A", "new": "value from Record B"}}
}

Definitions:
- "duplicate": Same clinical event, same data. These are exact or near-exact copies.
- "update": Same clinical event, but Record B has newer/updated values (dose change, status change, new result). Provide field_diff showing what changed.
- "related": Clinically connected but represent different events (e.g., same medication at different time periods, same condition at different encounters).
- "distinct": False positive — these are different clinical concepts despite surface similarity.

Rules:
- Compare clinical meaning, not just text similarity.
- A medication with a changed dose is an "update", not a "duplicate".
- A condition that changed from "active" to "resolved" is an "update".
- Two readings of the same lab on different dates are "related", not duplicates.
- Prefer "related" over "distinct" when records share the same clinical concept.
- Always provide field_diff for "update" classifications.
"""


@dataclass
class JudgmentResult:
    """Result of LLM judgment on a candidate pair."""

    classification: str
    confidence: float
    explanation: str
    field_diff: dict | None

    @classmethod
    def from_llm_response(cls, data: dict) -> JudgmentResult:
        classification = data.get("classification", "related")
        if classification not in VALID_CLASSIFICATIONS:
            classification = "related"
        return cls(
            classification=classification,
            confidence=max(0.0, min(1.0, data.get("confidence", 0.5))),
            explanation=data.get("explanation", ""),
            field_diff=data.get("field_diff"),
        )

    @classmethod
    def error_fallback(cls) -> JudgmentResult:
        return cls(
            classification="related",
            confidence=0.0,
            explanation="LLM judgment failed — flagged for manual review",
            field_diff=None,
        )


async def judge_candidate_pair(
    fhir_a: dict,
    fhir_b: dict,
    record_type: str,
    api_key: str,
) -> JudgmentResult:
    """Judge a single candidate pair using Gemini.

    Returns a JudgmentResult. On failure, returns a safe fallback
    that flags the pair for manual review.
    """
    try:
        client = genai.Client(api_key=api_key)
        content = (
            f"{_JUDGE_PROMPT}\n\n"
            f"Record type: {record_type}\n\n"
            f"Record A:\n{json.dumps(_strip_patient_fields(fhir_a), indent=2)}\n\n"
            f"Record B:\n{json.dumps(_strip_patient_fields(fhir_b), indent=2)}"
        )
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=content,
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        data = json.loads(response.text)
        return JudgmentResult.from_llm_response(data)
    except Exception:
        logger.exception("LLM judge failed for %s pair", record_type)
        return JudgmentResult.error_fallback()


async def judge_candidates_batch(
    pairs: list[tuple[dict, dict, str]],
    api_key: str,
    max_concurrent: int = 3,
) -> list[JudgmentResult]:
    """Judge multiple candidate pairs with bounded concurrency.

    Each entry in pairs is (fhir_a, fhir_b, record_type).
    Returns results in the same order as input pairs.
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def _judge_with_sem(fhir_a: dict, fhir_b: dict, record_type: str) -> JudgmentResult:
        async with sem:
            return await judge_candidate_pair(fhir_a, fhir_b, record_type, api_key)

    tasks = [_judge_with_sem(a, b, rt) for a, b, rt in pairs]
    return await asyncio.gather(*tasks)
