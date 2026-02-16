# Backend Engineering Handoff: AI-Enabled Clinical Uploads/Exports API Contract

This document defines the complete API contract between the AI-Enabled Clinical Uploads/Exports frontend and backend. All endpoints are prefixed with `/api/v1`. The frontend expects JSON responses with the schemas defined below.

---

## Authentication

All authenticated endpoints require a `Bearer` token in the `Authorization` header. The frontend stores JWT tokens in localStorage via Zustand and attaches them automatically through the `ApiClient` class (`src/lib/api.ts`).

### POST `/auth/register`

Create a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "display_name": "Optional Name"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "Optional Name",
  "is_active": true
}
```

**Errors:** `400` (validation), `409` (email already exists)

### POST `/auth/login`

Authenticate and receive JWT tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response (200):**
```json
{
  "access_token": "jwt-string",
  "refresh_token": "jwt-string",
  "token_type": "bearer"
}
```

**Errors:** `401` (invalid credentials)

### POST `/auth/refresh`

Refresh the access token using a refresh token. The old refresh token is revoked and a new token pair is issued.

**Request:**
```json
{
  "refresh_token": "jwt-string"
}
```

**Response (200):**
```json
{
  "access_token": "jwt-string",
  "refresh_token": "jwt-string",
  "token_type": "bearer"
}
```

**Errors:** `401` (invalid or expired refresh token)

### POST `/auth/logout`

Revoke the current session. Requires auth header.

**Response (204):** No content.

### GET `/auth/me`

Get the authenticated user's profile. Used by the Admin > SYS tab.

**Response (200):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "Optional Name",
  "is_active": true
}
```

---

## Dashboard

### GET `/dashboard/overview`

Primary data source for the Home pane. Returns aggregate statistics and recent records.

**Response (200):**
```json
{
  "total_records": 347,
  "total_patients": 1,
  "total_uploads": 3,
  "records_by_type": {
    "condition": 42,
    "observation": 128,
    "medication": 65,
    "encounter": 30,
    "immunization": 12,
    "procedure": 20,
    "document": 15,
    "allergy": 8,
    "imaging": 5,
    "diagnostic_report": 22
  },
  "recent_records": [
    {
      "id": "uuid",
      "record_type": "observation",
      "display_text": "Blood pressure: 120/80 mmHg",
      "effective_date": "2024-01-25T14:00:00Z",
      "created_at": "2024-02-01T10:30:00Z"
    }
  ],
  "date_range_start": "2019-03-15T00:00:00Z",
  "date_range_end": "2024-01-25T14:00:00Z"
}
```

**Notes:**
- `recent_records` should return the 10 most recently created records
- `records_by_type` keys are the `record_type` field values from `health_records`
- `date_range_start` and `date_range_end` are the min/max `effective_date` across all records
- All data MUST be scoped to the authenticated user (`user_id` filter)

### GET `/dashboard/labs`

Lab-specific dashboard data. Used by the Admin > LABS tab.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Items per page (max 100) |

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "display_text": "Glucose [Mass/volume] in Blood",
      "effective_date": "2024-01-15T08:00:00Z",
      "value": 95,
      "unit": "mg/dL",
      "reference_low": 70,
      "reference_high": 100,
      "interpretation": "N",
      "code_display": "Glucose",
      "code_value": "2345-7"
    }
  ],
  "total": 128,
  "page": 1,
  "page_size": 20
}
```

**Interpretation codes:** `N` (normal), `H` (high), `HH` (critical high), `L` (low), `LL` (critical low), `A` (abnormal), `AA` (critical abnormal).

**Notes:**
- Extract from `health_records` where `record_type = 'observation'` and the FHIR resource contains lab-relevant category codes
- `value` can be numeric or string; `unit` is the UCUM unit from the FHIR Observation
- `reference_low`/`reference_high` come from `referenceRange` in the FHIR resource

### GET `/dashboard/patients`

List patients belonging to the current user.

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "fhir_id": "Patient/12345",
      "gender": "female"
    }
  ],
  "total": 1
}
```

---

## Records

### GET `/records`

