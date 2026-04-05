# Phase B: Smart Deduplication & Ingestion Review

**Date:** 2026-04-05
**Status:** Approved
**Parent spec:** `2026-04-04-smart-extraction-and-dedup-design.md`
**Prerequisite:** Phase A (section-aware extraction) — merged

---

## Problem Statement

Users upload data from multiple sources — FHIR bundles, Epic EHI exports, and unstructured documents (PDF/RTF/TIFF). Three scenarios produce duplicates:

1. **Cumulative structured uploads**: A newer FHIR or Epic extract contains all previous records plus new ones. Uploading it creates complete duplicates of everything already in the database.
2. **Cross-system overlap**: Records from an Epic export overlap with a previously uploaded FHIR bundle (same medications, conditions, labs — different source formats).
3. **Unstructured extraction overlap**: AI-extracted entities from a clinical note duplicate records already ingested from structured files.

The current system has no dedup integration during ingestion. Duplicates are only caught via manual `/dedup/scan`, and the existing heuristic detector has no LLM intelligence, no auto-merge, and no field-level merge capability.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Dedup timing | Post-insert scoped scan | Simpler architecture — one dedup pipeline for all sources. Temporary duplicates hidden via `is_duplicate` flag before user sees them |
| Auto-merge exact matches | Yes, with notification (status `completed_with_merges`) | High-fidelity codes (ICD-10, CPT, LOINC) make exact matching reliable. Undo available. |
| Update handling | Present for review with side-by-side diff | Updates need human judgment (dose change vs. correction). LLM classifies, user confirms. |
| Bulk resolution | Category-grouped (by record type) | Clinical context grouping ("5 medication updates") enables informed bulk decisions |
| Review scope | Per-upload only | Natural flow (upload → review → done). Existing admin Dedup tab covers global sweep. |
| Dedup trigger surface | All upload types (FHIR, Epic, unstructured) | Structured uploads are the primary source of cumulative duplicates |

---

## Architecture

### Two-Tier Dedup Engine

```
Upload completes (any type)
  → Post-insert scoped scan: new upload's records vs existing patient records
  → Tier 1: Heuristic filter (threshold 0.5)
      → Score >= 0.95: auto_merged bucket
      → Score 0.5–0.95: needs_llm_review bucket
  → Tier 2: LLM Judge (Gemini, 3 concurrent)
      → duplicate: auto-merge
      → update: present for review (with field diff)
      → related: present for review
      → distinct: auto-dismiss
  → Update upload status + dedup_summary
  → User reviews via /upload/{id}/review
```

### Integration Points

Three places trigger the dedup pipeline:

1. **`_process_unstructured` (upload.py)** — After auto-confirm creates records from AI extraction
2. **`coordinator.py`** — After `bulk_inserter` finishes for FHIR/Epic structured uploads
3. **`confirm_extraction` endpoint** — After manual entity confirmation (also adds missing encounter linking + cross-references from Phase A)

All three call the same function: `run_upload_dedup(upload_id, patient_id, db)`.

---

## Dedup Engine Details

### Heuristic Filter — Upgraded `detector.py`

New method: `detect_upload_duplicates(upload_id, patient_id, db)` — scopes comparison to "records from this upload vs all other records for this patient" (not all-vs-all).

Changes from existing detector:
- Threshold lowered: 0.7 → 0.5
- New scoring signal: `source_section` match bonus +0.15
- Returns two buckets: `auto_merged` (>= 0.95) and `needs_llm_review` (0.5–0.95)
- Existing scoring signals unchanged: code match +0.4, exact text +0.3, fuzzy text +0.2, date proximity +0.2, status match +0.1, cross-source +0.1

### LLM Judge — New `services/dedup/llm_judge.py`

Input: List of candidate pairs from heuristic filter (the `needs_llm_review` bucket).

For each pair, sends both FHIR resources to Gemini with a classification prompt. Returns:
- `classification`: `duplicate` | `update` | `related` | `distinct`
- `confidence`: 0.0–1.0
- `explanation`: Human-readable reasoning (shown in review UI)
- `field_diff`: For `update` classifications — which fields changed, old vs new values

Auto-resolution rules based on LLM output:
- `duplicate` with confidence >= 0.8 → auto-merge
- `distinct` with confidence >= 0.8 → auto-dismiss
- Everything else → `needs_review`

Bounded to 3 concurrent Gemini calls via semaphore (shares the global Gemini semaphore).

### DedupCandidate Model Updates

New columns on `dedup_candidates`:
- `llm_classification` — enum: duplicate/update/related/distinct (nullable, null = not yet judged)
- `llm_confidence` — float (nullable)
- `llm_explanation` — text (nullable)
- `field_diff` — JSONB (nullable, for update pairs: `{"dosageInstruction": {"old": "500mg", "new": "1000mg"}}`)
- `auto_resolved` — boolean, default false
- `source_upload_id` — FK to `uploaded_files` (which upload triggered this candidate)

---

## Upload Status Flow

```
processing
  → dedup_scanning (new intermediate state)
    → completed             (no duplicates found)
    → completed_with_merges (exact duplicates auto-merged, count in dedup_summary)
    → awaiting_review       (fuzzy matches need user attention)
  → awaiting_confirmation   (no patient — unchanged)
  → failed                  (unchanged)
```

### `dedup_summary` JSONB (on UploadedFile)

Column already exists (added in Phase A), currently unused. Populated after dedup scan:

```json
{
  "total_candidates": 15,
  "auto_merged": 12,
  "needs_review": 3,
  "dismissed": 0,
  "by_type": {
    "medication": 5,
    "condition": 7,
    "observation": 3
  }
}
```

---

## Review API Endpoints

All on the existing upload router (`/api/v1/upload`):

### `GET /upload/{id}/review`

Returns review data for an upload:

```json
{
  "upload": {
    "id": "uuid",
    "filename": "export.json",
    "uploaded_at": "2026-04-05T...",
    "record_count": 200,
    "status": "awaiting_review",
    "dedup_summary": { ... }
  },
  "auto_merged": [
    {
      "candidate_id": "uuid",
      "primary": { "id": "uuid", "display_text": "Metformin 500mg", "record_type": "medication" },
      "secondary": { "id": "uuid", "display_text": "Metformin 500mg", "record_type": "medication" },
      "similarity_score": 0.98,
      "merged_at": "2026-04-05T..."
    }
  ],
  "needs_review": {
    "medication": [
      {
        "candidate_id": "uuid",
        "primary": { "id": "uuid", "display_text": "Metformin 500mg", "record_type": "medication", "fhir_resource": { ... } },
        "secondary": { "id": "uuid", "display_text": "Metformin 1000mg", "record_type": "medication", "fhir_resource": { ... } },
        "similarity_score": 0.72,
        "llm_classification": "update",
        "llm_confidence": 0.85,
        "llm_explanation": "Same medication with dose increase from 500mg to 1000mg",
        "field_diff": {
          "dosageInstruction": { "old": "500mg daily", "new": "1000mg daily" }
        }
      }
    ],
    "condition": [ ... ]
  }
}
```

### `POST /upload/{id}/review/resolve`

Bulk resolution:

```json
{
  "resolutions": [
    { "candidate_id": "uuid", "action": "merge" },
    { "candidate_id": "uuid", "action": "update", "field_overrides": ["clinicalStatus", "dosageInstruction"] },
    { "candidate_id": "uuid", "action": "dismiss" },
    { "candidate_id": "uuid", "action": "keep_both" }
  ]
}
```

Actions:
- `merge`: Keep primary, mark secondary as `is_duplicate=true`
- `update`: Apply selected fields from secondary to primary (or all changed fields if `field_overrides` omitted), mark secondary as duplicate
- `dismiss`: Not a duplicate — set candidate status to `dismissed`
- `keep_both`: Related but distinct — set candidate status to `dismissed`, no record changes

All merges/updates create provenance records. After all candidates resolved, upload status transitions to `completed`.

### `POST /upload/{id}/review/undo-merge`

```json
{ "candidate_id": "uuid" }
```

Restores the secondary record (clears `is_duplicate`), reverts field changes on primary using `previous_values` from `merge_metadata`, resets candidate status to `pending`.

---

## Field-Level Merge & Provenance

### Field-level merge flow

When resolving an `update` candidate:
1. LLM judge's `field_diff` identifies changed FHIR fields
2. Review UI shows old vs new per field with checkboxes
3. User accepts all, rejects all, or cherry-picks fields
4. Accepted changes applied to primary record's `fhir_resource` JSONB
5. Display text regenerated from updated FHIR resource

### `merge_metadata` JSONB (on primary record)

```json
{
  "merged_from": "uuid-of-secondary",
  "merged_at": "2026-04-05T...",
  "merge_type": "update",
  "source_upload_id": "uuid-of-upload",
  "fields_updated": ["clinicalStatus", "dosageInstruction"],
  "fields_kept": ["code", "medicationCodeableConcept"],
  "previous_values": {
    "clinicalStatus": { "coding": [{ "code": "active" }] }
  }
}
```

### Provenance

Every merge/update creates a record in the `provenance` table:
- `action`: `"merge"` or `"field_update"`
- `agent`: `"system/auto-merge"` or `"user/{user_id}"`
- `source_file_id`: the upload that triggered the dedup

### Undo support

`previous_values` in `merge_metadata` enables restoring the primary record's original fields. Undo reverts the FHIR resource, clears merge_metadata, and un-marks the secondary record.

