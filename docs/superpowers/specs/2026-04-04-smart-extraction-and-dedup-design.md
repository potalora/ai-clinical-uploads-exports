# Smart Multi-Record Extraction & Intelligent Deduplication

**Date:** 2026-04-04
**Status:** Approved
**Delivery:** Two phases — Phase A (extraction pipeline) then Phase B (smart dedup + review UI)

---

## Problem Statement

Users upload unstructured clinical documents (PDFs, RTFs, TIFFs) that contain multiple types of health records within a single file. A clinical note like a visit summary may contain medications, conditions, lab results, procedures, imaging findings, family history, assessment plans, and encounter metadata — all in one document.

The current extraction pipeline has critical limitations:
- **2000-character buffer** truncates large documents, losing ~90% of content
- **No document structure awareness** — sections like Medications, Labs, Assessment are flattened
- **Only 6 entity types** extracted (medication, condition, lab_result, vital, procedure, allergy)
- **No encounter extraction** — the visit itself isn't captured
- **Manual-only deduplication** with heuristic scoring, no LLM intelligence
- **All-or-nothing merge** — can't pick fields from each record

Additionally, users frequently upload cumulative data where files contain both previously-uploaded records and new ones. The system needs to automatically handle this overlap.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Multi-visit documents | One encounter per primary visit date only | Historical references are context, not standalone encounters |
| Large document handling | LLM section parsing → per-section entity extraction | Each tool's strength: Gemini for structure, LangExtract for entities |
| Dedup behavior | Hybrid: auto-merge exact, suggest fuzzy | Reduces review fatigue while keeping users in control of ambiguous cases |
| Record type expansion | Full coverage: encounter, imaging, family hx, A&P, social hx | FHIR R4B and Epic EHI standards compliance |
| Dedup intelligence | Heuristics as filter, LLM as judge | Keeps LLM calls proportional to actual candidates, not full record count |
| Assessment & Plan modeling | DocumentReference with cross-references | Preserves narrative, captures relationships, no duplication |
| Performance strategy | Bounded concurrency, 3 parallel Gemini calls | Fits 16GB M4 MacBook Air comfortably |
| Review page persistence | Persistent, accessible from upload history | No extra storage cost — view joins existing data |
| Review page location | Dedicated page at /upload/{id}/review | Complex dedup decisions deserve dedicated screen real estate |

---

## Phase A: Section-Aware Extraction Pipeline

### Section Parser

New service: `services/extraction/section_parser.py`

A Gemini Flash call takes the full PHI-scrubbed text and returns structured JSON identifying logical sections within the document.

**Input:** Full scrubbed document text
**Output:**
```json
{
  "document_type": "clinical_note",
  "primary_visit_date": "2026-03-30",
  "provider": "Dr. Elena Ivanina",
  "facility": "The Center for Integrative Gut Health",
  "sections": [
    {
      "type": "medications",
      "title": "Medications & Allergies",
      "text": "nitazoxanide 500 mg tablet...",
      "char_range": [450, 1200]
    }
  ]
}
```

**Section type enum:** `medications`, `assessment`, `clinical_note`, `labs`, `review_of_systems`, `history`, `physical_exam`, `assessment_plan`, `imaging`, `family_history`, `social_history`, `allergies`, `procedures`, `vitals`, `other`.

**Model:** Uses `gemini-3-flash-preview` (same as text extraction and summarization, configured via `GEMINI_MODEL`).

**Large section handling:** Sections exceeding 2000 characters are split at paragraph boundaries with 200-character overlap. Entities spanning the overlap are deduplicated by entity text + type within the same document.

**Concurrency:** Up to 3 sections extracted in parallel using asyncio semaphore, extending the existing `_gemini_semaphore` pattern.

### Expanded Record Types

**Current entity types (6):** medication, condition, lab_result, vital, procedure, allergy

**New entity types (5):**

| Entity Type | FHIR Resource | record_type | Source Sections |
|---|---|---|---|
| `encounter` | Encounter | `encounter` | clinical_note, assessment_plan |
| `imaging_result` | DiagnosticReport | `diagnostic_report` | imaging, history, clinical_note |
| `family_history` | FamilyMemberHistory | `family_history` | family_history, history |
| `assessment_plan` | DocumentReference | `document` | assessment_plan |
| `social_history` | Observation (social-history) | `observation` | social_history, history |

### FHIR Resource Construction

**Encounter:**
```json
{
  "resourceType": "Encounter",
  "status": "finished",
  "class": {"code": "VR", "display": "virtual"},
  "type": [{"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": "99214"}]}],
  "period": {"start": "2026-03-30T11:00:00"},
  "participant": [{"individual": {"display": "[PROVIDER]"}}],
  "serviceProvider": {"display": "[FACILITY]"},
  "reasonCode": [{"text": "Interval follow-up"}]
}
```
- Class codes follow FHIR ValueSet: AMB, VR, EMER, IMP, etc.
- CPT code extracted from Plan section when available.
- Visit date from section parser's `primary_visit_date`.

**DiagnosticReport (imaging/diagnostic results):**
```json
{
  "resourceType": "DiagnosticReport",
  "status": "final",
  "category": [{"coding": [{"code": "imaging", "display": "Imaging"}]}],
  "code": {"text": "EGD"},
  "effectiveDateTime": "2024-03-26",
  "conclusion": "50 eosinophils at GEJ, normal gastric and duodenal biopsies",
  "presentedForm": [{"contentType": "text/plain", "data": "..."}]
}
```
- Categories: `imaging`, `endoscopy`, `nuclear-medicine`, `pulmonary`, `laboratory-panel`.
- Captures procedure name, date, findings, and interpretation.
- Distinct from Procedure — DiagnosticReport captures *results*, Procedure captures the *act*.

**FamilyMemberHistory:**
```json
{
  "resourceType": "FamilyMemberHistory",
  "status": "completed",
  "relationship": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode", "code": "MTH", "display": "Mother"}]},
  "condition": [{"code": {"text": "Hypermobile"}, "note": [{"text": "mitral valve prolapse, EOE"}]}]
}
```
- Relationship codes from HL7 v3-RoleCode: MTH, FTH, GRFTH, GRMTH, SIB, etc.
- Multiple conditions per family member grouped under one resource.
- Extraction prompt updated to produce family_history as a storable entity type.

**DocumentReference (Assessment & Plan):**
```json
{
  "resourceType": "DocumentReference",
  "status": "current",
  "type": {"coding": [{"system": "http://loinc.org", "code": "51847-2", "display": "Assessment and Plan"}]},
  "date": "2026-03-30",
  "content": [{"attachment": {"contentType": "text/plain", "data": "<base64 of A&P text>"}}],
  "context": {
    "encounter": [{"reference": "Encounter/<uuid>"}],
    "related": [{"reference": "Condition/<uuid>"}, {"reference": "MedicationRequest/<uuid>"}]
  }
}
```
- LOINC code 51847-2 for Assessment & Plan.
- Cross-references to extracted conditions, medications, labs via `context.related`.
- Links to the encounter via `context.encounter`.
- Full narrative text preserved in attachment.

**Observation — social-history:**
```json
{
  "resourceType": "Observation",
  "status": "final",
  "category": [{"coding": [{"code": "social-history"}]}],
  "code": {"text": "Diet"},
  "valueString": "Low-er FODMAP, gluten-free, dairy-free. Triggers: fructose corn syrup, garlic, onions, lactose"
}
```
- Social history subtypes: diet, alcohol, tobacco, exercise, birth_history, occupation.
- Each distinct social factor becomes its own Observation.

### Entity-to-FHIR Mapping Updates

`services/extraction/entity_to_fhir.py` extended with builders for all 5 new entity types. `build_display_text()` expanded with handlers for `diagnostic_report` and `family_history`.

Epic mapper alignment: existing `FamilyHxMapper` already maps to `family_history` record_type. `entity_to_fhir.py` produces the same FHIR shape for consistency.

### Clinical Examples Updates

`services/extraction/clinical_examples.py` updated:
- `imaging_result` added as storable entity with attributes: `procedure_name`, `date`, `findings`, `interpretation`, `category`
- `family_history` added as storable entity with attributes: `relationship`, `condition`, `status`, `notes`
- `encounter` added as storable entity with attributes: `visit_type`, `date`, `cpt_code`, `reason`
- `social_history` added as storable entity with attributes: `category`, `value`, `date`
- `assessment_plan` added as storable entity with attributes: `plan_items` (array)
- Few-shot examples updated to demonstrate extraction from a multi-section clinical note

---

## Phase B: Smart Deduplication & Ingestion Review

### Dedup Engine: Two-Tier Architecture

**Tier 1: Heuristic Filter (modified existing)**

Runs automatically after records are created from extraction.

Changes from current system:
- **Lower threshold:** 0.5 instead of 0.7 (wider net for LLM evaluation)
- **Scope narrowing:** Only compares new records from this upload against existing records for the same patient — not all-vs-all
- **Exact match auto-merge:** Score >= 0.95 with matching `(record_type, code_value, effective_date, display_text)` — auto-merged, logged, no LLM call
- **New scoring signal:** +0.15 for same `source_section` type

Output split into:
- `auto_merged`: score >= 0.95, exact match criteria met
- `needs_llm_review`: score 0.5–0.95

**Tier 2: LLM Judge** (`services/dedup/llm_judge.py`)

New service. For each candidate pair in `needs_llm_review`, sends both records (PHI-scrubbed) to Gemini Flash (`gemini-3-flash-preview` via `GEMINI_MODEL`).

Prompt sends: record_type, display_text, FHIR resource summary, effective_date, source for both records.

**LLM response schema:**
```json
{
  "classification": "duplicate | update | related | distinct",
  "confidence": 0.92,
  "explanation": "Same medication (prucalopride/Motegrity), updated prescription with different SIG.",
  "recommendation": "merge",
  "preferred_primary": "b",
  "merge_notes": "Keep Record B as primary (newer date, more specific SIG)."
}
```

**Classification meanings:**
- **duplicate**: Same clinical fact, same time period. Merge recommended.
- **update**: Same entity evolved over time (dose change, status change). Merge recommended, keep newer as primary.
- **related**: Clinically connected but distinct records. Keep both.
- **distinct**: Not duplicates despite surface similarity. Keep both.

**Auto-resolution rules:**
- Auto-merge: heuristic >= 0.95 AND exact match on type+code+date+text
- Auto-merge: LLM classification == "duplicate" AND LLM confidence >= 0.9
- Flag for review: LLM "duplicate" with confidence < 0.9, all "update" classifications, "related" with confidence < 0.8
- Keep as distinct (no flag): LLM "distinct" with confidence >= 0.8

**Concurrency:** Up to 3 parallel LLM judge calls.

### Field-Level Merge

Replaces all-or-nothing merge. When merging, the primary record can inherit specific fields from the secondary (e.g., keep the newer SIG but preserve the older start date). `merge_metadata` JSONB column on `health_records` stores what was merged from which source. Provenance record created for every merge.

### Ingestion Review API

**New endpoints:**

```
GET  /upload/:id/review          — Full ingestion review data
POST /upload/:id/review/resolve  — Batch resolve dedup candidates
POST /upload/:id/review/undo-merge — Undo an auto-merge
```

**GET /upload/:id/review response:**
```json
{
  "upload_id": "uuid",
  "filename": "note_361370.pdf",
  "uploaded_at": "2026-03-30T15:00:00Z",
  "document_metadata": {
    "document_type": "clinical_note",
    "primary_visit_date": "2026-03-30",
    "provider": "[PROVIDER]",
    "facility": "[FACILITY]",
    "page_count": 8,
    "sections_identified": 8
  },
  "extraction_summary": {
    "sections": [
      {"type": "medications", "title": "Medications & Allergies", "records_extracted": 6}
    ],
    "total_records_extracted": 27,
    "by_type": {"medication": 6, "condition": 3, "observation": 12, "encounter": 1, "diagnostic_report": 5, "family_history": 4, "document": 1, "allergy": 1}
  },
  "dedup_summary": {
    "auto_merged": [
      {
        "candidate_id": "uuid",
        "kept_record": {"id": "uuid", "display_text": "...", "record_type": "..."},
        "merged_record": {"id": "uuid", "display_text": "...", "record_type": "..."},
        "similarity_score": 0.97,
        "can_undo": true
      }
    ],
    "needs_review": [
      {
        "candidate_id": "uuid",
        "record_a": {"id": "uuid", "display_text": "...", "record_type": "...", "effective_date": "...", "source": "this upload"},
        "record_b": {"id": "uuid", "display_text": "...", "record_type": "...", "effective_date": "...", "source": "upload from 2026-02-15"},
        "similarity_score": 0.82,
        "llm_classification": "update",
        "llm_confidence": 0.88,
        "llm_explanation": "Same medication, updated prescription with different SIG...",
        "llm_recommendation": "merge",
        "preferred_primary_id": "uuid"
      }
    ],
    "auto_distinct": 3
  },
  "new_records": [
    {"id": "uuid", "record_type": "encounter", "display_text": "Telehealth visit 03/30/2026", "source_section": "clinical_note"}
  ]
}
```

**POST /upload/:id/review/resolve request:**
```json
{
  "resolutions": [
    {"candidate_id": "uuid", "action": "merge", "primary_record_id": "uuid"},
    {"candidate_id": "uuid", "action": "keep_both"},
    {"candidate_id": "uuid", "action": "merge", "primary_record_id": "uuid", "field_overrides": {"effective_date": "2026-03-30", "status": "active"}}
  ]
}
```

**POST /upload/:id/review/undo-merge request:**
```json
{"candidate_id": "uuid"}
```

### Ingestion Review Frontend

**Page:** `/upload/[id]/review`

**Accessible from:**
- Upload page — "Review" button after processing completes
- Upload history — "Review" link on each row
- Upload status polling — redirects to review when complete

**Layout (three zones):**

1. **Header** — filename, upload date, document metadata (type, visit date, pages, sections found)

2. **Extraction breakdown** — collapsible section-by-section list showing what was extracted from each document section, with record type badges and counts. Records clickable (opens RecordDetailSheet).

3. **Dedup panel:**
   - **Auto-merged** (collapsed by default) — list of silent merges, each with "Undo" button
   - **Needs review** — side-by-side comparison cards with LLM explanation, Merge/Keep Both buttons, optional field-level override expand
   - **Summary bar** — counts of new/merged/flagged/distinct

---

## Updated Processing Pipeline

**End-to-end flow:**

```
1. Upload received → validate → UploadedFile created (status="processing")
2. Text extraction [1 Gemini call] → stored in extracted_text
3. PHI scrubbing [local] → scrubbed text for all subsequent steps
4. Section parsing [1 Gemini call] → sections JSON stored in extraction_sections
5. Per-section entity extraction [N calls, 3 concurrent] → entities aggregated
6. Entity → FHIR → HealthRecords [local] → records created with source_section, linked_encounter_id
7. Dedup check [heuristic + M LLM calls, 3 concurrent] → candidates created/resolved
8. Status finalized → "completed" or "awaiting_review"
```

**Performance budget (8-page clinical note, 16GB M4 MacBook Air):**

| Step | API calls | Est. time | Memory |
|---|---|---|---|
| Text extraction | 1 Gemini vision | 3-5s | ~10MB |
| PHI scrub | 0 (local) | <100ms | negligible |
| Section parsing | 1 Gemini text | 2-3s | ~1MB |
| Entity extraction | 3-5 (3 concurrent) | 4-8s | ~5MB peak |
| FHIR conversion | 0 (local) | <200ms | negligible |
| Dedup heuristic | 0 (local) | <500ms | ~2MB |
| Dedup LLM judge | 2-5 (3 concurrent) | 3-6s | ~1MB |
| **Total** | **7-12 calls** | **~15-25s** | **~19MB peak** |

---

## Database Migration

Single Alembic migration. All changes additive (nullable columns), no breaking changes.

### health_records table
- Add `source_section` (VARCHAR, nullable) — document section the record was extracted from
- Add `linked_encounter_id` (UUID FK → health_records.id, nullable) — links records to their encounter
- Add `merge_metadata` (JSONB, nullable) — field-level merge history

### New table: record_cross_references
```sql
CREATE TABLE record_cross_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_record_id UUID NOT NULL REFERENCES health_records(id),
    referenced_record_id UUID NOT NULL REFERENCES health_records(id),
    reference_type VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ix_cross_ref_pair ON record_cross_references(document_record_id, referenced_record_id);
CREATE INDEX ix_cross_ref_referenced ON record_cross_references(referenced_record_id);
```

### dedup_candidates table
- Add `llm_classification` (VARCHAR, nullable) — duplicate/update/related/distinct
- Add `llm_confidence` (FLOAT, nullable)
- Add `llm_explanation` (TEXT, nullable)
- Add `llm_recommendation` (VARCHAR, nullable)
- Add `preferred_primary_id` (UUID FK → health_records.id, nullable)
- Add `auto_resolved` (BOOLEAN, default false)
- Add `source_upload_id` (UUID FK → uploaded_files.id, nullable)

### uploaded_files table
- Add `extraction_sections` (JSONB, nullable)
- Add `document_metadata` (JSONB, nullable)
- Add `dedup_summary` (JSONB, nullable)

### New indexes
- `ix_health_records_linked_encounter` on `health_records(linked_encounter_id)` WHERE NOT NULL
- `ix_dedup_source_upload` on `dedup_candidates(source_upload_id)` WHERE NOT NULL
- `ix_health_records_source_file_section` on `health_records(source_file_id, source_section)` WHERE NOT NULL

---

## Testing Strategy

### New test files (~105 tests, bringing total to ~440)

| File | Est. Count | Scope |
|---|---|---|
| `test_section_parser.py` | ~15 | Section identification, type enum coverage, large doc splitting, paragraph boundary handling, malformed documents |
| `test_expanded_extraction.py` | ~25 | New entity types (encounter, imaging_result, family_history, assessment_plan, social_history), FHIR resource construction, cross-reference generation, display_text |
| `test_llm_judge.py` | ~18 | All 4 classifications, confidence thresholds, auto-merge rules, PHI scrubbing, structured output parsing, retry logic |
| `test_smart_dedup.py` | ~20 | End-to-end dedup: heuristic filter, exact match auto-merge, LLM judge routing, field-level merge, undo, batch resolution |
| `test_ingestion_review.py` | ~15 | Review endpoints, batch resolve, undo-merge, persistent access, status transitions |
| `test_pipeline_integration.py` | ~12 | Full pipeline: upload → sections → entities → records → dedup, record counts, encounter linking, cross-references |

### Testing approach
- **Unit tests** mock Gemini responses with fixtures based on the sample PDF structure. No live API calls.
- **Slow tests** (`@pytest.mark.slow`) run actual Gemini calls against synthetic clinical text. Requires `GEMINI_API_KEY`.
- **Fidelity tests** extend existing suite with `family_history` and `diagnostic_report` coverage.

### Key test scenarios
1. Multi-section document produces records tagged with correct `source_section`, all linked to same encounter
2. Cumulative upload — same document twice, exact duplicates auto-merged, review shows merges
3. Field-level merge — merge two medications, override SIG from secondary, verify `merge_metadata`
4. Cross-reference integrity — A&P DocumentReference references conditions/medications from same document
5. Large section splitting — section >2000 chars split at paragraph boundaries, overlap entities deduplicated
6. Undo auto-merge — restored record visible, candidate status reset to pending

### Not in scope
- Frontend e2e tests (Playwright)
- Load/stress testing
- Real PHI test data (synthetic fixtures only)

---

## API Summary

### New endpoints
```
GET  /api/v1/upload/:id/review          — Ingestion review data
POST /api/v1/upload/:id/review/resolve  — Batch resolve dedup candidates
POST /api/v1/upload/:id/review/undo-merge — Undo an auto-merge
```

### Modified endpoints
```
GET  /api/v1/upload/:id/status    — New status value: "awaiting_review"
GET  /api/v1/upload/history       — Each row includes review availability indicator
POST /api/v1/upload/unstructured  — Pipeline now includes section parsing + auto-dedup
POST /api/v1/upload/trigger-extraction — Same, extended pipeline
```

### Unchanged endpoints
All existing record, timeline, dashboard, summary, auth, and dedup endpoints remain unchanged. The existing `/dedup/scan` and `/dedup/candidates` continue to work for manual dedup workflows.

---

## New files

### Backend
- `app/services/extraction/section_parser.py` — Gemini-powered document section parser
- `app/services/dedup/llm_judge.py` — LLM-powered dedup classification
- `app/models/cross_reference.py` — RecordCrossReference model
- `app/schemas/review.py` — Ingestion review request/response schemas
- `app/api/review.py` — Review endpoints (mounted under upload router)
- `tests/test_section_parser.py`
- `tests/test_expanded_extraction.py`
- `tests/test_llm_judge.py`
- `tests/test_smart_dedup.py`
- `tests/test_ingestion_review.py`
- `tests/test_pipeline_integration.py`
- `frontend/src/app/(dashboard)/upload/[id]/review/page.tsx` — Ingestion review page

### Modified files
- `app/services/extraction/entity_extractor.py` — Section-aware extraction
- `app/services/extraction/entity_to_fhir.py` — 5 new entity type builders
- `app/services/extraction/clinical_examples.py` — New entity types + examples
- `app/services/dedup/detector.py` — Lowered threshold, scoped comparison, new scoring signal
- `app/api/upload.py` — Extended pipeline with section parsing + auto-dedup
- `app/models/deduplication.py` — New LLM columns
- `app/models/record.py` — New columns (source_section, linked_encounter_id, merge_metadata)
- `app/models/uploaded_file.py` — New columns (extraction_sections, document_metadata, dedup_summary)
- `app/schemas/dedup.py` — LLM classification fields
- `app/schemas/upload.py` — Review-related response fields
- `app/utils/coding.py` — build_display_text handlers for new types
- `alembic/versions/` — New migration
- `frontend/src/app/(dashboard)/upload/page.tsx` — Review button integration
- `frontend/src/app/(dashboard)/admin/page.tsx` — LLM explanation in dedup tab