Paginated, filterable record list. Primary data source for Admin > ALL tab and type-specific tabs.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Items per page (max 100) |
| `record_type` | string | - | Filter by record type (e.g., `medication`, `condition`) |
| `search` | string | - | Full-text search on `display_text` and `code_display` |

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "patient_id": "uuid",
      "record_type": "medication",
      "fhir_resource_type": "MedicationRequest",
      "fhir_resource": { "...full FHIR R4B resource..." },
      "source_format": "fhir_r4",
      "effective_date": "2024-01-15T00:00:00Z",
      "status": "active",
      "category": ["medication"],
      "code_system": "http://www.nlm.nih.gov/research/umls/rxnorm",
      "code_value": "197361",
      "code_display": "Lisinopril 10 MG Oral Tablet",
      "display_text": "Lisinopril 10 MG — Take once daily",
      "created_at": "2024-02-01T10:30:00Z"
    }
  ],
  "total": 347,
  "page": 1,
  "page_size": 20
}
```

### GET `/records/:id`

Single record detail. Used by RecordDetailSheet and deep-link record detail page.

**Response (200):** Same schema as a single item from the `items` array above.

**Errors:** `404` (record not found or belongs to different user)

### DELETE `/records/:id`

Soft-delete a record (sets `deleted_at` timestamp). **Never hard-delete.**

**Response (204):** No content.

---

## Timeline

### GET `/timeline`

Date-ordered event list for the Timeline pane. Lighter than `/records` — doesn't include full FHIR resources.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `record_type` | string | - | Filter by type |
| `limit` | int | 200 | Max events to return |

**Response (200):**
```json
{
  "events": [
    {
      "id": "uuid",
      "record_type": "observation",
      "display_text": "Blood pressure: 120/80 mmHg",
      "effective_date": "2024-01-25T14:00:00Z",
      "code_display": "Blood pressure panel",
      "category": ["vital-signs"]
    }
  ],
  "total": 347
}
```

**Notes:**
- Events should be ordered by `effective_date DESC` (newest first)
- `total` is the total count matching filters (before limit is applied)
- Frontend groups events by month/year for display

---

## Upload & Ingestion

### POST `/upload`

Upload a file for ingestion. Accepts multipart form data.

**Request:** `multipart/form-data` with field `file` (JSON or ZIP)

**Response (200):**
```json
{
  "upload_id": "uuid",
  "status": "completed",
  "records_inserted": 142,
  "errors": []
}
```

**Notes:**
- For small files: process synchronously and return results immediately
- For large files (>5s processing): return `202 Accepted` with `upload_id` and `status: "processing"`, then process in background
- File size limit: 500MB per file, 5GB for Epic exports
- Supported MIME types: `application/json`, `application/zip`
- Validate file integrity before processing

### GET `/upload/:id/status`

Poll for ingestion progress on large imports. Frontend polls every 2 seconds.

**Response (200):**
```json
{
  "upload_id": "uuid",
  "ingestion_status": "processing",
  "ingestion_progress": {
    "current_file": "MEDICATIONS.tsv",
    "file_index": 12,
    "total_files": 47,
    "records_ingested": 8400,
    "records_failed": 3
  },
  "ingestion_errors": [
    {
      "file": "ORDER_PROC.tsv",
      "row": 445,
      "error": "invalid date format"
    }
  ],
  "record_count": 8400,
  "total_file_count": 47,
  "processing_started_at": "2024-02-01T10:30:00Z",
  "processing_completed_at": null
}
```

**Status values:** `pending`, `processing`, `completed`, `failed`, `partial`

**Frontend behavior:**
- Polls while status is `pending` or `processing`
- Stops polling when `completed`, `failed`, or `partial`
- Shows partial results (records already committed) even during processing

### GET `/upload/:id/errors`

Get row-level ingestion errors for a specific upload.

**Response (200):**
```json
{
  "errors": [
    {
      "file": "ORDER_PROC.tsv",
      "row": 445,
      "error": "invalid date format"
    }
  ]
}
```

### GET `/upload/history`

List upload history with record counts.

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "filename": "records.json",
      "ingestion_status": "completed",
      "record_count": 142,
      "file_size_bytes": 524288,
      "created_at": "2024-02-01T10:30:00Z"
    }
  ],
  "total": 3
}
```

### POST `/upload/unstructured`

Upload a PDF, RTF, or TIFF for AI-powered text extraction and entity extraction. Processing happens in the background.

**Request:** `multipart/form-data` with field `file` (PDF, RTF, TIF, or TIFF)

**Response (202):**
```json
{
  "upload_id": "uuid",
  "status": "processing",
  "file_type": "pdf"
}
```

**Notes:**
- Allowed extensions: `.pdf`, `.rtf`, `.tif`, `.tiff`
- Magic byte validation ensures content matches claimed file type
- Processing pipeline: text extraction (Gemini for PDF/TIFF, `striprtf` for RTF) → PHI scrubbing → entity extraction (LangExtract via Gemini)
- Final status is `awaiting_confirmation` when entities are ready for user review
- File size limit: 500MB

### POST `/upload/unstructured-batch`

Upload multiple unstructured files for concurrent processing.

**Request:** `multipart/form-data` with field `files` (multiple PDF/RTF/TIFF files)

**Response (202):**
```json
{
  "uploads": [
    {
      "upload_id": "uuid",
      "status": "processing",
      "file_type": "pdf"
    }
  ],
  "total": 3
}
```

**Notes:**
- Files with unsupported extensions, invalid magic bytes, or that exceed size limits are silently skipped
- Each file is processed independently in the background

### GET `/upload/:id/extraction`

Get extracted text and entities for an unstructured upload.

**Response (200):**
```json
{
  "upload_id": "uuid",
  "status": "awaiting_confirmation",
  "extracted_text_preview": "First 500 characters of extracted text...",
  "entities": [
    {
      "entity_class": "medication",
      "text": "Lisinopril 10mg",
      "attributes": { "dosage": "10mg", "frequency": "daily" },
      "start_pos": 120,
      "end_pos": 135,
      "confidence": 0.92
    }
  ],
  "error": null
}
```

**Entity classes:** `medication`, `condition`, `procedure`, `lab_result`, `vital_sign`, `allergy`, `provider`

**Notes:**
- `extracted_text_preview` is the first 500 characters of the extracted text
- `entities` may be empty if extraction is still processing or if no entities were found
- `error` contains a user-safe error message if extraction failed

### POST `/upload/:id/confirm-extraction`

Confirm extracted entities and create FHIR health records.

**Request:**
```json
{
  "patient_id": "uuid",
  "confirmed_entities": [
    {
      "entity_class": "medication",
      "text": "Lisinopril 10mg",
      "attributes": { "dosage": "10mg" },
      "start_pos": 120,
      "end_pos": 135,
      "confidence": 0.92
    }
  ]
}
```

**Response (200):**
```json
{
  "upload_id": "uuid",
  "records_created": 5,
  "status": "completed"
}
```

**Notes:**
- The user reviews extracted entities in the UI and submits only the confirmed ones
- Each confirmed entity is mapped to a FHIR resource and stored as a `HealthRecord` with `ai_extracted=true`
- The upload status transitions from `awaiting_confirmation` to `completed`

---

## AI Summary

**Dual-mode operation:** Mode 1 (`build-prompt`) constructs de-identified prompts for the user to execute externally — no API key needed. Mode 2 (`generate`) calls the Gemini API directly — requires `GEMINI_API_KEY`. All health data is de-identified via the PHI scrubber before any AI operation in both modes.

### POST `/summary/build-prompt`

Build a de-identified prompt from health records. Returns the prompt for external use — does not call any AI service.

**Request:**
```json
{
  "patient_id": "uuid",
  "summary_type": "full",
  "category": null,
  "date_from": null,
  "date_to": null,
  "record_ids": null,
  "record_types": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `patient_id` | UUID | Required. Patient to summarize. |
| `summary_type` | string | `full`, `category`, `date_range`, or `single_record` |
| `category` | string? | Filter by record category (e.g., `medication`) |
| `date_from` | datetime? | Start of date range |
| `date_to` | datetime? | End of date range |
| `record_ids` | UUID[]? | Specific records to include |
| `record_types` | string[]? | Filter by record types (e.g., `["medication", "condition"]`) |

**`summary_type` values:** `full`, `category`, `date_range`, `single_record`

**Response (200):**
```json
{
  "id": "uuid",
  "summary_type": "full",
  "system_prompt": "You are a medical records summarizer...",
  "user_prompt": "The following de-identified health records span 2019-2024...",
  "target_model": "gemini-3-flash-preview",
  "suggested_config": {
    "temperature": 0.3,
    "max_output_tokens": 4096,
    "thinking_level": "low"
  },
  "record_count": 47,
  "de_identification_report": {
    "names_scrubbed": 12,
    "dates_generalized": 8,
    "mrns_removed": 3,
    "addresses_removed": 2
  },
  "copyable_payload": "...single string ready to paste into Google AI Studio...",
  "generated_at": "2024-02-01T10:30:00Z"
}
```

**PHI De-identification Requirements:**
- All 18 HIPAA identifiers MUST be scrubbed before embedding in any prompt
- Names → `[PATIENT]`, `[PROVIDER]`, `[CONTACT]`
- Dates (except year) → generalized to month/year
- SSN, MRN, phone, email, addresses → replaced with type tags
- `de_identification_report` logs what was scrubbed (types and counts, NOT values)
- `copyable_payload` is the full combined prompt (system + user) as a single copyable string

**Prompt constraints (MUST be embedded in system_prompt):**
- "Do NOT provide any diagnoses, treatment recommendations, medical advice, or clinical decision support."
- "Summarize the factual medical information only."
- "If information is unclear or potentially conflicting, note this without interpretation."

### GET `/summary/prompts`

List previously built prompts.

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "summary_type": "full",
      "system_prompt": "...",
      "user_prompt": "...",
      "target_model": "gemini-3-flash-preview",
      "suggested_config": {},
      "record_count": 47,
      "de_identification_report": {},
      "copyable_payload": "...",
      "generated_at": "2024-02-01T10:30:00Z"
    }
  ]
}
```

### GET `/summary/prompts/:id`

Get a single prompt detail, including any stored response.

**Response (200):**
```json
{
  "id": "uuid",
  "summary_type": "full",
  "system_prompt": "...",
  "user_prompt": "...",
  "target_model": "gemini-3-flash-preview",
  "suggested_config": {},
  "record_count": 47,
  "de_identification_report": {},
  "copyable_payload": "...",
  "response_text": "Previously pasted or generated response, if any",
  "generated_at": "2024-02-01T10:30:00Z"
}
```

**Errors:** `404` (prompt not found or belongs to different user)

### POST `/summary/paste-response`

User pastes back an AI response for storage. This is optional and user-initiated.

**Request:**
```json
{
  "prompt_id": "uuid",
  "response_text": "The patient's records show..."
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "prompt_id": "uuid",
  "response_pasted_at": "2024-02-01T11:00:00Z"
}
```

### POST `/summary/generate`

Generate an AI summary by calling the Gemini API directly. Requires `GEMINI_API_KEY`.

**Request:**
```json
{
  "patient_id": "uuid",
  "summary_type": "full",
  "category": null,
  "date_from": null,
  "date_to": null,
  "output_format": "natural_language",
  "custom_system_prompt": null,
  "custom_user_prompt": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `patient_id` | UUID | Required. Patient to summarize. |
| `summary_type` | string | `full`, `category`, `date_range`, or `single_record` |
| `output_format` | string | `natural_language`, `json`, or `both` |
| `custom_system_prompt` | string? | Override the default system prompt |
| `custom_user_prompt` | string? | Override the default user prompt |

**Response (200):**
```json
{
  "id": "uuid",
  "natural_language": "The patient's records show...",
  "json_data": null,
  "record_count": 47,
  "duplicate_warning": {
    "total_records": 50,
    "deduped_records": 47,
    "duplicates_excluded": 3,
    "message": "3 duplicate records were excluded from this summary."
  },
  "de_identification_report": {
    "names_scrubbed": 12,
    "dates_generalized": 8
  },
  "model_used": "gemini-3-flash-preview",
  "generated_at": "2024-02-01T10:30:00Z"
}
```

**Notes:**
- `natural_language` contains the text summary (null when `output_format` is `json`)
- `json_data` contains structured output (null when `output_format` is `natural_language`)
- `duplicate_warning` is present only when duplicates were detected and excluded
- All health data is de-identified via the PHI scrubber before the Gemini API call

**Errors:** `400` (no records found, invalid request), `404` (patient not found)

### GET `/summary/responses`

List stored AI responses (both pasted and API-generated).

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "summary_type": "full",
      "record_count": 47,
      "response_text": "First 200 characters of the response...",
      "response_pasted_at": "2024-02-01T11:00:00Z"
    }
  ],
  "total": 5
}
```

**Notes:**
- `response_text` is truncated to 200 characters in the list view
- Use `GET /summary/prompts/:id` to retrieve the full response

---

## Deduplication

### GET `/dedup/candidates`

List deduplication candidates (paginated).

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `limit` | int | 20 | Items per page |

**Response (200):**
```json
{
  "items": [
    {
      "id": "uuid",
      "similarity_score": 0.92,
      "match_reasons": {
        "same_code": true,
        "same_date": true,
        "similar_text": false
      },
      "status": "pending",
      "record_a": {
        "id": "uuid",
        "display_text": "Lisinopril 10 MG Oral Tablet",
        "record_type": "medication",
        "source_format": "fhir_r4",
        "effective_date": "2024-01-15T00:00:00Z"
      },
      "record_b": {
        "id": "uuid",
        "display_text": "LISINOPRIL 10MG TAB",
        "record_type": "medication",
        "source_format": "epic_ehi",
        "effective_date": "2024-01-15T00:00:00Z"
      }
    }
  ],
  "total": 5
}
```