---

## Review UI (Frontend)

### Page: `/upload/[id]/review`

Accessible from upload history and post-upload redirect when status is `completed_with_merges` or `awaiting_review`.

**Layout:**

1. **Header**: Upload filename, date, record count, status badge
2. **Summary bar**: "12 auto-merged, 3 need review" with quick stats
3. **Auto-merged section** (collapsible, default collapsed): List of auto-merged pairs with "Undo" button per pair
4. **Needs Review section** (primary focus): Grouped by record type

**Category-grouped review cards:**
- Group header: "Medications (2 updates)" with "Accept All" / "Decline All" buttons
- Each candidate row:
  - Compact summary: "Metformin 500mg → 1000mg" or "Hypertension (active → resolved)"
  - LLM confidence badge (high/medium/low color)
  - Expandable: side-by-side FHIR field diff, LLM explanation, field-level checkboxes for cherry-picking
  - Per-row actions: Accept / Decline / Edit
- **Sticky bulk action bar** (bottom): "Accept Selected (5)" / "Decline Selected" / resolved vs remaining count

**Post-resolution**: After all candidates resolved, status updates to `completed` and page shows "All resolved" confirmation state.

---

## Database Migration

New columns on `dedup_candidates`:
```sql
ALTER TABLE dedup_candidates ADD COLUMN llm_classification VARCHAR(20);
ALTER TABLE dedup_candidates ADD COLUMN llm_confidence FLOAT;
ALTER TABLE dedup_candidates ADD COLUMN llm_explanation TEXT;
ALTER TABLE dedup_candidates ADD COLUMN field_diff JSONB;
ALTER TABLE dedup_candidates ADD COLUMN auto_resolved BOOLEAN DEFAULT FALSE;
ALTER TABLE dedup_candidates ADD COLUMN source_upload_id UUID REFERENCES uploaded_files(id);
```

Index: `CREATE INDEX ix_dedup_source_upload ON dedup_candidates(source_upload_id) WHERE source_upload_id IS NOT NULL;`

No new tables needed — all other columns (`dedup_summary`, `merge_metadata`) already exist from Phase A.

---

## Testing Strategy

### Unit tests (~24 tests)
- **Heuristic filter** (~10): Threshold 0.5, source_section bonus, upload-scoped detection, auto-merge bucketing at 0.95, cross-source scoring
- **LLM judge** (~8): Classification parsing, confidence thresholds, field diff extraction, auto-resolution rules, error handling/fallback, concurrent call limiting
- **Field-level merge** (~6): FHIR field application, merge_metadata generation, previous_values storage, display text regeneration, undo restores original

### Integration tests (~10 tests)
- Structured upload → dedup trigger: Upload FHIR bundle with known duplicates, verify candidates created and auto-merges applied (~4)
- Cross-system: Upload Epic then FHIR with overlapping records, verify candidates scoped correctly (~3)
- Bulk resolution: Resolve multiple candidates in one call, verify statuses and provenance (~3)

### API tests (~10 tests)
- `GET /upload/{id}/review`: Returns grouped candidates with diffs
- `POST /upload/{id}/review/resolve`: Handles merge/update/dismiss/keep_both actions
- `POST /upload/{id}/review/undo-merge`: Restores records
- Upload status transitions through all states
- Undo merge reverts field changes
- Bulk resolution creates provenance for each action
- Error cases: invalid candidate_id, wrong upload owner, already-resolved candidates

**Total: ~44 new tests**, all mocking Gemini calls. LLM judge gets one `@pytest.mark.slow` live test.

---

## HIPAA Compliance

- PHI never sent to Gemini during dedup — the LLM judge receives only FHIR resource JSON (clinical codes, values, dates), not patient-identifying data. For AI-extracted records, text was PHI-scrubbed before extraction. For structured records (FHIR/Epic), the `fhir_resource` JSONB contains clinical data only — PII (name, DOB, MRN) lives on the `patients` table, not in health record resources. The LLM judge prompt must explicitly exclude any patient-level fields if they appear in the resource.
- Audit logging on all review endpoints (resolve, undo-merge)
- User-scoped access: review endpoint enforces `upload.user_id == authenticated_user_id`
- Merge provenance creates a full audit trail of who merged what and when
- Error messages in dedup endpoints follow HIPAA pattern (no stack traces, sanitized errors)

---

## Scope Boundary

**In scope:**
- Dedup engine (heuristic + LLM judge)
- Ingestion integration (all three trigger points)
- Review API endpoints
- Review UI page with category-grouped bulk resolution
- Field-level merge with provenance and undo
- Upload status flow changes

**Out of scope (future):**
- Automatic re-scan when records are edited
- Dedup across patients (only within same patient)
- Real-time dedup during streaming ingestion
- Admin bulk-merge across all patients
