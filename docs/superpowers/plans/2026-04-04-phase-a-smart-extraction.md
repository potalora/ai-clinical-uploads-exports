# Phase A: Section-Aware Smart Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the truncating single-pass extraction with a section-aware pipeline that parses document structure, extracts 11 entity types (6 existing + 5 new), and links records to encounters.

**Architecture:** Gemini Flash parses scrubbed text into logical sections → LangExtract runs per-section (3 concurrent, respecting 2000-char buffer) → new entity-to-FHIR builders produce Encounter, DiagnosticReport, FamilyMemberHistory, DocumentReference (A&P), and Observation (social-history) → records linked via `linked_encounter_id` and `record_cross_references` table.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, google-genai (Gemini Flash), langextract, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-04-smart-extraction-and-dedup-design.md`

---

## File Map

### New files
| File | Responsibility |
|------|---------------|
| `backend/app/services/extraction/section_parser.py` | Gemini-powered document section parser |
| `backend/app/models/cross_reference.py` | RecordCrossReference SQLAlchemy model |
| `backend/tests/test_section_parser.py` | Section parser unit tests |
| `backend/tests/test_expanded_extraction.py` | New entity type + FHIR builder tests |
| `backend/tests/test_pipeline_integration.py` | End-to-end pipeline integration tests |

### Modified files
| File | Changes |
|------|---------|
| `backend/app/models/record.py` | Add `source_section`, `linked_encounter_id`, `merge_metadata` columns |
| `backend/app/models/uploaded_file.py` | Add `extraction_sections`, `document_metadata`, `dedup_summary` columns |
| `backend/app/models/__init__.py` | Register `RecordCrossReference` model |
| `backend/app/services/extraction/clinical_examples.py` | Add 5 new entity types + few-shot examples |
| `backend/app/services/extraction/entity_to_fhir.py` | Add 5 new entity type builders |
| `backend/app/services/ingestion/fhir_parser.py` | Add `DiagnosticReport` handler in `build_display_text` |
| `backend/app/api/upload.py` | Integrate section parser into `_process_unstructured` |
| `backend/alembic/versions/` | New migration for all schema changes |
| `backend/tests/conftest.py` | Add `record_cross_references` to TRUNCATE list |

---

### Task 1: Database Migration — New Columns and Tables

**Files:**
- Create: `backend/alembic/versions/<auto>_add_smart_extraction_columns.py`
- Modify: `backend/app/models/record.py`
- Modify: `backend/app/models/uploaded_file.py`
- Create: `backend/app/models/cross_reference.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Add columns to HealthRecord model**

In `backend/app/models/record.py`, add three new columns after the existing `ai_extracted` column:

```python
# Add these imports at the top (ForeignKey is already imported)
# No new imports needed — UUID, JSONB, Text, Boolean, Float, ForeignKey all already imported

# Add after the ai_extracted column (around line 48):
    source_section: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("health_records.id"), nullable=True
    )
    merge_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 2: Add columns to UploadedFile model**

In `backend/app/models/uploaded_file.py`, add three new columns after `extraction_entities`:

```python
    extraction_sections: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    document_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dedup_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 3: Create RecordCrossReference model**

Create `backend/app/models/cross_reference.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RecordCrossReference(Base):
    """Links A&P DocumentReferences to the records they reference."""

    __tablename__ = "record_cross_references"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    document_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("health_records.id"), nullable=False
    )
    referenced_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("health_records.id"), nullable=False
    )
    reference_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Add the missing `datetime` import at the top:

```python
from datetime import datetime
```

- [ ] **Step 4: Register model in __init__.py**

In `backend/app/models/__init__.py`, add:

```python
from app.models.cross_reference import RecordCrossReference
```

And add `"RecordCrossReference"` to the `__all__` list.

- [ ] **Step 5: Update conftest.py TRUNCATE**

In `backend/tests/conftest.py`, add `record_cross_references` to both TRUNCATE statements (lines 48 and 61). Insert it before `health_records` since it has FK dependencies:

```python
"TRUNCATE revoked_tokens, provenance, dedup_candidates, record_cross_references, health_records, "
```

- [ ] **Step 6: Generate and review Alembic migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add smart extraction columns and cross references table"
```

Review the generated migration. Manually add indexes not caught by autogenerate:

```python
# Add inside upgrade() after the autogenerated operations:
op.create_index(
    "ix_health_records_linked_encounter",
    "health_records",
    ["linked_encounter_id"],
    postgresql_where=text("linked_encounter_id IS NOT NULL"),
)
op.create_index(
    "ix_health_records_source_file_section",
    "health_records",
    ["source_file_id", "source_section"],
    postgresql_where=text("source_file_id IS NOT NULL"),
)
op.create_index(
    "ix_cross_ref_pair",
    "record_cross_references",
    ["document_record_id", "referenced_record_id"],
    unique=True,
)
op.create_index(
    "ix_cross_ref_referenced",
    "record_cross_references",
    ["referenced_record_id"],
)
```

Add corresponding `op.drop_index()` calls in `downgrade()`.

- [ ] **Step 7: Run migration against test DB**

Run:
```bash
cd backend && DATABASE_URL=postgresql+asyncpg://localhost:5432/medtimeline_test alembic upgrade head
```

Expected: Migration applies cleanly.

- [ ] **Step 8: Verify models load**

Run:
```bash
cd backend && python -c "from app.models import RecordCrossReference, HealthRecord; print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/record.py backend/app/models/uploaded_file.py backend/app/models/cross_reference.py backend/app/models/__init__.py backend/alembic/versions/ backend/tests/conftest.py
git commit -m "feat: add smart extraction DB schema — sections, encounter linking, cross-references"
```

---

### Task 2: Section Parser Service

**Files:**
- Create: `backend/app/services/extraction/section_parser.py`
- Test: `backend/tests/test_section_parser.py`

- [ ] **Step 1: Write failing tests for section parser**

Create `backend/tests/test_section_parser.py`:

```python
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.extraction.section_parser import (
    parse_sections,
    SectionType,
    ParsedDocument,
    ParsedSection,
    split_large_section,
)


SAMPLE_CLINICAL_NOTE = """Medications & Allergies:
nitazoxanide 500 mg tablet - 1 tablet every 12 hours for 5 days
Vitamin D2 1,250 mcg capsule - take 1 capsule per week

Assessment:
ICD-10-CM Condition R14.0 Abdominal distension (gaseous)
ICD-10-CM Condition R19.4 Change in bowel habit

Review of Systems:
Gastrointestinal: Regular bowel movements, mild intermittent bloating.
Denies abdominal pain, nausea, vomiting.

Assessment & Plan:
#1: Post-infectious IBS with elevated anti-vinculin Ab.
- Continue prucalopride 2 mg daily.
- Add low-dose naltrexone 0.5 mg nightly."""


MOCK_LLM_RESPONSE = {
    "document_type": "clinical_note",
    "primary_visit_date": "2026-03-30",
    "provider": "Dr. Elena Ivanina",
    "facility": "The Center for Integrative Gut Health",
    "sections": [
        {
            "type": "medications",
            "title": "Medications & Allergies",
            "text": "nitazoxanide 500 mg tablet - 1 tablet every 12 hours for 5 days\nVitamin D2 1,250 mcg capsule - take 1 capsule per week",
            "char_range": [0, 130],
        },
        {
            "type": "assessment",
            "title": "Assessment",
            "text": "ICD-10-CM Condition R14.0 Abdominal distension (gaseous)\nICD-10-CM Condition R19.4 Change in bowel habit",
            "char_range": [130, 260],
        },
        {
            "type": "review_of_systems",
            "title": "Review of Systems",
            "text": "Gastrointestinal: Regular bowel movements, mild intermittent bloating.\nDenies abdominal pain, nausea, vomiting.",
            "char_range": [260, 400],
        },
        {
            "type": "assessment_plan",
            "title": "Assessment & Plan",
            "text": "#1: Post-infectious IBS with elevated anti-vinculin Ab.\n- Continue prucalopride 2 mg daily.\n- Add low-dose naltrexone 0.5 mg nightly.",
            "char_range": [400, 560],
        },
    ],
}


class TestSectionParser:
    """Tests for the section parser service."""

    @pytest.mark.asyncio
    async def test_parse_sections_returns_parsed_document(self):
        """Section parser returns a ParsedDocument with sections."""
        with patch(
            "app.services.extraction.section_parser._call_gemini_for_sections",
            new_callable=AsyncMock,
            return_value=MOCK_LLM_RESPONSE,
        ):
            result = await parse_sections("some clinical text", "test-api-key")

        assert isinstance(result, ParsedDocument)
        assert result.document_type == "clinical_note"
        assert result.primary_visit_date == "2026-03-30"
        assert result.provider == "Dr. Elena Ivanina"
        assert result.facility == "The Center for Integrative Gut Health"
        assert len(result.sections) == 4

    @pytest.mark.asyncio
    async def test_parse_sections_maps_section_types(self):
        """Each section has a valid SectionType enum value."""
        with patch(
            "app.services.extraction.section_parser._call_gemini_for_sections",
            new_callable=AsyncMock,
            return_value=MOCK_LLM_RESPONSE,
        ):
            result = await parse_sections("some clinical text", "test-api-key")

        types = [s.section_type for s in result.sections]
        assert types == [
            SectionType.MEDICATIONS,
            SectionType.ASSESSMENT,
            SectionType.REVIEW_OF_SYSTEMS,
            SectionType.ASSESSMENT_PLAN,
        ]

    @pytest.mark.asyncio
    async def test_parse_sections_preserves_text(self):
        """Section text is preserved from the LLM response."""
        with patch(
            "app.services.extraction.section_parser._call_gemini_for_sections",
            new_callable=AsyncMock,
            return_value=MOCK_LLM_RESPONSE,
        ):
            result = await parse_sections("some clinical text", "test-api-key")

        assert "nitazoxanide" in result.sections[0].text
        assert "R14.0" in result.sections[1].text

    @pytest.mark.asyncio
    async def test_parse_sections_unknown_type_falls_back_to_other(self):
        """Unknown section types map to SectionType.OTHER."""
        response = {
            **MOCK_LLM_RESPONSE,
            "sections": [
                {"type": "made_up_type", "title": "Weird Section", "text": "stuff", "char_range": [0, 5]},
            ],
        }
        with patch(
            "app.services.extraction.section_parser._call_gemini_for_sections",
            new_callable=AsyncMock,
            return_value=response,
        ):
            result = await parse_sections("stuff", "test-api-key")

        assert result.sections[0].section_type == SectionType.OTHER

    @pytest.mark.asyncio
    async def test_parse_sections_empty_text_returns_single_other_section(self):
        """Empty or very short text returns a single OTHER section with the full text."""
        with patch(
            "app.services.extraction.section_parser._call_gemini_for_sections",
            new_callable=AsyncMock,
            return_value={"document_type": "unknown", "primary_visit_date": None, "provider": None, "facility": None, "sections": []},
        ):
            result = await parse_sections("short", "test-api-key")

        assert len(result.sections) == 1
        assert result.sections[0].section_type == SectionType.OTHER
        assert result.sections[0].text == "short"

    @pytest.mark.asyncio
    async def test_parse_sections_handles_llm_error_gracefully(self):
        """If Gemini fails, return single OTHER section with full text."""
        with patch(
            "app.services.extraction.section_parser._call_gemini_for_sections",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await parse_sections("fallback text here", "test-api-key")

        assert len(result.sections) == 1
        assert result.sections[0].section_type == SectionType.OTHER
        assert result.sections[0].text == "fallback text here"


class TestSplitLargeSection:
    """Tests for splitting oversized sections at paragraph boundaries."""

    def test_small_section_not_split(self):
        """Sections under max_chars are returned as-is."""
        result = split_large_section("short text", max_chars=2000)
        assert result == ["short text"]

    def test_large_section_split_at_paragraphs(self):
        """Large sections split at double-newline paragraph boundaries."""
        paragraphs = ["Paragraph one. " * 50, "Paragraph two. " * 50, "Paragraph three. " * 50]
        text = "\n\n".join(paragraphs)
        result = split_large_section(text, max_chars=1000)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= 1200  # max_chars + overlap tolerance

    def test_split_includes_overlap(self):
        """Split chunks have overlapping content at boundaries."""
        para_a = "A sentence. " * 100  # ~1200 chars
        para_b = "B sentence. " * 100
        text = para_a + "\n\n" + para_b
        result = split_large_section(text, max_chars=1300, overlap=200)
        assert len(result) == 2
        # Last 200 chars of chunk 0 should appear at start of chunk 1
        overlap_text = result[0][-200:]
        assert overlap_text in result[1]

    def test_single_huge_paragraph_still_split(self):
        """A single paragraph exceeding max_chars is split at sentence boundaries."""
        text = "This is a sentence. " * 200  # ~4000 chars, no paragraph breaks
        result = split_large_section(text, max_chars=2000)
        assert len(result) >= 2

    def test_all_section_types_in_enum(self):
        """SectionType enum covers all expected types."""
        expected = {
            "medications", "assessment", "clinical_note", "labs",
            "review_of_systems", "history", "physical_exam",
            "assessment_plan", "imaging", "family_history",
            "social_history", "allergies", "procedures", "vitals", "other",
        }
        actual = {t.value for t in SectionType}
        assert actual == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_section_parser.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.services.extraction.section_parser'`

- [ ] **Step 3: Implement section parser**

Create `backend/app/services/extraction/section_parser.py`:

```python
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)


class SectionType(str, Enum):
    """Logical section types in a clinical document."""

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
    """A single identified section within a clinical document."""

    section_type: SectionType
    title: str
    text: str
    char_range: tuple[int, int] | None = None


@dataclass
class ParsedDocument:
    """Result of parsing a clinical document into sections."""

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

    sections = []
    for s in llm_response.get("sections", []):
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
        document_type=llm_response.get("document_type", "unknown"),
        primary_visit_date=llm_response.get("primary_visit_date"),
        provider=llm_response.get("provider"),
        facility=llm_response.get("facility"),
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
    """Split a large section into chunks at paragraph or sentence boundaries.

    Returns a list of text chunks, each at most max_chars long (plus overlap).
    """
    if len(text) <= max_chars:
        return [text]

    # Try paragraph splits first (double newline)
    paragraphs = text.split("\n\n")
    if len(paragraphs) > 1:
        return _merge_chunks(paragraphs, max_chars, overlap, separator="\n\n")

    # Fall back to sentence splits
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
            # Start next chunk with overlap from end of current
            overlap_text = current[-overlap:] if len(current) > overlap else current
            current = overlap_text + separator + part
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_section_parser.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/extraction/section_parser.py backend/tests/test_section_parser.py
git commit -m "feat: add section parser service with Gemini-powered document structure parsing"
```

---

### Task 3: Expanded Clinical Examples and Entity Types

**Files:**
- Modify: `backend/app/services/extraction/clinical_examples.py`

- [ ] **Step 1: Read current clinical_examples.py**

Read the full file to understand the existing prompt and examples structure before modifying.

- [ ] **Step 2: Update CLINICAL_EXTRACTION_PROMPT**

In `backend/app/services/extraction/clinical_examples.py`, replace the `CLINICAL_EXTRACTION_PROMPT` with an expanded version that includes the 5 new entity types. The prompt should be replaced in full:

```python
CLINICAL_EXTRACTION_PROMPT = """\
Extract clinical entities from the following medical text. Entity types:

STORABLE ENTITIES (create health records):
- medication: Drug names. Group related dosage/route/frequency via medication_group attribute. Include: name, dose, unit, route, frequency, indication.
- condition: Patient diagnoses. Include status attribute: active, resolved, historical, negated.
- lab_result: Laboratory test results. Include: test, value, unit, ref_low, ref_high, interpretation.
- vital: Vital signs (BP, HR, Temp, SpO2, Weight, Height, BMI). Include: type, value, unit.
- procedure: Medical procedures performed ON THIS PATIENT. Include: date, status.
- allergy: Drug/food/substance allergies. Include: reaction, severity.
- encounter: A clinical visit or encounter. Extract ONLY the PRIMARY visit (the visit this document is about). Include: visit_type (office, telehealth, emergency, inpatient), date, cpt_code, reason.
- imaging_result: Diagnostic test/imaging results (EGD, MRI, CT, ultrasound, X-ray, breath test, gastric emptying, SBFT, colonoscopy, etc). Include: procedure_name, date, findings, interpretation, category (imaging, endoscopy, nuclear_medicine, pulmonary, laboratory_panel).
- family_history: Health conditions of family members. Include: relationship (mother, father, grandmother, grandfather, sibling, etc.), condition, status, notes.
- social_history: Social/lifestyle factors. Include: category (diet, alcohol, tobacco, exercise, birth_history, occupation), value, date.
- assessment_plan: The Assessment & Plan section as a whole. Extract as a SINGLE entity with the full A&P text. Include: plan_items (array of numbered plan item summaries).

ATTRIBUTE ENTITIES (support storable entities, do NOT create records):
- dosage: Dose amounts (group via medication_group)
- route: Administration route (IV, PO, IM, topical, etc.)
- frequency: Dosing schedule (BID, TID, QID, daily, weekly, etc.)
- duration: Treatment duration
- date: Associated dates

RULES:
1. Use EXACT text from the document. Do NOT paraphrase or infer.
2. Group medication + dosage + route + frequency using matching medication_group attribute values.
3. NEGATION: "No X", "denies X", "ruled out X" → skip OR set status="negated". Do NOT extract as active conditions.
4. EDUCATIONAL TEXT: Skip conditions in "can cause", "may develop", "risk of" phrasing.
5. FAMILY HISTORY: Conditions attributed to family members ("Father has X", "Mom: X") → extract as family_history entity, NOT as condition.
6. Extract the date attribute for ALL entity types when a date is available in the text (format as found).
7. ENCOUNTER: Extract only ONE encounter per document — the primary visit. Do NOT create encounters for historical visit references.
8. IMAGING RESULTS: Extract the FINDINGS and INTERPRETATION, not just the procedure name. Include the date of the study.
9. ASSESSMENT & PLAN: Extract as a single entity containing the full A&P narrative. Summarize each numbered plan item in the plan_items array.
10. Confidence scoring: High (>0.8) for exact matches with clear context, Medium (0.5-0.8) for context-dependent extractions, Low (<0.5) for ambiguous mentions.
"""
```

- [ ] **Step 3: Add new few-shot examples**

Add a third example to `CLINICAL_EXAMPLES` that demonstrates the new entity types. Append after the existing two examples:

```python
CLINICAL_EXAMPLES.append(
    lx.data.ExampleData(
        text="""\
Patient: [PATIENT] DOB: [DATE] Sex: M
Provider: [PROVIDER] Visit: 03/30/2026 11:00AM

Medications:
prucalopride 2 mg tablet - take 1 tablet at night
low dose naltrexone 0.5 mg tablet - take 1 tablet at bedtime

Assessment:
ICD-10-CM R14.0 Abdominal distension (gaseous)
ICD-10-CM R10.9 Unspecified abdominal pain

Labs reviewed:
IBS-Smart Anti-Vinculin Ab 2.83 Elevated (collected 2/16/26)
H. pylori stool 1/28/26: negative
CRP 9.5 (H)
VitB12 331 (L)
VitD 17 (L)

FHX: Mom: Hypermobile, mitral valve prolapse, EOE. Father: single exon deletion SDHB gene. Grandparents: HTN, melanoma.

EGD 3/26/24: 50 eosinophils at GEJ, normal gastric and duodenal biopsies.
Ultrasound Abd 4/2024: normal.
Gastric emptying study 6/2024: normal other than first hour tiny delay (94% retained vs 90% normal).
BREATH TEST FOODMARBLE SIBO Lactulose 1/7/26: Negative.

Social History:
Diet: Low FODMAP, gluten-free, dairy-free. Triggers: fructose corn syrup, garlic, onions, lactose.
Alcohol: avoided (recognized as trigger).
Birth: Bogota, Colombia. Vaginal delivery, breastfed.

Assessment & Plan:
#1: Post-infectious IBS / SIBO risk with elevated anti-vinculin Ab. Continue prucalopride 2 mg daily. Add low-dose naltrexone 0.5 mg nightly.
#2: Dietary re-introduction. Weekday baseline gluten-free dairy-free. Use digestive enzyme with first bite.""",
        extractions=[
            lx.data.ExtractionData(label="encounter", text="Visit: 03/30/2026 11:00AM", char_interval=(56, 83), attributes={"visit_type": "telehealth", "date": "03/30/2026", "reason": "follow-up"}),
            lx.data.ExtractionData(label="medication", text="prucalopride 2 mg tablet", char_interval=(98, 122), attributes={"medication_group": "prucalopride", "date": "03/30/2026"}),
            lx.data.ExtractionData(label="dosage", text="2 mg", char_interval=(112, 116), attributes={"medication_group": "prucalopride"}),
            lx.data.ExtractionData(label="frequency", text="at night", char_interval=(133, 141), attributes={"medication_group": "prucalopride"}),
            lx.data.ExtractionData(label="medication", text="low dose naltrexone 0.5 mg tablet", char_interval=(142, 174), attributes={"medication_group": "naltrexone", "date": "03/30/2026"}),
            lx.data.ExtractionData(label="dosage", text="0.5 mg", char_interval=(162, 168), attributes={"medication_group": "naltrexone"}),
            lx.data.ExtractionData(label="frequency", text="at bedtime", char_interval=(185, 195), attributes={"medication_group": "naltrexone"}),
            lx.data.ExtractionData(label="condition", text="Abdominal distension (gaseous)", char_interval=(217, 247), attributes={"status": "active", "code": "R14.0", "code_system": "ICD-10-CM"}),
            lx.data.ExtractionData(label="condition", text="Unspecified abdominal pain", char_interval=(262, 287), attributes={"status": "active", "code": "R10.9", "code_system": "ICD-10-CM"}),
            lx.data.ExtractionData(label="lab_result", text="IBS-Smart Anti-Vinculin Ab 2.83 Elevated", char_interval=(305, 345), attributes={"test": "Anti-Vinculin Ab", "value": "2.83", "interpretation": "elevated", "date": "2/16/26"}),
            lx.data.ExtractionData(label="lab_result", text="H. pylori stool 1/28/26: negative", char_interval=(365, 398), attributes={"test": "H. pylori stool", "value": "negative", "date": "1/28/26"}),
            lx.data.ExtractionData(label="lab_result", text="CRP 9.5 (H)", char_interval=(399, 411), attributes={"test": "CRP", "value": "9.5", "interpretation": "high"}),
            lx.data.ExtractionData(label="lab_result", text="VitB12 331 (L)", char_interval=(412, 426), attributes={"test": "VitB12", "value": "331", "interpretation": "low"}),
            lx.data.ExtractionData(label="lab_result", text="VitD 17 (L)", char_interval=(427, 438), attributes={"test": "VitD", "value": "17", "interpretation": "low"}),
            lx.data.ExtractionData(label="family_history", text="Mom: Hypermobile, mitral valve prolapse, EOE", char_interval=(445, 489), attributes={"relationship": "mother", "condition": "Hypermobile", "notes": "mitral valve prolapse, EOE"}),
            lx.data.ExtractionData(label="family_history", text="Father: single exon deletion SDHB gene", char_interval=(491, 529), attributes={"relationship": "father", "condition": "single exon deletion SDHB gene"}),
            lx.data.ExtractionData(label="family_history", text="Grandparents: HTN, melanoma", char_interval=(531, 558), attributes={"relationship": "grandparent", "condition": "HTN", "notes": "melanoma"}),
            lx.data.ExtractionData(label="imaging_result", text="EGD 3/26/24: 50 eosinophils at GEJ, normal gastric and duodenal biopsies", char_interval=(561, 633), attributes={"procedure_name": "EGD", "date": "3/26/24", "findings": "50 eosinophils at GEJ, normal gastric and duodenal biopsies", "category": "endoscopy"}),
            lx.data.ExtractionData(label="imaging_result", text="Ultrasound Abd 4/2024: normal", char_interval=(635, 664), attributes={"procedure_name": "Ultrasound Abd", "date": "4/2024", "findings": "normal", "category": "imaging"}),
            lx.data.ExtractionData(label="imaging_result", text="Gastric emptying study 6/2024: normal other than first hour tiny delay (94% retained vs 90% normal)", char_interval=(666, 765), attributes={"procedure_name": "Gastric emptying study", "date": "6/2024", "findings": "normal other than first hour tiny delay (94% retained vs 90% normal)", "category": "nuclear_medicine"}),
            lx.data.ExtractionData(label="imaging_result", text="BREATH TEST FOODMARBLE SIBO Lactulose 1/7/26: Negative", char_interval=(767, 821), attributes={"procedure_name": "SIBO Lactulose Breath Test", "date": "1/7/26", "findings": "Negative", "category": "pulmonary"}),
            lx.data.ExtractionData(label="social_history", text="Diet: Low FODMAP, gluten-free, dairy-free. Triggers: fructose corn syrup, garlic, onions, lactose.", char_interval=(840, 938), attributes={"category": "diet", "value": "Low FODMAP, gluten-free, dairy-free. Triggers: fructose corn syrup, garlic, onions, lactose."}),
            lx.data.ExtractionData(label="social_history", text="Alcohol: avoided (recognized as trigger)", char_interval=(939, 979), attributes={"category": "alcohol", "value": "avoided (recognized as trigger)"}),
            lx.data.ExtractionData(label="social_history", text="Birth: Bogota, Colombia. Vaginal delivery, breastfed.", char_interval=(980, 1033), attributes={"category": "birth_history", "value": "Bogota, Colombia. Vaginal delivery, breastfed."}),
            lx.data.ExtractionData(label="assessment_plan", text="#1: Post-infectious IBS / SIBO risk with elevated anti-vinculin Ab. Continue prucalopride 2 mg daily. Add low-dose naltrexone 0.5 mg nightly.\n#2: Dietary re-introduction. Weekday baseline gluten-free dairy-free. Use digestive enzyme with first bite.", char_interval=(1055, 1300), attributes={"plan_items": ["Post-infectious IBS / SIBO risk — continue prucalopride, add LDN", "Dietary re-introduction — weekday GF/DF baseline, digestive enzyme"]}),
        ],
    )
)
```

- [ ] **Step 4: Verify syntax**

Run:
```bash
cd backend && python -c "from app.services.extraction.clinical_examples import CLINICAL_EXTRACTION_PROMPT, CLINICAL_EXAMPLES; print(f'{len(CLINICAL_EXAMPLES)} examples loaded')"
```

Expected: `3 examples loaded`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/extraction/clinical_examples.py
git commit -m "feat: expand extraction prompt with 5 new entity types and clinical examples"
```

---

### Task 4: Expanded Entity-to-FHIR Builders

**Files:**
- Modify: `backend/app/services/extraction/entity_to_fhir.py`
- Modify: `backend/app/services/ingestion/fhir_parser.py`
- Test: `backend/tests/test_expanded_extraction.py`

- [ ] **Step 1: Write failing tests for new entity type builders**

Create `backend/tests/test_expanded_extraction.py`:

```python
from __future__ import annotations

import pytest
from uuid import uuid4

from app.services.extraction.entity_extractor import ExtractedEntity
from app.services.extraction.entity_to_fhir import entity_to_health_record_dict


USER_ID = uuid4()
PATIENT_ID = uuid4()
SOURCE_FILE_ID = uuid4()


def _make_entity(entity_class: str, text: str, **attrs) -> ExtractedEntity:
    return ExtractedEntity(entity_class=entity_class, text=text, attributes=attrs, confidence=0.85)


class TestEncounterBuilder:
    """Tests for encounter entity → FHIR Encounter conversion."""

    def test_encounter_produces_record(self):
        entity = _make_entity("encounter", "Visit: 03/30/2026", visit_type="telehealth", date="03/30/2026", cpt_code="99214", reason="follow-up")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result is not None
        assert result["record_type"] == "encounter"
        assert result["fhir_resource_type"] == "Encounter"

    def test_encounter_fhir_resource_structure(self):
        entity = _make_entity("encounter", "Visit: 03/30/2026", visit_type="telehealth", date="03/30/2026", cpt_code="99214", reason="follow-up")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        fhir = result["fhir_resource"]
        assert fhir["resourceType"] == "Encounter"
        assert fhir["status"] == "finished"
        assert fhir["class"]["code"] == "VR"
        assert fhir["type"][0]["coding"][0]["code"] == "99214"
        assert fhir["reasonCode"][0]["text"] == "follow-up"

    def test_encounter_class_mapping(self):
        for visit_type, expected_code in [("office", "AMB"), ("telehealth", "VR"), ("emergency", "EMER"), ("inpatient", "IMP")]:
            entity = _make_entity("encounter", "Visit", visit_type=visit_type)
            result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
            assert result["fhir_resource"]["class"]["code"] == expected_code

    def test_encounter_display_text(self):
        entity = _make_entity("encounter", "Visit: 03/30/2026", visit_type="telehealth", date="03/30/2026")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert "telehealth" in result["display_text"].lower() or "Telehealth" in result["display_text"]


class TestDiagnosticReportBuilder:
    """Tests for imaging_result entity → FHIR DiagnosticReport."""

    def test_imaging_produces_record(self):
        entity = _make_entity("imaging_result", "EGD 3/26/24", procedure_name="EGD", date="3/26/24", findings="50 eosinophils at GEJ", category="endoscopy")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result is not None
        assert result["record_type"] == "diagnostic_report"
        assert result["fhir_resource_type"] == "DiagnosticReport"

    def test_imaging_fhir_structure(self):
        entity = _make_entity("imaging_result", "EGD 3/26/24", procedure_name="EGD", date="3/26/24", findings="50 eosinophils at GEJ", interpretation="possible EoE", category="endoscopy")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        fhir = result["fhir_resource"]
        assert fhir["resourceType"] == "DiagnosticReport"
        assert fhir["status"] == "final"
        assert fhir["code"]["text"] == "EGD"
        assert fhir["conclusion"] == "50 eosinophils at GEJ"
        assert fhir["category"][0]["coding"][0]["code"] == "endoscopy"

    def test_imaging_display_text(self):
        entity = _make_entity("imaging_result", "Ultrasound Abd normal", procedure_name="Ultrasound Abd", findings="normal")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert "Ultrasound Abd" in result["display_text"]
        assert "normal" in result["display_text"]


class TestFamilyHistoryBuilder:
    """Tests for family_history entity → FHIR FamilyMemberHistory."""

    def test_family_history_produces_record(self):
        entity = _make_entity("family_history", "Mom: HTN", relationship="mother", condition="HTN")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result is not None
        assert result["record_type"] == "family_history"
        assert result["fhir_resource_type"] == "FamilyMemberHistory"

    def test_family_history_fhir_structure(self):
        entity = _make_entity("family_history", "Mom: Hypermobile, MVP, EOE", relationship="mother", condition="Hypermobile", notes="mitral valve prolapse, EOE")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        fhir = result["fhir_resource"]
        assert fhir["resourceType"] == "FamilyMemberHistory"
        assert fhir["status"] == "completed"
        assert fhir["relationship"]["coding"][0]["code"] == "MTH"
        assert fhir["condition"][0]["code"]["text"] == "Hypermobile"

    def test_family_history_relationship_mapping(self):
        mapping = {"mother": "MTH", "father": "FTH", "sibling": "SIB", "grandmother": "GRMTH", "grandfather": "GRFTH", "grandparent": "GRPRN"}
        for rel, code in mapping.items():
            entity = _make_entity("family_history", f"{rel}: condition", relationship=rel, condition="condition")
            result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
            assert result["fhir_resource"]["relationship"]["coding"][0]["code"] == code, f"Failed for {rel}"

    def test_family_history_display_text(self):
        entity = _make_entity("family_history", "Father: SDHB deletion", relationship="father", condition="SDHB deletion")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert "SDHB deletion" in result["display_text"]
        assert "father" in result["display_text"].lower() or "Father" in result["display_text"]


class TestAssessmentPlanBuilder:
    """Tests for assessment_plan entity → FHIR DocumentReference."""

    def test_assessment_plan_produces_record(self):
        entity = _make_entity("assessment_plan", "#1: IBS treatment plan. #2: Dietary re-introduction.", plan_items=["IBS treatment", "Dietary re-introduction"])
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result is not None
        assert result["record_type"] == "document"
        assert result["fhir_resource_type"] == "DocumentReference"

    def test_assessment_plan_fhir_structure(self):
        entity = _make_entity("assessment_plan", "#1: IBS plan.", plan_items=["IBS plan"])
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        fhir = result["fhir_resource"]
        assert fhir["resourceType"] == "DocumentReference"
        assert fhir["status"] == "current"
        assert fhir["type"]["coding"][0]["code"] == "51847-2"
        assert fhir["type"]["coding"][0]["system"] == "http://loinc.org"
        assert fhir["content"][0]["attachment"]["contentType"] == "text/plain"

    def test_assessment_plan_display_text(self):
        entity = _make_entity("assessment_plan", "#1: IBS. #2: Diet.", plan_items=["IBS", "Diet"])
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert "Assessment & Plan" in result["display_text"]


class TestSocialHistoryBuilder:
    """Tests for social_history entity → FHIR Observation (social-history)."""

    def test_social_history_produces_record(self):
        entity = _make_entity("social_history", "Diet: Low FODMAP", category="diet", value="Low FODMAP")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result is not None
        assert result["record_type"] == "observation"
        assert result["fhir_resource_type"] == "Observation"

    def test_social_history_fhir_structure(self):
        entity = _make_entity("social_history", "Alcohol: avoided", category="alcohol", value="avoided")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        fhir = result["fhir_resource"]
        assert fhir["resourceType"] == "Observation"
        assert fhir["category"][0]["coding"][0]["code"] == "social-history"
        assert fhir["code"]["text"] == "Alcohol"
        assert fhir["valueString"] == "avoided"

    def test_social_history_display_text(self):
        entity = _make_entity("social_history", "Diet: GF/DF", category="diet", value="GF/DF")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert "Diet" in result["display_text"]


class TestExistingEntityTypesUnchanged:
    """Verify existing 6 entity types still work after changes."""

    def test_medication_still_works(self):
        entity = _make_entity("medication", "prucalopride 2mg")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result["record_type"] == "medication"

    def test_condition_still_works(self):
        entity = _make_entity("condition", "Type 2 diabetes", status="active")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result["record_type"] == "condition"

    def test_nonstorable_returns_none(self):
        entity = _make_entity("dosage", "500mg")
        result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/test_expanded_extraction.py -v 2>&1 | head -30
```

Expected: Multiple `KeyError` or assertion failures because the new entity types aren't in `ENTITY_TO_RECORD_TYPE` yet.

- [ ] **Step 3: Expand ENTITY_TO_RECORD_TYPE mapping**

In `backend/app/services/extraction/entity_to_fhir.py`, add the 5 new entries to `ENTITY_TO_RECORD_TYPE`:

```python
ENTITY_TO_RECORD_TYPE: dict[str, tuple[str, str] | None] = {
    # Existing
    "medication": ("medication", "MedicationRequest"),
    "condition": ("condition", "Condition"),
    "lab_result": ("observation", "Observation"),
    "vital": ("observation", "Observation"),
    "procedure": ("procedure", "Procedure"),
    "allergy": ("allergy", "AllergyIntolerance"),
    # New
    "encounter": ("encounter", "Encounter"),
    "imaging_result": ("diagnostic_report", "DiagnosticReport"),
    "family_history": ("family_history", "FamilyMemberHistory"),
    "assessment_plan": ("document", "DocumentReference"),
    "social_history": ("observation", "Observation"),
    # Non-storable (return None)
    "provider": None,
    "dosage": None,
    "route": None,
    "frequency": None,
    "duration": None,
    "date": None,
}
```

- [ ] **Step 4: Add FHIR resource builders to _build_fhir_resource**

In `backend/app/services/extraction/entity_to_fhir.py`, add new branches to `_build_fhir_resource`. Add these after the existing `AllergyIntolerance` branch and before the final return:

```python
    if resource_type == "Encounter":
        visit_type = attrs.get("visit_type", "office")
        class_map = {
            "office": ("AMB", "ambulatory"),
            "telehealth": ("VR", "virtual"),
            "emergency": ("EMER", "emergency"),
            "inpatient": ("IMP", "inpatient encounter"),
        }
        class_code, class_display = class_map.get(visit_type, ("AMB", "ambulatory"))
        resource = {
            "resourceType": "Encounter",
            "status": "finished",
            "class": {"code": class_code, "display": class_display},
        }
        cpt_code = attrs.get("cpt_code")
        if cpt_code:
            resource["type"] = [{"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": cpt_code}]}]
        reason = attrs.get("reason")
        if reason:
            resource["reasonCode"] = [{"text": reason}]
        date_val = attrs.get("date")
        if date_val:
            resource["period"] = {"start": date_val}
        resource["_extraction_metadata"] = extraction_meta
        return resource

    if resource_type == "DiagnosticReport":
        category = attrs.get("category", "imaging")
        resource = {
            "resourceType": "DiagnosticReport",
            "status": "final",
            "category": [{"coding": [{"code": category, "display": category.replace("_", " ").title()}]}],
            "code": {"text": attrs.get("procedure_name", entity.text)},
        }
        findings = attrs.get("findings")
        if findings:
            resource["conclusion"] = findings
        interpretation = attrs.get("interpretation")
        if interpretation:
            resource["conclusionCode"] = [{"text": interpretation}]
        resource["_extraction_metadata"] = extraction_meta
        return resource

    if resource_type == "FamilyMemberHistory":
        relationship = attrs.get("relationship", "unknown")
        rel_map = {
            "mother": ("MTH", "Mother"),
            "father": ("FTH", "Father"),
            "sibling": ("SIB", "Sibling"),
            "sister": ("SIS", "Sister"),
            "brother": ("BRO", "Brother"),
            "grandmother": ("GRMTH", "Grandmother"),
            "grandfather": ("GRFTH", "Grandfather"),
            "grandparent": ("GRPRN", "Grandparent"),
            "aunt": ("AUNT", "Aunt"),
            "uncle": ("UNCLE", "Uncle"),
            "child": ("CHILD", "Child"),
        }
        rel_code, rel_display = rel_map.get(relationship.lower(), ("FAMMEMB", relationship.title()))
        condition_text = attrs.get("condition", entity.text)
        condition_entry: dict = {"code": {"text": condition_text}}
        notes = attrs.get("notes")
        if notes:
            condition_entry["note"] = [{"text": notes}]
        resource = {
            "resourceType": "FamilyMemberHistory",
            "status": "completed",
            "relationship": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode", "code": rel_code, "display": rel_display}],
            },
            "condition": [condition_entry],
            "_extraction_metadata": extraction_meta,
        }
        return resource

    if resource_type == "DocumentReference":
        import base64
        resource = {
            "resourceType": "DocumentReference",
            "status": "current",
            "type": {"coding": [{"system": "http://loinc.org", "code": "51847-2", "display": "Assessment and Plan"}]},
            "content": [{
                "attachment": {
                    "contentType": "text/plain",
                    "data": base64.b64encode(entity.text.encode()).decode(),
                },
            }],
            "_extraction_metadata": extraction_meta,
        }
        plan_items = attrs.get("plan_items")
        if plan_items and isinstance(plan_items, list):
            resource["description"] = "; ".join(plan_items)
        return resource