**Notes:**
- Only `pending` candidates are returned (server-side filter)
- `record_a` and `record_b` can be `null` if a record was deleted

### POST `/dedup/scan`

Trigger a deduplication scan across all records.

**Response (200):**
```json
{
  "candidates_found": 5
}
```

### POST `/dedup/merge`

Merge two duplicate records (keep primary, archive secondary).

**Request:**
```json
{
  "candidate_id": "uuid"
}
```

**Response (200):**
```json
{
  "status": "merged",
  "primary_record_id": "uuid",
  "archived_record_id": "uuid"
}
```

### POST `/dedup/dismiss`

Dismiss a candidate pair as not duplicates.

**Request:**
```json
{
  "candidate_id": "uuid"
}
```

**Response (200):**
```json
{
  "status": "dismissed"
}
```

---

## Record Types

The frontend recognizes these `record_type` values and assigns distinct visual styling to each:

| `record_type` | Label | Short Code | FHIR Resource |
|---------------|-------|------------|---------------|
| `condition` | Conditions | COND | Condition |
| `observation` | Labs & Vitals | OBS | Observation |
| `medication` | Medications | MED | MedicationRequest / MedicationStatement |
| `encounter` | Encounters | ENC | Encounter |
| `immunization` | Immunizations | IMMUN | Immunization |
| `procedure` | Procedures | PROC | Procedure |
| `document` | Documents | DOC | DocumentReference |
| `allergy` | Allergies | ALRG | AllergyIntolerance |
| `imaging` | Imaging | IMG | ImagingStudy |
| `diagnostic_report` | Diagnostic Reports | DIAG | DiagnosticReport |

Additional types the frontend handles gracefully (with default styling):
- `service_request`, `communication`, `appointment`, `care_plan`

Any unknown `record_type` values render with a neutral gray badge.

---

## Error Response Format

All error responses MUST follow this format:

```json
{
  "detail": "Human-readable error message"
}
```

The frontend reads `response.json().detail` for error display. **Never expose stack traces, internal errors, or PII in error responses.**

**Standard HTTP Status Codes:**
| Code | Usage |
|------|-------|
| 200 | Success |
| 201 | Created (registration) |
| 202 | Accepted (async processing started) |
| 204 | No content (logout, delete) |
| 400 | Validation error |
| 401 | Authentication required or invalid token |
| 403 | Forbidden (accessing another user's data) |
| 404 | Resource not found |
| 409 | Conflict (duplicate email) |
| 413 | File too large |
| 422 | Unprocessable entity |
| 500 | Internal server error |

---

## CORS Requirements

The backend MUST allow CORS from the frontend origin:

```
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, Accept
Access-Control-Allow-Credentials: true
```

---

## Security Requirements

1. **User-scoped data:** Every database query MUST filter by `user_id`. A user must never see another user's records.
2. **JWT validation:** Verify token signature, expiration, and issuer on every authenticated request.
3. **Audit logging:** Log every data access and mutation to the `audit_log` table.
4. **Soft deletes only:** Never hard-delete health records. Use `deleted_at` timestamps.
5. **Dual-mode AI:** Mode 1 builds prompts locally (no API key). Mode 2 calls Gemini API with de-identified data only. All health data passes through the PHI scrubber before any external API call.
6. **API key management:** Gemini API key stored in `.env` only. Never hardcoded in source. No other AI provider keys permitted.
7. **Input validation:** Strict Pydantic validation on all inputs. Sanitize file uploads.
8. **Password hashing:** bcrypt with cost >= 12.

---

## Testing Requirements

For each endpoint, ensure:

1. **Auth guard:** Unauthenticated requests return 401
2. **User isolation:** User A cannot access User B's records
3. **Pagination:** Page boundaries work correctly, total counts are accurate
4. **Filtering:** Record type and search filters return correct subsets
5. **Soft delete:** Deleted records don't appear in list/timeline queries
6. **De-identification:** Summary prompts contain ZERO raw PII (test all 18 HIPAA identifier types)
7. **File upload:** Reject oversized files, invalid MIME types, and malformed content
8. **Error format:** All error responses use `{"detail": "..."}` format
