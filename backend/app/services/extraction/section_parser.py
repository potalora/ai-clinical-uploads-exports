from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)


class SectionType(str, Enum):
    MEDICATIONS = "medications"
    ASSESSMENT = "assessment"
    CLINICAL_NOTE = "clinical_note"
    LABS = "labs"
    REVIEW_OF_SYSTEMS = "review_of_systems"
    HISTORY = "history"
    PHYSICAL_EXAM = "physical_exam"
    ASSESSMENT_PLAN = "assessment_plan"
    IMAGING = "imaging"
    FAMILY_HISTORY = "family_history"
    SOCIAL_HISTORY = "social_history"
    ALLERGIES = "allergies"
    PROCEDURES = "procedures"
    VITALS = "vitals"
    OTHER = "other"


@dataclass
class ParsedSection:
    section_type: SectionType
    title: str
    text: str
    char_range: tuple[int, int] | None = None


@dataclass
class ParsedDocument:
    document_type: str
    primary_visit_date: str | None
    provider: str | None
    facility: str | None
    sections: list[ParsedSection] = field(default_factory=list)


_SECTION_PARSER_PROMPT = """\
You are a clinical document parser. Given the full text of a medical document, \
identify its logical sections and return structured JSON.

Return ONLY valid JSON with this exact schema:
{
  "document_type": "clinical_note" | "lab_report" | "imaging_report" | "discharge_summary" | "referral" | "other",
  "primary_visit_date": "YYYY-MM-DD" or null,
  "provider": "provider name" or null,
  "facility": "facility name" or null,
  "sections": [
    {
      "type": "medications" | "assessment" | "clinical_note" | "labs" | "review_of_systems" | "history" | "physical_exam" | "assessment_plan" | "imaging" | "family_history" | "social_history" | "allergies" | "procedures" | "vitals" | "other",
      "title": "Section heading as it appears in the document",
      "text": "Full text content of this section, preserving original formatting",
      "char_range": [start_char, end_char]
    }
  ]
}

Rules:
- Preserve ALL text — every character of the original document must appear in exactly one section.
- Use the most specific section type that fits. Use "other" only for content that doesn't match any type.
- If the document has no clear section structure, return a single section with type "clinical_note".
- The "history" type covers past medical history, surgical history, and previous visit notes.
- "assessment_plan" is specifically for the Assessment & Plan or A&P section.
- "assessment" is for standalone diagnosis/assessment lists (e.g., ICD-10 code tables) NOT combined with a plan.
- Date should be the primary visit/encounter date, not document generation dates or historical dates.
- Provider and facility are extracted from document headers, not from narrative text.
"""


async def parse_sections(text: str, api_key: str) -> ParsedDocument:
    """Parse a clinical document into logical sections using Gemini.

    Falls back to a single OTHER section if the LLM call fails.
    """
    if not text or len(text.strip()) < 10:
        return ParsedDocument(
            document_type="unknown",
            primary_visit_date=None,
            provider=None,
            facility=None,
            sections=[ParsedSection(SectionType.OTHER, "Full Document", text or "")],
        )

    try:
        llm_response = await _call_gemini_for_sections(text, api_key)
    except Exception:
        logger.exception("Section parsing failed, falling back to single section")
        return ParsedDocument(
            document_type="unknown",
            primary_visit_date=None,
            provider=None,
            facility=None,
            sections=[ParsedSection(SectionType.OTHER, "Full Document", text)],
        )

    # Handle case where Gemini returns a JSON array instead of an object.
    # If the response is a list, treat it as the sections array directly.
    if isinstance(llm_response, list):
        raw_sections = llm_response
        doc_type = "unknown"
        visit_date = None
        provider = None
        facility = None
    else:
        raw_sections = llm_response.get("sections", [])
        doc_type = llm_response.get("document_type", "unknown")
        visit_date = llm_response.get("primary_visit_date")
        provider = llm_response.get("provider")
        facility = llm_response.get("facility")

    sections = []
    for s in raw_sections:
        if not isinstance(s, dict):
            continue
        try:
            section_type = SectionType(s["type"])
        except (ValueError, KeyError):
            section_type = SectionType.OTHER

        char_range = s.get("char_range")
        sections.append(
            ParsedSection(
                section_type=section_type,
                title=s.get("title", ""),
                text=s.get("text", ""),
                char_range=tuple(char_range) if char_range and len(char_range) == 2 else None,
            )
        )

    if not sections:
        sections = [ParsedSection(SectionType.OTHER, "Full Document", text)]

    return ParsedDocument(
        document_type=doc_type,
        primary_visit_date=visit_date,
        provider=provider,
        facility=facility,
        sections=sections,
    )


async def _call_gemini_for_sections(text: str, api_key: str) -> dict:
    """Call Gemini Flash to parse document sections. Returns parsed JSON dict."""
    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=f"{_SECTION_PARSER_PROMPT}\n\n---\n\nDOCUMENT TEXT:\n{text}",
        config=genai.types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


def split_large_section(text: str, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    """Split a large section into chunks at paragraph or sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    if len(paragraphs) > 1:
        return _merge_chunks(paragraphs, max_chars, overlap, separator="\n\n")

    sentences = text.replace(". ", ".\n").split("\n")
    return _merge_chunks(sentences, max_chars, overlap, separator=" ")


def _merge_chunks(
    parts: list[str], max_chars: int, overlap: int, separator: str
) -> list[str]:
    """Merge small parts into chunks respecting max_chars, adding overlap."""
    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = current + separator + part if current else part
        if len(candidate) > max_chars and current:
            chunks.append(current)
            overlap_text = current[-overlap:] if len(current) > overlap else current
            current = overlap_text + separator + part
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks
