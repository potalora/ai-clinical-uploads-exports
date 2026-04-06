# CDA XML / IHE XDM Ingestion Pipeline — Design Spec

> **For agentic workers:** This spec describes the CDA XML ingestion pipeline. Use superpowers:writing-plans to create the implementation plan from this spec.

**Goal:** Add native support for ingesting C-CDA (Consolidated Clinical Document Architecture) documents packaged in IHE XDM (Cross-enterprise Document Media Interchange) format, converting structured clinical data to FHIR R4 resources and integrating with the existing dedup pipeline.

**Motivation:** Epic MyChart health summary exports use the IHE XDM format — a directory/ZIP containing CDA XML documents, a PDF rendering, HTML views, and a manifest. The current ingestion pipeline has no XML support, so these exports can only be processed through the unstructured PDF path, losing all structured clinical data (coded entries, LOINC/SNOMED codes, discrete observations). This pipeline extracts the high-fidelity structured data directly from the CDA XML documents.

---

## Architecture Overview

```
ZIP/Directory Upload
        |
        v
  coordinator.py --- detect_file_type()
        |
        +-- .json -> FHIR parser (existing)
        +-- .tsv  -> Epic parser (existing)
        +-- .pdf/.rtf/.tiff -> Unstructured pipeline (existing)
        |
        +-- METADATA.XML detected -> NEW: IHE XDM pipeline
                |
                v
        xdm_parser.py --- parse METADATA.XML
                |         (document inventory, hashes, patient info)
                v
        Format prioritization
                |         (CDA XMLs -> structured pipeline)
                |         (PDFs/HTML -> skip, log as "structured preferred")
                v
        cda_parser.py --- for each DOC*.XML:
                |         1. Validate hash against manifest
                |         2. Convert CDA -> FHIR R4 via python-fhir-converter
                |         3. Post-process: tag source metadata, handle custom sections
                v
        Intra-upload dedup (cda_dedup.py)
                |         (exact match across documents: same code + date + value -> keep one)
                |         (link provenance to all source documents)
                v
        bulk_insert_records() (existing)
                |
                v
        Upload-scoped dedup engine (existing Phase B)
                |         (heuristic + LLM judge against DB records)
                v
        Done (status: completed | completed_with_merges | awaiting_review)
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mixed formats in directory | Prefer structured (CDA XML), skip PDF | CDA XML has coded entries with LOINC/SNOMED codes, exact dates, structured values. PDF extraction via Gemini produces lower-fidelity duplicates. Avoids wasted API calls. |
| Overlapping CDA documents | Parse all 6, intra-upload exact-match dedup | All documents share core sections (allergies, meds, problems) but differ in scope. Parsing all captures the full clinical picture; intra-upload dedup collapses identical entries. |
| Parsing engine | `python-fhir-converter` (MIT) + custom post-processing | Library handles namespace-aware XML parsing, template OID disambiguation, coded data types. Custom layer adds source tracking, metadata enrichment, custom section handling. |
| Manifest handling | Use METADATA.XML for discovery, hashes, patient info | Provides file integrity checks, patient identification for matching, document type info. Graceful fallback to file-extension discovery if manifest is malformed. |

---

## Components

### 1. `xdm_parser.py` — IHE XDM Manifest Parser

**Location:** `backend/app/services/ingestion/xdm_parser.py`

**Responsibility:** Parse METADATA.XML, build document inventory, extract patient demographics.

**Data structures:**

```python
@dataclass
class XDMDocument:
    uri: str                    # "DOC0001.XML"
    hash: str                   # SHA-1 from manifest
    size: int                   # bytes
    creation_time: str          # "20260406003208"
    mime_type: str              # "text/xml"
    author_institution: str     # "Premise Health"

@dataclass
class XDMManifest:
    documents: list[XDMDocument]
    patient_id: str | None      # from sourcePatientId
    patient_name: str | None    # from PID-5
    patient_dob: str | None     # from PID-7
```

**Behavior:**
- Parses the ebXML `<SubmitObjectsRequest>` registry format using `lxml`
- Extracts `<ExtrinsicObject>` entries with their slots (URI, hash, size, creationTime)
- Extracts patient info from `sourcePatientInfo` PID fields
- Returns ordered document list filtered to `mimeType="text/xml"`
- Non-XML entries (PDF, HTML) included in manifest but flagged for skipping

### 2. `cda_parser.py` — CDA-to-FHIR Conversion + Post-Processing

**Location:** `backend/app/services/ingestion/cda_parser.py`

**Responsibility:** Convert each CDA XML document to FHIR resources with source metadata.

**Pipeline per document:**

1. **Hash validation** — compute SHA-1 of file, compare against manifest hash. Skip on mismatch (log warning).
2. **CDA-to-FHIR conversion** — use `python-fhir-converter`'s CCD template to produce FHIR R4 Bundle JSON.
3. **Post-processing** — for each resource in the bundle:
   - Tag with `_extraction_metadata`: `source_format: "cda_r2"`, `source_document`, `source_section` (LOINC code), `source_institution`
   - Extract `effective_date`, `code_system`, `code_value`, `code_display` using existing `map_fhir_resource()` logic
   - Determine `record_type` from FHIR `resourceType`
4. **Custom section handling** — sections with non-LOINC codes (`X-CE-PFD`, `X-DOCCMT`) or sections the library doesn't recognize:
   - Map to `DocumentReference` with narrative HTML preserved in `content.attachment.data`
   - Tag `source_section` with the custom code for traceability

**Key function:**

```python
async def parse_cda_document(
    file_path: Path,
    manifest_doc: XDMDocument | None,
) -> list[dict]:
    """Convert a single CDA XML document to a list of mapped FHIR records."""
```

### 3. `cda_dedup.py` — Intra-Upload Cross-Document Dedup

**Location:** `backend/app/services/ingestion/cda_dedup.py`

**Responsibility:** Collapse identical records across multiple CDA documents before DB insertion.

**Algorithm:**

```
For each record from all documents:
    key = (record_type, code_value, code_system, effective_date, normalized_value)
    if key already seen:
        append source_document to existing record's provenance list
        increment dedup counter
    else:
        add to unique records dict
        track key -> record
```

- Pure in-memory operation, no DB queries
- Runs before `bulk_insert_records()`
- Exact match only — same clinical fact across documents collapses to one record
- Provenance tracks all source documents for each deduplicated record
- Returns `(unique_records: list[dict], stats: CdaDedupStats)`

**Stats dataclass:**

```python
@dataclass
class CdaDedupStats:
    total_parsed: int           # total records from all documents
    unique_records: int         # after dedup
    duplicates_collapsed: int   # total_parsed - unique_records
    records_per_document: dict[str, int]  # DOC0001.XML: 65, DOC0002.XML: 76, ...