```

For `social_history`, it already falls through to the existing `Observation` builder for `vital`. Update the existing Observation branch to handle social-history:

```python
    if resource_type == "Observation":
        if entity.entity_class == "lab_result":
            # ... existing lab_result code unchanged ...
        elif entity.entity_class == "social_history":
            category_label = attrs.get("category", "social-history")
            resource = {
                "resourceType": "Observation",
                "status": "final",
                "category": [{"coding": [{"code": "social-history"}]}],
                "code": {"text": category_label.replace("_", " ").title()},
                "valueString": attrs.get("value", entity.text),
                "_extraction_metadata": extraction_meta,
            }
            return resource
        else:
            # ... existing vital code unchanged ...
```

- [ ] **Step 5: Update _build_display_text for new entity types**

In `backend/app/services/extraction/entity_to_fhir.py`, add handlers in `_build_display_text`:

```python
    if entity.entity_class == "encounter":
        visit_type = attrs.get("visit_type", "visit")
        date = attrs.get("date", "")
        return f"{visit_type.title()} encounter{' — ' + date if date else ''}"

    if entity.entity_class == "imaging_result":
        name = attrs.get("procedure_name", entity.text)
        findings = attrs.get("findings", "")
        return f"{name}: {findings}" if findings else name

    if entity.entity_class == "family_history":
        rel = attrs.get("relationship", "Family member")
        condition = attrs.get("condition", entity.text)
        return f"{rel.title()}: {condition}"

    if entity.entity_class == "assessment_plan":
        plan_items = attrs.get("plan_items", [])
        count = len(plan_items) if isinstance(plan_items, list) else 0
        return f"Assessment & Plan ({count} items)" if count else "Assessment & Plan"

    if entity.entity_class == "social_history":
        category = attrs.get("category", "Social")
        value = attrs.get("value", entity.text)
        return f"{category.replace('_', ' ').title()}: {value}"
```

- [ ] **Step 6: Add DiagnosticReport handler in fhir_parser.py build_display_text**

In `backend/app/services/ingestion/fhir_parser.py`, add a handler after the existing `DocumentReference` block (after line 215):

```python
    if resource_type == "DiagnosticReport":
        conclusion = resource.get("conclusion")
        if conclusion:
            code_text = code_obj.get("text", "Diagnostic Report") if code_obj else "Diagnostic Report"
            return f"{code_text}: {conclusion[:100]}"
        return "Diagnostic Report"
```

- [ ] **Step 7: Run tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/test_expanded_extraction.py -v
```

Expected: All 20 tests PASS.

- [ ] **Step 8: Run existing extraction tests to verify no regression**

Run:
```bash
cd backend && python -m pytest tests/test_entity_extraction.py -v
```

Expected: All 18 existing tests still PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/extraction/entity_to_fhir.py backend/app/services/ingestion/fhir_parser.py backend/tests/test_expanded_extraction.py
git commit -m "feat: add FHIR builders for encounter, diagnostic report, family history, A&P, social history"
```

---

### Task 5: Integrate Section Parser into Upload Pipeline

**Files:**
- Modify: `backend/app/api/upload.py`

- [ ] **Step 1: Read current _process_unstructured function**

Read `backend/app/api/upload.py` lines 470-575 to understand the current flow before modifying.

- [ ] **Step 2: Add section parser imports**

At the top of `backend/app/api/upload.py`, add:

```python
from app.services.extraction.section_parser import parse_sections, split_large_section
```

- [ ] **Step 3: Refactor _process_unstructured to use section parsing**

Replace the entity extraction step (Step 3 in the current flow) with section-aware extraction. The key changes are:

1. After PHI scrubbing, call `parse_sections()` to identify document sections
2. Store section data and document metadata on the upload record
3. For each section, run entity extraction (respecting the 2000-char buffer via `split_large_section`)
4. Aggregate entities from all sections
5. Create an Encounter record from document metadata
6. Link all records to the encounter via `linked_encounter_id`
7. Set `source_section` on each record

The modified `_process_unstructured` function should follow this structure:

```python
async def _process_unstructured(upload_id: UUID, file_path: Path, user_id: UUID) -> None:
    """Process an unstructured file through the section-aware extraction pipeline."""
    async with AsyncSessionLocal() as db:
        try:
            upload = await db.get(UploadedFile, upload_id)
            if not upload:
                return
            upload.ingestion_status = "processing"
            upload.processing_started_at = datetime.now(timezone.utc)
            await db.commit()

            # Step 1: Text extraction (unchanged)
            sem = _get_gemini_semaphore()
            async with sem:
                text = await extract_text(str(file_path), settings.gemini_api_key)
            upload.extracted_text = text
            await db.commit()

            # Step 2: PHI scrubbing (unchanged)
            scrubbed_text, deident_report = scrub_phi(text)

            # Step 3: Section parsing (NEW)
            async with sem:
                parsed_doc = await parse_sections(scrubbed_text, settings.gemini_api_key)

            upload.extraction_sections = {
                "sections": [
                    {"type": s.section_type.value, "title": s.title, "char_range": s.char_range}
                    for s in parsed_doc.sections
                ]
            }
            upload.document_metadata = {
                "document_type": parsed_doc.document_type,
                "primary_visit_date": parsed_doc.primary_visit_date,
                "provider": parsed_doc.provider,
                "facility": parsed_doc.facility,
                "section_count": len(parsed_doc.sections),
            }
            await db.commit()

            # Step 4: Per-section entity extraction (NEW — replaces single extraction)
            all_entities = []
            extraction_tasks = []

            for section in parsed_doc.sections:
                chunks = split_large_section(section.text)
                for chunk in chunks:
                    extraction_tasks.append((chunk, section.section_type.value))

            # Process up to 3 sections concurrently
            section_sem = asyncio.Semaphore(3)

            async def extract_chunk(text_chunk: str, section_type: str):
                async with section_sem:
                    async with sem:
                        result = await extract_entities_async(
                            text_chunk, upload.filename, settings.gemini_api_key
                        )
                return result, section_type

            tasks = [extract_chunk(chunk, stype) for chunk, stype in extraction_tasks]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    logger.error("Section extraction failed: %s", r)
                    continue
                extraction_result, section_type = r
                if extraction_result.error:
                    logger.warning("Extraction error in section %s: %s", section_type, extraction_result.error)
                    continue
                for entity in extraction_result.entities:
                    entity.attributes["_source_section"] = section_type
                    all_entities.append(entity)

            # Deduplicate entities within the same document (same text + same type)
            seen = set()
            unique_entities = []
            for entity in all_entities:
                key = (entity.entity_class, entity.text.strip().lower())
                if key not in seen:
                    seen.add(key)
                    unique_entities.append(entity)

            # Store entities on upload
            upload.extraction_entities = [
                {
                    "entity_class": e.entity_class,
                    "text": e.text,
                    "attributes": e.attributes,
                    "start_pos": e.start_pos,
                    "end_pos": e.end_pos,
                    "confidence": e.confidence,
                }
                for e in unique_entities
            ]
            await db.commit()

            # Step 5: Auto-confirm if patient exists (modified — adds encounter linking)
            patient_result = await db.execute(
                select(Patient).where(Patient.user_id == user_id).limit(1)
            )
            patient = patient_result.scalar_one_or_none()

            if patient:
                encounter_id = None
                created_records = []

                for entity in unique_entities:
                    record_dict = entity_to_health_record_dict(
                        entity, user_id, patient.id, upload_id
                    )
                    if record_dict is None:
                        continue
                    record_dict["source_section"] = entity.attributes.get("_source_section")
                    record = HealthRecord(**record_dict)
                    db.add(record)
                    created_records.append((record, entity))

                    # Track encounter ID for linking
                    if entity.entity_class == "encounter":
                        await db.flush()
                        encounter_id = record.id

                # Link all records to the encounter
                if encounter_id:
                    for record, _ in created_records:
                        if record.id != encounter_id:
                            record.linked_encounter_id = encounter_id

                # Create cross-references from A&P DocumentReference to other records
                ap_records = [(r, e) for r, e in created_records if e.entity_class == "assessment_plan"]
                non_ap_records = [(r, e) for r, e in created_records if e.entity_class != "assessment_plan"]
                if ap_records and non_ap_records:
                    from app.models.cross_reference import RecordCrossReference
                    for ap_record, _ in ap_records:
                        await db.flush()  # Ensure ap_record.id is set
                        for other_record, other_entity in non_ap_records:
                            if other_entity.entity_class in ("encounter",):
                                continue  # Don't cross-ref the encounter itself
                            ref_type = {
                                "medication": "prescribes",
                                "condition": "addresses",
                                "lab_result": "supports",
                                "vital": "supports",
                                "procedure": "addresses",
                                "allergy": "addresses",
                                "imaging_result": "supports",
                                "family_history": "supports",
                                "social_history": "supports",
                            }.get(other_entity.entity_class, "addresses")
                            xref = RecordCrossReference(
                                document_record_id=ap_record.id,
                                referenced_record_id=other_record.id,
                                reference_type=ref_type,
                            )
                            db.add(xref)

                await db.commit()
                upload.ingestion_status = "completed"
                upload.record_count = len(created_records)
            else:
                upload.ingestion_status = "awaiting_confirmation"

            upload.processing_completed_at = datetime.now(timezone.utc)
            await db.commit()

        except Exception as e:
            logger.error("Unstructured processing failed for %s: %s", upload_id, e, exc_info=True)
            try:
                upload.ingestion_status = "failed"
                error_type = type(e).__name__
                upload.ingestion_errors = [{"error": "Processing failed. Please retry or contact support.", "error_type": error_type}]
                upload.processing_completed_at = datetime.now(timezone.utc)
                await db.commit()
            except Exception:
                logger.error("Failed to update error status for %s", upload_id, exc_info=True)
```

Note: Keep the existing imports (`extract_text`, `scrub_phi`, `extract_entities_async`, `entity_to_health_record_dict`, `Patient`, `HealthRecord`). Add the new imports from step 2.

- [ ] **Step 4: Run existing upload tests to verify no regression**

Run:
```bash
cd backend && python -m pytest tests/test_upload.py tests/test_unstructured_upload.py -v
```

Expected: Existing tests pass. Some may need mock updates for `parse_sections` — patch it alongside existing mocks if needed.

- [ ] **Step 5: Fix any test failures from new function calls**

If existing unstructured upload tests fail because they don't mock `parse_sections`, add the mock:

```python
@patch("app.api.upload.parse_sections", new_callable=AsyncMock)
```

With a return value of:

```python
ParsedDocument(
    document_type="clinical_note",
    primary_visit_date=None,
    provider=None,
    facility=None,
    sections=[ParsedSection(SectionType.OTHER, "Full Document", "test text")],
)
```

Also patch `split_large_section` if needed (it should work without mocking since it's pure logic).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/upload.py
git commit -m "feat: integrate section-aware extraction into unstructured upload pipeline"
```

---

### Task 6: Pipeline Integration Tests

**Files:**
- Create: `backend/tests/test_pipeline_integration.py`

- [ ] **Step 1: Write integration tests**

Create `backend/tests/test_pipeline_integration.py`:

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.extraction.entity_extractor import ExtractedEntity, ExtractionResult
from app.services.extraction.entity_to_fhir import entity_to_health_record_dict
from app.services.extraction.section_parser import (
    ParsedDocument,
    ParsedSection,
    SectionType,
    parse_sections,
    split_large_section,
)


class TestEntityToFhirRoundTrip:
    """Test that entities from all 11 types produce valid record dicts."""

    ENTITY_CONFIGS = [
        ("medication", "aspirin 81mg", {"medication_group": "aspirin"}),
        ("condition", "Hypertension", {"status": "active"}),
        ("lab_result", "HbA1c 6.5", {"test": "HbA1c", "value": "6.5", "unit": "%"}),
        ("vital", "BP 120/80", {"type": "Blood Pressure"}),
        ("procedure", "Colonoscopy", {"date": "2024-03-15"}),
        ("allergy", "Penicillin", {"reaction": "rash", "severity": "moderate"}),
        ("encounter", "Office visit", {"visit_type": "office", "date": "2026-03-30"}),
        ("imaging_result", "CT Abdomen", {"procedure_name": "CT Abdomen", "findings": "normal", "category": "imaging"}),
        ("family_history", "Father: DM2", {"relationship": "father", "condition": "DM2"}),
        ("assessment_plan", "#1: Continue meds.", {"plan_items": ["Continue medications"]}),
        ("social_history", "Alcohol: none", {"category": "alcohol", "value": "none"}),
    ]

    @pytest.mark.parametrize("entity_class,text,attrs", ENTITY_CONFIGS)
    def test_storable_entity_produces_record(self, entity_class, text, attrs):
        entity = ExtractedEntity(entity_class=entity_class, text=text, attributes=attrs)
        result = entity_to_health_record_dict(entity, uuid4(), uuid4(), uuid4())
        assert result is not None
        assert result["record_type"] in ("medication", "condition", "observation", "procedure", "allergy", "encounter", "diagnostic_report", "family_history", "document")
        assert result["fhir_resource"]["resourceType"] in ("MedicationRequest", "Condition", "Observation", "Procedure", "AllergyIntolerance", "Encounter", "DiagnosticReport", "FamilyMemberHistory", "DocumentReference")
        assert result["display_text"]
        assert result["ai_extracted"] is True
        assert result["confidence_score"] == 0.8

    NONSTORABLE = ["dosage", "route", "frequency", "duration", "date", "provider"]

    @pytest.mark.parametrize("entity_class", NONSTORABLE)
    def test_nonstorable_entity_returns_none(self, entity_class):
        entity = ExtractedEntity(entity_class=entity_class, text="some value")
        result = entity_to_health_record_dict(entity, uuid4(), uuid4())
        assert result is None