```

### 4. Coordinator Integration

**File:** `backend/app/services/ingestion/coordinator.py`

**Changes:**

In `_ingest_zip()`, after extracting the ZIP:
1. Recursively scan extracted directory tree for `METADATA.XML` with `<SubmitObjectsRequest>` root element (IHE XDM places it at `IHE_XDM/<PatientDir>/METADATA.XML`, but scan recursively for robustness)
2. If found → route to new `_ingest_xdm(xdm_dir: Path, upload_id, patient_id, user_id, db)` where `xdm_dir` is the directory containing METADATA.XML (CDA documents are co-located)
3. If not found → existing routing (TSV → Epic, JSON → FHIR, PDF → unstructured)

The `_ingest_xdm()` method:
1. Parse manifest via `xdm_parser`
2. Filter to XML documents only
3. Log skipped files (PDF, HTML, TXT) with reason `"structured_preferred"`
4. For each XML document: convert via `cda_parser`
5. Run `cda_dedup` across all documents
6. Insert via `bulk_insert_records()`
7. Run upload-scoped dedup (existing Phase B pipeline)
8. Update upload status

---

## Data Flow — Happy Path

1. User uploads `HealthSummary.zip` via `/upload` or `/upload/epic-export`
2. `coordinator._ingest_zip()` extracts contents
3. Detects `METADATA.XML` → routes to `_ingest_xdm()`
4. `xdm_parser` parses manifest:
   - 6 CDA XML documents found
   - 1 PDF found → logged as skipped (structured preferred)
   - Patient demographics extracted for matching
5. For each CDA document (DOC0001-DOC0006):
   a. Validate file hash against manifest SHA-1
   b. Convert CDA → FHIR R4 bundle via `python-fhir-converter`
   c. Post-process: tag source metadata, handle custom sections
   d. Collect all mapped records
6. `cda_dedup` collapses identical records across documents:
   - Input: ~400 records (6 docs x ~65 entries)
   - Output: ~80-120 unique records + provenance links
7. `bulk_insert_records()` inserts unique records (batches of 100)
8. Upload-scoped dedup engine runs against existing DB records
9. Status set to `completed` / `completed_with_merges` / `awaiting_review`

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Hash mismatch | Log warning, skip document, continue with others. Record in upload errors. |
| Library conversion fails on a document | Log error with document name, skip that document, continue. Partial success OK. |
| Custom section not recognized by library | Fallback: capture narrative text as DocumentReference. Never silently drop data. |
| No CDA documents in manifest (all non-XML) | Fall through to existing pipeline routing (PDF → unstructured, etc.) |
| METADATA.XML malformed | Fall back to file-extension discovery: scan for `*.XML` with `<ClinicalDocument>` root. Log warning. |
| Patient not found in DB | Create patient from manifest demographics (same as FHIR/Epic path). |
| All documents fail | Mark upload as `failed`, store errors. |

### Skipped File Logging

Files skipped due to structured-over-unstructured preference are logged in the upload's `ingestion_errors` JSONB:

```json
{
  "skipped_files": [
    {
      "file": "1 of 1 - My Health Summary.PDF",
      "reason": "structured_preferred",
      "message": "Skipped: CDA XML documents provide higher-fidelity structured data"
    }
  ]
}
```

### Ingestion Progress

Upload status flow follows existing conventions:
- `processing` → parsing manifest + converting documents
- `dedup_scanning` → running cross-DB dedup
- `completed` / `completed_with_merges` / `awaiting_review`

Progress percentage: `documents_processed / total_documents * 100`

---

## CDA Section Coverage

The pipeline handles all standard C-CDA sections via `python-fhir-converter` templates:

| LOINC Code | Section | FHIR Resource |
|------------|---------|---------------|
| 48765-2 | Allergies | AllergyIntolerance |
| 10160-0 | Medications | MedicationRequest |
| 11450-4 | Active Problems | Condition |
| 11348-0 | Resolved Problems | Condition |
| 30954-2 | Results (Labs) | Observation, DiagnosticReport |
| 8716-3 | Vital Signs | Observation (vital-signs) |
| 11369-6 | Immunizations | Immunization |
| 46240-8 | Encounters | Encounter |
| 29762-2 | Social History | Observation (social-history) |
| 47519-4 | Procedures | Procedure |
| 18776-5 | Plan of Treatment | CarePlan, ServiceRequest |
| 29299-5 | Reason for Visit | Encounter (reason) |
| 42349-1 | Reason for Referral | ServiceRequest |
| 85847-2 | Care Teams | CareTeam |
| 51848-0 | Visit Diagnoses | Condition (encounter-diagnosis) |
| 10164-2 | Progress Notes | DocumentReference |
| 48768-6 | Insurance | Coverage (stored as DocumentReference) |
| 47420-5 | Functional Status | Observation |
| 66149-6 | Ordered Prescriptions | MedicationRequest |

**Custom sections** (X-CE-PFD, X-DOCCMT, etc.) → `DocumentReference` with narrative preserved.

---

## New Dependency

```
python-fhir-converter>=0.3.0
```

- **License:** MIT
- **Transitive deps:** `python-liquid` (BSD), `xmltodict` (MIT), `pyjson5` (Apache 2.0), `isodate` (BSD)
- **No GPL in the chain**
- **Python 3.12 compatible:** Yes

---

## Files Changed

### New Files

| File | Purpose |
|------|---------|
| `backend/app/services/ingestion/xdm_parser.py` | IHE XDM manifest parser |
| `backend/app/services/ingestion/cda_parser.py` | CDA→FHIR conversion + post-processing |
| `backend/app/services/ingestion/cda_dedup.py` | Intra-upload cross-document dedup |
| `backend/tests/test_xdm_parser.py` | XDM manifest parser tests (~8) |
| `backend/tests/test_cda_parser.py` | CDA conversion tests (~12) |
| `backend/tests/test_cda_dedup.py` | Intra-upload dedup tests (~6) |
| `backend/tests/test_xdm_ingestion.py` | Integration tests (~8) |
| `backend/tests/fidelity/test_cda_fidelity.py` | Real-data fidelity tests (~10) |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/services/ingestion/coordinator.py` | Add XDM detection in `_ingest_zip()`, new `_ingest_xdm()` method |
| `backend/pyproject.toml` or `requirements.txt` | Add `python-fhir-converter>=0.3.0` |

---

## Testing Strategy

### Unit Tests (~26 tests)

**`test_xdm_parser.py` (~8 tests):**
- Parse valid METADATA.XML → correct document count, hashes, patient info
- Handle missing/malformed METADATA.XML → graceful fallback
- Extract patient demographics from PID fields
- Filter documents by mime type (text/xml vs application/pdf)
- Handle empty manifest (no documents)

**`test_cda_parser.py` (~12 tests):**
- Convert CDA XML → FHIR bundle → correct resource types
- Post-processing tags source_format, source_document, source_section
- Custom section (X-CE-PFD, X-DOCCMT) → DocumentReference with narrative
- Hash validation: valid hash passes, mismatched hash skips with warning
- Handle malformed CDA XML gracefully (skip, don't crash)
- Major section types produce correct FHIR resources (allergies → AllergyIntolerance, meds → MedicationRequest, problems → Condition, results → Observation, vitals → Observation, immunizations → Immunization)

**`test_cda_dedup.py` (~6 tests):**
- Identical records across 2 documents → collapse to 1 with both in provenance
- Different records across documents → both kept
- Same code but different dates → both kept
- Same code + date but different values → both kept
- Empty input → empty output
- Single document → no dedup needed

### Integration Tests (~8 tests) — `test_xdm_ingestion.py`

- Full pipeline: ZIP with XDM structure → records in DB
- Coordinator routes XDM correctly (not to Epic/FHIR parsers)
- PDF in XDM package skipped, not processed through unstructured pipeline
- Intra-upload dedup reduces record count
- Upload-scoped dedup detects matches against existing DB records
- Status progression: processing → dedup_scanning → final status
- Skipped files logged in upload errors
- Upload with only non-XML documents falls through to existing pipelines

### Real-Data Fidelity Tests (~10 tests) — `test_cda_fidelity.py`

- Parse actual HealthSummary export directory
- Verify all 6 documents parse successfully
- Verify section coverage: all 20 section types represented
- Verify intra-upload dedup: unique records < total parsed
- Verify resource type distribution
- Verify custom sections captured as DocumentReference
- Verify patient demographics from manifest
- Skip when fixture directory absent (`@pytest.mark.fidelity`)

**Total: ~44 new tests**

---

## HIPAA Considerations

- CDA XML contains PHI (patient name, DOB, addresses in header) — same handling as FHIR bundles
- Patient demographics extracted from manifest encrypted at rest (existing encryption_service)
- No data sent to external APIs during CDA parsing — all local processing via `python-fhir-converter`
- Audit logging already covers upload endpoints
- Provenance records created for each ingested record (existing pattern)
- PHI scrubber not needed for this pipeline (no AI/Gemini calls involved in CDA parsing)

---

## Scope Boundaries

**In scope:**
- IHE XDM package detection and routing
- METADATA.XML manifest parsing
- CDA R2 / C-CDA XML → FHIR R4 conversion via `python-fhir-converter`
- Custom section fallback to DocumentReference
- Intra-upload cross-document exact-match dedup
- Integration with existing upload-scoped dedup (Phase B)
- Hash validation against manifest
- Skipped file logging

**Out of scope:**
- CDA document creation/export
- CDA R1 support (only R2/C-CDA)
- HL7 v2 message parsing
- Non-Epic XDM packages (designed for Epic MyChart exports, but should work with any conformant IHE XDM)
- New UI components (uses existing upload + admin views)
- New API endpoints (uses existing upload endpoints)