class TestSectionParserToEntityPipeline:
    """Test the section parser → entity extraction flow."""

    @pytest.mark.asyncio
    async def test_parsed_sections_feed_into_extraction(self):
        """Verify that parsed sections can be individually extracted."""
        doc = ParsedDocument(
            document_type="clinical_note",
            primary_visit_date="2026-03-30",
            provider="Dr. Test",
            facility="Test Clinic",
            sections=[
                ParsedSection(SectionType.MEDICATIONS, "Medications", "aspirin 81mg daily"),
                ParsedSection(SectionType.LABS, "Labs", "HbA1c 6.5%"),
            ],
        )

        mock_entities_meds = ExtractionResult(
            source_file="test.pdf",
            source_text="aspirin 81mg daily",
            entities=[ExtractedEntity("medication", "aspirin 81mg", {"medication_group": "aspirin"})],
        )
        mock_entities_labs = ExtractionResult(
            source_file="test.pdf",
            source_text="HbA1c 6.5%",
            entities=[ExtractedEntity("lab_result", "HbA1c 6.5", {"test": "HbA1c", "value": "6.5"})],
        )

        with patch(
            "app.services.extraction.entity_extractor.extract_entities_async",
            new_callable=AsyncMock,
            side_effect=[mock_entities_meds, mock_entities_labs],
        ):
            from app.services.extraction.entity_extractor import extract_entities_async

            all_entities = []
            for section in doc.sections:
                result = await extract_entities_async(section.text, "test.pdf", "fake-key")
                for entity in result.entities:
                    entity.attributes["_source_section"] = section.section_type.value
                    all_entities.append(entity)

        assert len(all_entities) == 2
        assert all_entities[0].entity_class == "medication"
        assert all_entities[0].attributes["_source_section"] == "medications"
        assert all_entities[1].entity_class == "lab_result"
        assert all_entities[1].attributes["_source_section"] == "labs"

    def test_large_section_splitting_preserves_content(self):
        """All content is preserved across split chunks."""
        paragraphs = [f"Paragraph {i}. " * 80 for i in range(5)]
        text = "\n\n".join(paragraphs)
        chunks = split_large_section(text, max_chars=1500)
        assert len(chunks) >= 2
        # Every paragraph should appear in at least one chunk
        for para in paragraphs:
            found = any(para[:50] in chunk for chunk in chunks)
            assert found, f"Paragraph starting with '{para[:50]}' not found in any chunk"

    def test_document_dedup_removes_same_entity_from_overlapping_chunks(self):
        """Duplicate entities across chunks are removed by text+type dedup."""
        entities = [
            ExtractedEntity("medication", "aspirin 81mg"),
            ExtractedEntity("medication", "aspirin 81mg"),  # duplicate from overlap
            ExtractedEntity("condition", "Hypertension"),
        ]
        seen = set()
        unique = []
        for e in entities:
            key = (e.entity_class, e.text.strip().lower())
            if key not in seen:
                seen.add(key)
                unique.append(e)
        assert len(unique) == 2

    def test_encounter_record_links_to_other_records(self):
        """Encounter record ID can be used as linked_encounter_id."""
        encounter_entity = ExtractedEntity("encounter", "Visit 03/30", attributes={"visit_type": "office", "date": "2026-03-30"})
        med_entity = ExtractedEntity("medication", "aspirin 81mg")

        user_id, patient_id = uuid4(), uuid4()
        enc_dict = entity_to_health_record_dict(encounter_entity, user_id, patient_id)
        med_dict = entity_to_health_record_dict(med_entity, user_id, patient_id)

        assert enc_dict is not None
        assert med_dict is not None
        # The caller (upload.py) sets linked_encounter_id — here we verify the dict has an id
        assert "id" in enc_dict
        assert "id" in med_dict
```

- [ ] **Step 2: Run tests**

Run:
```bash
cd backend && python -m pytest tests/test_pipeline_integration.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Run full test suite to verify no regressions**

Run:
```bash
cd backend && python -m pytest -x -v --ignore=tests/fidelity 2>&1 | tail -20
```

Expected: All tests pass. If any existing tests fail due to the new columns or imports, fix them.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_pipeline_integration.py
git commit -m "test: add pipeline integration tests for section-aware extraction"
```

---

### Task 7: Run Full Test Suite and Fix Regressions

**Files:**
- Various (depending on what breaks)

- [ ] **Step 1: Run the complete test suite**

Run:
```bash
cd backend && python -m pytest -x -v --ignore=tests/fidelity 2>&1 | tail -40
```

- [ ] **Step 2: Fix any regressions**

Common issues to look for:
- Tests that create `HealthRecord` objects directly may need to handle new nullable columns
- Tests that mock `_process_unstructured` may need `parse_sections` patched
- The conftest TRUNCATE statement must include `record_cross_references`
- Fidelity tests may need `build_display_text` updates for `DiagnosticReport`

Fix each issue as found.

- [ ] **Step 3: Run fidelity tests (column spec only)**

Run:
```bash
cd backend && python -m pytest tests/fidelity/ -v --ignore=tests/fidelity/test_epic_fidelity.py -k "not fidelity" 2>&1 | tail -20
```

- [ ] **Step 4: Commit fixes**

```bash
git add -u
git commit -m "fix: resolve test regressions from smart extraction schema changes"
```

---

### Task 8: Run Migration on Dev Database and Manual Smoke Test

**Files:**
- No file changes — validation only

- [ ] **Step 1: Run migration on dev database**

Run:
```bash
cd backend && alembic upgrade head
```

Expected: Migration applies cleanly.

- [ ] **Step 2: Start backend server**

Run:
```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

Expected: Server starts without errors.

- [ ] **Step 3: Verify new columns exist**

Run:
```bash
psql medtimeline -c "\d health_records" | grep -E "source_section|linked_encounter|merge_metadata"
```

Expected: All three columns visible.

Run:
```bash
psql medtimeline -c "\d record_cross_references"
```

Expected: Table exists with all columns and indexes.

Run:
```bash
psql medtimeline -c "\d uploaded_files" | grep -E "extraction_sections|document_metadata|dedup_summary"
```

Expected: All three columns visible.

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -u
git commit -m "fix: migration and startup verification"
```

---

## Summary

| Task | Description | Est. Tests |
|------|------------|-----------|
| 1 | Database migration — new columns and tables | 0 (schema) |
| 2 | Section parser service | 11 |
| 3 | Expanded clinical examples and entity types | 0 (config) |
| 4 | Entity-to-FHIR builders for 5 new types | 20 |
| 5 | Integrate section parser into upload pipeline | 0 (integration) |
| 6 | Pipeline integration tests | 6 |
| 7 | Full suite regression fix | 0 (fixes) |
| 8 | Dev migration and smoke test | 0 (validation) |
| **Total** | | **~37 new tests** |

After Phase A is complete and verified, Phase B (smart dedup + ingestion review page) will be planned separately.
