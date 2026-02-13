# CLAUDE.md — MedTimeline: Personal Health Records Dashboard

## Project Overview

**MedTimeline** is a local-first, HIPAA-compliant personal health records management application that ingests structured medical records (FHIR R4 JSON bundles, Epic EHI Tables exports) into a unified FHIR R4B-compliant database, with future support for unstructured data (clinical notes via LangExtract, scanned documents via AI-enabled OCR). It displays records through a rich interactive timeline and categorized dashboard, and builds AI-ready prompts for health record summarization using Google Gemini 3 Flash.

**AI Architecture — PROMPT-READY, NO API CALLS**: The application constructs fully de-identified, ready-to-send prompts for Gemini 3 Flash but **does NOT make any external API calls**. No API keys are stored, loaded, or used at runtime. The summary endpoints return the constructed prompt (with de-identified health data embedded) so the user can review it, verify no PHI leaked, and execute it themselves outside the app. This is a deliberate security boundary to prevent API key exfiltration during autonomous code generation.

**Critical constraint**: This application provides record organization and AI-ready prompts ONLY. It must NEVER generate diagnoses, treatment suggestions, medical advice, or clinical decision support of any kind. Prompts must instruct the model accordingly, and any future AI output display must include a disclaimer that summaries are for personal reference only and not medical advice.

---

## Current Completion Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Foundation (auth, DB, API shell, frontend shell) | COMPLETE |
| Phase 2 | Structured Data Ingestion (FHIR parser + 5 Epic mappers) | COMPLETE |
| Phase 3 | Record Display & Timeline (via unified Admin Console) | COMPLETE |
| Phase 4 | AI Prompt Builder (prompt-only, no API calls) | COMPLETE |
| Phase 5 | Deduplication (detection + merge/dismiss + pagination) | COMPLETE |
| Phase 6 | Unstructured Data Scaffolding (LangExtract/OCR) | NOT STARTED |
| Phase 7 | Polish & Testing | PARTIAL |

**Testing**: 83 backend tests passing across 8 test files. E2E verified manually via Playwright MCP (Flows A, B, C). No frontend test automation yet.

**Frontend theme**: Retro CRT "Nostromo Earth Terminal" — amber/sage/sienna earth-tone palette, scanline effects, phosphor glow, monospace typography. 13 custom retro components.

**API contract**: All endpoints match the canonical contract in `docs/backend-handoff.md`.

---

## Tech Stack

### Backend
- **Runtime**: Python 3.12+
- **Framework**: FastAPI with Uvicorn
- **Database**: PostgreSQL 16 with pgcrypto extension
- **ORM**: SQLAlchemy 2.x with Alembic migrations
- **FHIR**: `fhir.resources` (v8.x, R4B subpackage) for FHIR model validation and parsing
- **FHIRPath**: `fhirpathpy` for FHIRPath expression evaluation
- **TSV/CSV parsing**: Python `csv` stdlib module for Epic EHI Tables TSV parsing (streaming row-by-row)
- **Streaming JSON**: `ijson` for memory-efficient parsing of large FHIR bundles (>10MB)
- **Auth**: `python-jose` for JWT, `passlib[bcrypt]` for password hashing
- **File processing**: `python-multipart` for uploads
- **AI**: Prompt-only architecture — NO external AI SDK installed, NO API calls made. The app builds de-identified prompts formatted for `gemini-3-flash-preview` and returns them to the user.
- **Validation**: Pydantic v2 throughout
- **Testing**: pytest + pytest-asyncio + httpx (async test client) + factory-boy
- **Background tasks**: `arq` with Redis for async ingestion jobs (fallback: FastAPI BackgroundTasks)

#### Phase 2 Dependencies (Scaffolded Now, Installed Later by User)
- **LangExtract** (`langextract`, Apache 2.0, `google/langextract`) — AI-powered entity extraction for clinical notes. Requires Gemini API key or local Ollama. **NOT installed during autonomous build.** Only the config schemas, few-shot examples, and FHIR mapping layer are built.
- **OCR**: `pytesseract` + Tesseract engine for scanned documents. `PyMuPDF` (fitz) for PDF text extraction. These are autonomous (no API key). Can be installed during build for the text extraction layer, but AI-enhanced post-processing is prompt-only.

### Frontend
- **Framework**: Next.js 15 (App Router) with TypeScript
- **UI Library**: shadcn/ui + Radix primitives + Tailwind CSS 4
- **Custom components**: 13 retro-themed components in `components/retro/` (RetroCard, RetroButton, RetroTable, RetroTabs, RetroInput, RetroNav, RetroBadge, RetroLoadingState, CRTOverlay, GlowText, StatusReadout, TerminalLog, RecordDetailSheet)
- **Charts**: Recharts (installed, available for lab trends)
- **State**: Zustand (installed), TanStack Query v5 (installed, used for API polling)
- **File Upload**: `react-dropzone` (installed)
- **Icons**: `lucide-react`
- **Toasts**: `sonner` via shadcn/ui
- **Themes**: `next-themes`
- **Auth**: NextAuth.js with credentials provider (local JWT validation)
- **Testing**: E2E verified manually via Playwright MCP; no Vitest or automated Playwright specs configured yet

### Infrastructure (Local — No Docker)
- **PostgreSQL 16**: Installed natively via Homebrew (`brew install postgresql@16`). Run as a macOS service.
- **Redis 7**: Installed natively via Homebrew (`brew install redis`). Run as a macOS service.
- **Environment**: macOS (Apple Silicon M4, 16GB RAM) — all services run natively, no containers.
- **Version Control**: Local git repository. Claude Code uses git for atomic commits per feature and can revert on failure.

---

## Project Structure (Actual Built State)

```
medtimeline/
├── CLAUDE.md                          # This file
├── .gitignore
├── docs/
│   └── backend-handoff.md             # Canonical API contract specification
├── scripts/
│   ├── init-db.sql                    # PostgreSQL extensions (pgcrypto, uuid-ossp, pg_trgm)
│   ├── setup-local.sh                 # One-shot: brew install, createdb, extensions, alembic migrate
│   └── pg-tuning.sql                  # PostgreSQL config tuning for large imports
├── .env.example                       # Environment template
├── .claude/
│   └── settings.json                  # Claude Code permissions
│
├── backend/
│   ├── pyproject.toml                 # Python project config (uv/pip)
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/                  # Migration files
│   ├── app/
│   │   ├── main.py                    # FastAPI app factory
│   │   ├── config.py                  # Settings via pydantic-settings
│   │   ├── database.py                # SQLAlchemy engine + session
│   │   ├── dependencies.py            # Dependency injection
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                # JWT middleware
│   │   │   ├── audit.py               # Audit logging middleware
│   │   │   └── encryption.py          # Field-level encryption helpers
│   │   ├── models/                    # SQLAlchemy ORM models (unified health_records table)
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Base model class
│   │   │   ├── user.py                # User model
│   │   │   ├── patient.py             # Patient demographics
│   │   │   ├── record.py              # Unified health_records (all record types)
│   │   │   ├── uploaded_file.py       # Upload tracking + ingestion progress
│   │   │   ├── ai_summary.py          # AI prompt storage
│   │   │   ├── deduplication.py       # Dedup candidates
│   │   │   ├── provenance.py          # Data provenance tracking
│   │   │   └── audit.py               # Audit log
│   │   ├── schemas/                   # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── records.py
│   │   │   ├── timeline.py
│   │   │   ├── summary.py
│   │   │   ├── upload.py
│   │   │   └── dedup.py
│   │   ├── api/                       # API route modules
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # Main API router aggregation
│   │   │   ├── auth.py                # /api/auth/*
│   │   │   ├── records.py             # /api/records/*
│   │   │   ├── timeline.py            # /api/timeline/*
│   │   │   ├── upload.py              # /api/upload/*
│   │   │   ├── summary.py             # /api/summary/*
│   │   │   ├── dedup.py               # /api/dedup/*
│   │   │   └── dashboard.py           # /api/dashboard/*
│   │   ├── services/                  # Business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py        # Auth business logic
│   │   │   ├── ingestion/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── coordinator.py     # Orchestrates ingestion pipeline
│   │   │   │   ├── fhir_parser.py     # FHIR R4 Bundle/Resource parsing
│   │   │   │   ├── epic_parser.py     # Epic EHI Tables TSV directory parsing
│   │   │   │   ├── bulk_inserter.py   # Batched DB insert with commit-per-batch
│   │   │   │   └── epic_mappers/      # One mapper class per Epic table → FHIR resource
│   │   │   │       ├── __init__.py
│   │   │   │       ├── base.py        # Abstract mapper interface
│   │   │   │       ├── problems.py    # PROBLEM_LIST → FHIR Condition
│   │   │   │       ├── results.py     # ORDER_RESULTS → FHIR Observation
│   │   │   │       ├── medications.py # MEDICATIONS → FHIR MedicationRequest
│   │   │   │       ├── encounters.py  # ENCOUNTERS → FHIR Encounter
│   │   │   │       └── documents.py   # DOC_INFORMATION → FHIR DocumentReference
│   │   │   ├── ai/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── prompt_builder.py  # Builds complete prompts for Gemini (NO API calls)
│   │   │   │   └── phi_scrubber.py    # PHI de-identification (18 HIPAA identifiers)
│   │   │   ├── dedup/
│   │   │   │   ├── __init__.py
│   │   │   │   └── detector.py        # Duplicate detection (fuzzy + exact matching)
│   │   │   ├── timeline_service.py    # Timeline data aggregation
│   │   │   ├── dashboard_service.py   # Dashboard metrics & aggregation
│   │   │   └── encryption_service.py  # AES-256 field-level encryption
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── coding.py              # LOINC, SNOMED, ICD-10 code lookups
│   │       ├── date_utils.py          # Date/time normalization
│   │       └── file_utils.py          # File type detection, temp storage
│   └── tests/                         # 83 tests, flat structure
│       ├── __init__.py
│       ├── conftest.py                # Fixtures, test DB, auth_headers(), create_test_patient(), seed_test_records()
│       ├── test_auth.py               # Auth endpoint tests
│       ├── test_records.py            # Records CRUD tests
│       ├── test_dashboard.py          # Dashboard overview + labs tests
│       ├── test_timeline.py           # Timeline + stats tests
│       ├── test_upload.py             # Upload + ingestion status tests
│       ├── test_summary.py            # Prompt build + paste-response tests
│       ├── test_dedup.py              # Dedup candidates + merge/dismiss tests
│       ├── test_ingestion.py          # FHIR parser + Epic mapper unit tests
│       └── fixtures/                  # Test data
│           ├── README.md
│           ├── sample_fhir_bundle.json      # Synthetic FHIR bundle
│           └── sample_epic_tsv/             # Synthetic Epic TSV
│               ├── PATIENT.tsv
│               ├── PROBLEM_LIST.tsv
│               ├── ORDER_RESULTS.tsv
│               ├── MEDICATIONS.tsv
│               ├── ALLERGIES.tsv
│               └── ENCOUNTERS.tsv
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx             # Root layout (Berkeley Mono + Space Mono + VT323 fonts)
│   │   │   ├── globals.css            # Retro earth-tone palette + CRT effects
│   │   │   ├── page.tsx               # Landing / login redirect
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx     # Retro-styled login
│   │   │   │   └── register/page.tsx  # Retro-styled registration
│   │   │   └── (dashboard)/
│   │   │       ├── layout.tsx         # Dashboard shell (RetroNav sidebar)
│   │   │       ├── page.tsx           # Home dashboard (stats, recent activity)
│   │   │       ├── timeline/page.tsx  # Full timeline view (retro-styled)
│   │   │       ├── summaries/page.tsx # AI summaries hub (prompt build + paste-back)
│   │   │       ├── admin/page.tsx     # Unified Admin Console (1012 lines, 12 tabs)
│   │   │       ├── records/
│   │   │       │   ├── page.tsx       # Redirects to admin?tab=all
│   │   │       │   └── [id]/page.tsx  # Single record detail (retro-styled)
│   │   │       ├── labs/page.tsx           # → admin?tab=labs
│   │   │       ├── medications/page.tsx    # → admin?tab=medications
│   │   │       ├── conditions/page.tsx     # → admin?tab=conditions
│   │   │       ├── encounters/page.tsx     # → admin?tab=encounters
│   │   │       ├── immunizations/page.tsx  # → admin?tab=immunizations
│   │   │       ├── imaging/page.tsx        # → admin?tab=imaging
│   │   │       ├── upload/page.tsx         # → admin?tab=upload
│   │   │       ├── dedup/page.tsx          # → admin?tab=dedup
│   │   │       └── settings/page.tsx       # → admin?tab=settings
│   │   ├── components/
│   │   │   ├── ui/                    # shadcn/ui components
│   │   │   │   ├── button.tsx
│   │   │   │   ├── card.tsx
│   │   │   │   ├── input.tsx
│   │   │   │   ├── label.tsx
│   │   │   │   ├── dialog.tsx
│   │   │   │   ├── sheet.tsx
│   │   │   │   ├── table.tsx
│   │   │   │   ├── badge.tsx
│   │   │   │   ├── tabs.tsx
│   │   │   │   ├── separator.tsx
│   │   │   │   ├── dropdown-menu.tsx
│   │   │   │   ├── sonner.tsx
│   │   │   │   ├── alert.tsx
│   │   │   │   ├── avatar.tsx
│   │   │   │   └── scroll-area.tsx
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx        # Legacy sidebar (superseded by RetroNav)
│   │   │   │   └── Header.tsx         # Legacy header
│   │   │   ├── retro/                 # Custom retro CRT component library
│   │   │   │   ├── CRTOverlay.tsx     # Scanline + vignette overlay
│   │   │   │   ├── GlowText.tsx       # Phosphor glow text effects
│   │   │   │   ├── RetroCard.tsx      # Bordered card with glow
│   │   │   │   ├── RetroButton.tsx    # Earth-tone buttons with hover glow
│   │   │   │   ├── RetroTable.tsx     # Styled data table
│   │   │   │   ├── RetroTabs.tsx      # Tab navigation
│   │   │   │   ├── RetroInput.tsx     # Form inputs
│   │   │   │   ├── RetroNav.tsx       # Sidebar navigation
│   │   │   │   ├── RetroBadge.tsx     # Status badges
│   │   │   │   ├── RetroLoadingState.tsx  # Loading spinner/skeleton
│   │   │   │   ├── StatusReadout.tsx  # Key-value status display
│   │   │   │   ├── TerminalLog.tsx    # Terminal-style log output
│   │   │   │   └── RecordDetailSheet.tsx  # Slide-over record detail
│   │   │   └── Providers.tsx          # TanStack Query + theme providers
│   │   └── lib/
│   │       ├── api.ts                 # API client (fetch wrapper)
│   │       ├── utils.ts               # Shared utilities (cn)
│   │       └── constants.ts           # API URL, app name
│   └── (no automated test files yet)
│
└── scripts/
    ├── seed_sample_data.py            # Seeds DB with FHIR Synthea data
    ├── generate_test_fixtures.py      # Generates test fixture files
    └── reset_db.sh                    # Drops and recreates DB
```

**Note on planned but not-yet-built files** (Phase 6 future work):
- `services/ingestion/langextract_scaffold.py`, `langextract_config/`, `ocr_scaffold.py`, `response_parser.py`
- `services/ai/extractor.py`, `services/ai/prompts.py`, `services/ai/summarizer.py`
- `services/dedup/merger.py`, `services/dedup/scoring.py`
- `services/ingestion/epic_mappers/patient.py`, `allergies.py`, `immunizations.py`, `procedures.py`
- Frontend: `hooks/`, `stores/`, `types/` directories (inline types used instead)

---

## Database Schema Design

Use FHIR R4B as the canonical data model. All ingested records regardless of source format are normalized into these FHIR-aligned tables. Use PostgreSQL with `pgcrypto` for encryption-at-rest on PII fields.

### Core Tables

```sql
-- All PII fields (name, DOB, SSN, MRN) encrypted at rest with AES-256 via pgcrypto
-- All tables include: id (UUID PK), created_at, updated_at, deleted_at (soft delete)

users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,           -- encrypted
    password_hash TEXT NOT NULL,
    display_name TEXT,                     -- encrypted
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
)

patients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),    -- owner
    fhir_id TEXT,                          -- FHIR Patient resource ID
    mrn_encrypted BYTEA,                  -- encrypted MRN
    name_encrypted BYTEA,                 -- encrypted full name
    birth_date_encrypted BYTEA,           -- encrypted DOB
    gender TEXT,
    contact_info_encrypted BYTEA,         -- encrypted JSON
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
)

-- Base record: all clinical data inherits from this
health_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES patients(id) NOT NULL,
    user_id UUID REFERENCES users(id) NOT NULL,
    record_type TEXT NOT NULL,             -- 'condition', 'observation', 'medication', etc.
    fhir_resource_type TEXT NOT NULL,      -- FHIR resource type string
    fhir_resource JSONB NOT NULL,          -- Full FHIR R4B resource as JSON
    source_format TEXT NOT NULL,           -- Phase 1: 'fhir_r4', 'epic_ehi'. Future: 'ccda', 'pdf', 'raw_text', 'langextract'
    source_file_id UUID,                  -- reference to uploaded file
    effective_date TIMESTAMPTZ,           -- primary date for timeline ordering
    effective_date_end TIMESTAMPTZ,       -- for date ranges
    status TEXT,                          -- FHIR resource status
    category TEXT[],                      -- FHIR category codes
    code_system TEXT,                     -- e.g., 'http://loinc.org'
    code_value TEXT,                      -- e.g., LOINC code
    code_display TEXT,                    -- Human-readable code display
    display_text TEXT NOT NULL,           -- Human-readable summary for UI
    is_duplicate BOOLEAN DEFAULT false,
    merged_into_id UUID REFERENCES health_records(id),
    confidence_score FLOAT,              -- AI extraction confidence (0-1)
    ai_extracted BOOLEAN DEFAULT false,  -- whether AI was used to extract
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ               -- soft delete
)

-- Indexes for performance
CREATE INDEX idx_health_records_patient_date ON health_records(patient_id, effective_date DESC);
CREATE INDEX idx_health_records_type ON health_records(record_type);
CREATE INDEX idx_health_records_code ON health_records(code_system, code_value);
CREATE INDEX idx_health_records_fhir_resource ON health_records USING GIN (fhir_resource);

uploaded_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size_bytes BIGINT,
    file_hash TEXT NOT NULL,               -- SHA-256 for dedup
    storage_path TEXT NOT NULL,            -- encrypted file path
    -- Ingestion tracking (designed for large multi-file imports)
    ingestion_status TEXT DEFAULT 'pending', -- pending, processing, completed, failed, partial
    ingestion_progress JSONB DEFAULT '{}',  -- {"current_file": "MEDICATIONS.tsv", "file_index": 12, "total_files": 47, "records_ingested": 8400, "records_failed": 3}
    ingestion_errors JSONB DEFAULT '[]',    -- [{file: "ORDER_PROC.tsv", row: 445, error: "invalid date format"}, ...]
    record_count INTEGER DEFAULT 0,        -- total records successfully extracted
    total_file_count INTEGER DEFAULT 1,    -- for directories/ZIPs: number of sub-files
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
)

-- Stores constructed prompts (NOT AI responses — no API calls are made)
ai_summary_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) NOT NULL,
    patient_id UUID REFERENCES patients(id) NOT NULL,
    summary_type TEXT NOT NULL,            -- 'full', 'category', 'date_range', 'single_record'
    scope_filter JSONB,                   -- filter criteria used to select records
    system_prompt TEXT NOT NULL,           -- system instruction for the model
    user_prompt TEXT NOT NULL,             -- de-identified health data + instructions
    target_model TEXT NOT NULL DEFAULT 'gemini-3-flash-preview',
    suggested_config JSONB NOT NULL,      -- {temperature, max_output_tokens, thinking_level}
    record_count INTEGER NOT NULL,        -- how many records were included
    de_identification_log JSONB,          -- what PHI was scrubbed (types, not values)
    -- User can optionally paste back the AI response for storage
    response_text TEXT,                   -- manually pasted AI response (optional)
    response_pasted_at TIMESTAMPTZ,
    generated_at TIMESTAMPTZ DEFAULT now()
)

dedup_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_a_id UUID REFERENCES health_records(id) NOT NULL,
    record_b_id UUID REFERENCES health_records(id) NOT NULL,
    similarity_score FLOAT NOT NULL,       -- 0-1
    match_reasons JSONB NOT NULL,          -- which fields matched
    status TEXT DEFAULT 'pending',         -- pending, merged, dismissed
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
)

provenance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id UUID REFERENCES health_records(id) NOT NULL,
    action TEXT NOT NULL,                  -- 'created', 'merged', 'updated', 'ai_extracted'
    source_file_id UUID REFERENCES uploaded_files(id),
    agent TEXT NOT NULL,                   -- 'system', 'user', 'prompt_builder'
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
)

audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id UUID,
    ip_address TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
)
```

---

## HIPAA Compliance Requirements

### Mandatory Controls — Implement ALL of These

1. **Encryption at rest**: All PII fields use AES-256 encryption via `pgcrypto`. File uploads encrypted on disk.
2. **Encryption in transit**: TLS 1.3 required for all API communication. In local dev, use self-signed certs with Caddy.
3. **Authentication**: bcrypt password hashing (min cost 12). JWT access tokens (15 min expiry) + refresh tokens (7 day expiry, rotated on use).
4. **Authorization**: Row-level security — users can ONLY access their own records. Enforce in every query, not just API layer.
5. **Audit logging**: Every data access, modification, and deletion logged to `audit_log` table with timestamp, user, action, resource.
6. **Session management**: Automatic session timeout (30 min idle). Token revocation on logout.
7. **Data minimization**: Only store data necessary for functionality. AI prompts never include raw PII — all prompts are built from de-identified data. No API keys are stored or used.
8. **Soft deletes**: Never hard-delete health records. Use `deleted_at` timestamps.
9. **Input validation**: Strict Pydantic validation on all inputs. Sanitize file uploads. Limit file sizes (500MB per individual file, 5GB per Epic export ZIP/directory).
10. **Error handling**: Never expose internal errors, stack traces, or PII in error responses. Log errors server-side with full context.

### AI-Specific HIPAA Protections

- **No external API calls**: The application NEVER calls any external AI API. It constructs prompts and returns them to the user. This eliminates the risk of PHI transmission to third parties.
- **No API keys in codebase**: No API keys, tokens, or credentials for AI services are stored, loaded, or referenced anywhere in the application code or environment variables.
- **De-identify before prompt construction**: Strip names, DOBs, MRNs, addresses, phone numbers, SSNs, and all 18 HIPAA identifiers from text before embedding in any prompt. Use the dedicated `phi_scrubber.py` service.
- **Use a configurable PHI scrubber** in `services/ai/phi_scrubber.py` that processes text through regex + entity detection. The scrubber produces a de-identification log (what types of PHI were found and scrubbed, NOT the values) stored with each prompt.
- **Prompt review before execution**: The UI displays the full constructed prompt to the user so they can verify no PHI leaked before copying it to an external tool.
- **Optional response paste-back**: The UI allows users to paste an AI response back into the app for storage, but this is entirely optional and user-initiated.

---

## AI Integration: Prompt-Only Architecture (No API Calls)

### Security Rationale

This application builds prompts but **never executes them**. No AI SDK is installed. No API keys exist in the codebase or environment. This is a deliberate security boundary:
- Prevents API key exfiltration during autonomous code generation
- Gives the user full control over what data leaves their machine
- Allows prompt inspection before any external transmission
- Eliminates dependency on third-party API availability

### How It Works

1. User requests a summary (selects records, date range, or category)
2. Backend fetches relevant health records from the database
3. PHI scrubber (`services/ai/phi_scrubber.py`) de-identifies all text
4. Prompt builder (`services/ai/prompt_builder.py`) constructs a complete prompt:
   - System instruction (role, constraints, no-diagnosis rule)
   - De-identified health data formatted for the model
   - Output format instructions
5. API returns the full prompt package as JSON:

```json
{
  "id": "uuid",
  "summary_type": "full",
  "system_prompt": "You are a medical records summarizer. Summarize ONLY factual information...",
  "user_prompt": "The following de-identified health records span 2019-2024...\n\n[de-identified data]",
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
  "copyable_payload": "... single string ready to paste into Google AI Studio or API ..."
}
```

6. User reviews the prompt in the UI, copies it, and runs it themselves (Google AI Studio, Gemini API, etc.)
7. Optionally, user pastes the AI response back into the app for storage alongside the prompt

### Prompt Templates (centralized in `services/ai/prompts.py`)

All prompts MUST:
- Explicitly instruct: "Do NOT provide any diagnoses, treatment recommendations, medical advice, or clinical decision support."
- Instruct: "Summarize the factual medical information only."
- Instruct: "If information is unclear or potentially conflicting, note this without interpretation."
- Include output format instructions (structured markdown with sections by category/date)
- Be version-controlled and testable

### Summary Types

1. **Full health summary**: Chronological overview of all records for a patient
2. **Category summary**: Focused summary on one category (labs, medications, conditions, etc.)
3. **Date range summary**: Summary for a specific time period
4. **Single record summary**: Enhanced summary of one complex record (e.g., long clinical note)

### PHI Scrubber (`services/ai/phi_scrubber.py`)

The scrubber is a critical component. It MUST remove all 18 HIPAA identifiers:
1. Names → replaced with `[PATIENT]`, `[PROVIDER]`, `[CONTACT]`
2. Geographic data (below state) → `[LOCATION]`
3. Dates (except year) → generalized to month/year or `[DATE]`
4. Phone numbers → `[PHONE]`
5. Fax numbers → `[FAX]`
6. Email → `[EMAIL]`
7. SSN → `[SSN]`
8. MRN → `[MRN]`
9. Health plan numbers → `[PLAN_ID]`
10. Account numbers → `[ACCOUNT]`
11. Certificate/license numbers → `[LICENSE]`
12. Vehicle IDs → `[VEHICLE]`
13. Device IDs → `[DEVICE]`
14. URLs → `[URL]`
15. IP addresses → `[IP]`
16. Biometric IDs → `[BIOMETRIC]`
17. Full-face photos → (not applicable to text, but flag if embedded)
18. Any other unique identifier → `[IDENTIFIER]`

Implementation approach:
- **Regex patterns** for structured identifiers (SSN, phone, email, MRN patterns)
- **Named entity recognition** using the patient's known name, DOB, and address from the `patients` table for targeted scrubbing
- **Date generalization**: Convert specific dates to month/year unless clinically meaningful (preserve relative timing like "3 days post-op")
- **Confidence logging**: Track what was scrubbed and why, stored in `de_identification_log`

### AI-Assisted Extraction — LangExtract (Phase 2, Not Autonomous)

For unstructured documents (clinical notes, scanned records), the app will use **LangExtract** (`google/langextract`, Apache 2.0) — a Python library that uses LLMs for structured entity extraction with precise source grounding. LangExtract is ideal because it:
- Maps every extracted entity to exact character offsets in source text (traceability)
- Uses few-shot examples to define extraction schemas (no fine-tuning needed)
- Supports clinical/medical extraction out of the box (medications, dosages, conditions)
- Works with Gemini (cloud, requires API key) or local models via Ollama (no API key)

**However, LangExtract requires an API key for cloud models and is therefore NOT installed or executed during autonomous build.** The scaffolding built in Phase 6 includes:
- Extraction schema definitions (few-shot examples for clinical entities)
- FHIR R4B mapping layer for LangExtract output → FHIR resources
- Response parser for ingesting structured extraction results
- Config files that would be passed to `lx.extract()` when the user runs it themselves

The two-step user-involved process for unstructured ingestion:
1. Upload document → app extracts raw text (PyMuPDF/Tesseract, autonomous) → app builds LangExtract config or summary prompt → user executes LangExtract or Gemini externally
2. User pastes structured response → app parses response → app creates FHIR resources marked with `ai_extracted = true`

---

## Ingestion Pipeline Architecture

### Phased Approach

**Phase 1 (Build Now):** Structured data only — FHIR R4 JSON bundles and Epic EHI Tables exports (TSV). These are fully parseable without AI.

**Phase 2 (Future — Not Autonomous):** Unstructured data — clinical notes, handwritten scans, raw text. Will use:
- **LangExtract** (`google/langextract`, Apache 2.0) for AI-powered entity extraction from clinical notes. LangExtract uses LLMs (Gemini via API key or local models via Ollama) with precise source grounding and few-shot examples. Since it requires an API key for cloud models, it is NOT built autonomously — only the integration scaffolding, prompt examples, and FHIR mapping layer are built. Actual LangExtract execution is user-initiated.
- **AI-enabled OCR** for scanned documents. Text extraction via PyMuPDF/Tesseract is built autonomously. AI-enhanced OCR correction and entity extraction from scanned text follows the same prompt-only pattern — not autonomous.

### Phase 1 Flow (Structured Data — Fully Autonomous)

```
File Upload → Type Detection → Format Validation → Parser Selection → FHIR R4B Normalization → DB Storage → Dedup Check → Index
```

Supported formats in Phase 1:
1. **FHIR R4 JSON Bundles**: Direct parsing via `fhir.resources` R4B. Validate resource types, extract individual resources from bundles, store normalized.
2. **Epic EHI Tables Export (TSV directory)**: Parse the directory of TSV files per Epic's EHI Tables specification. Map Epic table schemas to FHIR R4B resources. Handle the multi-file structure (each table is a separate TSV with a defined schema from `open.epic.com/EHITables`).

### Phase 1 Parser Details

#### FHIR R4 JSON Parser (`services/ingestion/fhir_parser.py`)
- Accept single FHIR resources or Bundle resources
- Validate each resource against `fhir.resources` R4B models
- Extract from Bundle: iterate `entry` array, validate each `resource`
- Map supported resource types to internal `health_records` table:
  - `Patient` → `patients` table
  - `Condition` → record_type='condition'
  - `Observation` → record_type='observation' (labs, vitals)
  - `MedicationRequest` / `MedicationStatement` → record_type='medication'
  - `AllergyIntolerance` → record_type='allergy'
  - `Procedure` → record_type='procedure'
  - `Encounter` → record_type='encounter'
  - `Immunization` → record_type='immunization'
  - `DiagnosticReport` → record_type='diagnostic_report'
  - `DocumentReference` → record_type='document'
  - `ImagingStudy` → record_type='imaging'
- Preserve the full FHIR resource as JSONB in `fhir_resource` column
- Extract `effectiveDateTime`, `issued`, `date`, `period.start` etc. for timeline ordering
- Extract coding info (system + code + display) for categorization

#### Epic EHI Tables Parser (`services/ingestion/epic_parser.py`)

Epic EHI exports can be **very large** — hundreds of TSV files, some with hundreds of thousands of rows, potentially multiple gigabytes total. The parser MUST be designed for memory efficiency on a 16GB MacBook Air.

**Architecture: streaming row-by-row, file-by-file**

```python
# CORRECT: Stream each TSV file row-by-row
import csv
from pathlib import Path

async def parse_epic_export(export_dir: Path, user_id: UUID, patient_id: UUID, db: AsyncSession):
    """Process Epic EHI export directory. Files are processed one at a time, rows streamed."""
    tsv_files = sorted(export_dir.glob("*.tsv"))  # could be 100+ files
    
    for tsv_path in tsv_files:
        table_name = tsv_path.stem.upper()
        mapper = EPIC_TABLE_MAPPERS.get(table_name)
        if not mapper:
            log.info(f"Skipping unmapped Epic table: {table_name}")
            continue
        
        batch = []
        row_count = 0
        with open(tsv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                fhir_resource = mapper.to_fhir(row)  # map single row → FHIR resource
                if fhir_resource:
                    batch.append(fhir_resource)
                    row_count += 1
                
                if len(batch) >= BATCH_SIZE:  # flush every 100 records
                    await bulk_insert_records(db, batch, user_id, patient_id, source="epic_ehi")
                    batch.clear()
                    await db.commit()  # commit per batch to avoid long transactions
            
            if batch:  # flush remainder
                await bulk_insert_records(db, batch, user_id, patient_id, source="epic_ehi")
                await db.commit()
        
        log.info(f"Processed {table_name}: {row_count} rows")

# WRONG: Never do this
# data = tsv_path.read_text()  # loads entire file into memory
# rows = list(csv.DictReader(...))  # materializes all rows at once
```

**Critical design rules for Epic parser:**
- **NEVER read an entire TSV file into memory.** Always use `csv.DictReader` as an iterator.
- **NEVER collect all rows into a list.** Process row-by-row, flush to DB in batches.
- **NEVER load all files simultaneously.** Process one file at a time, sequentially.
- **Batch DB inserts**: Flush to database every 100 records using `executemany` / bulk insert. Commit per batch to keep transaction size small and release memory.
- **Track progress per file**: Update `uploaded_files.ingestion_progress` with file-level progress (e.g., "Processing MEDICATIONS.tsv (3/47 files, 12,400 rows)").
- **Handle encoding**: Epic TSVs may use `utf-8-sig` (BOM) encoding. Always specify `encoding="utf-8-sig"`.
- **Handle malformed rows gracefully**: Log and skip rows that fail parsing. Never abort the entire import for one bad row. Store errors in `uploaded_files.ingestion_errors` JSONB field.
- **ZIP support**: If user uploads a ZIP, extract to a temp directory, process, then clean up. Use `zipfile` with streaming extraction — never extract entire ZIP to memory.

**Table mapper architecture:**
- Each supported Epic table gets a dedicated mapper class in `services/ingestion/epic_mappers/`
- Mapper classes implement a common interface: `to_fhir(row: dict) -> Optional[FHIRResource]`
- Mapper handles column name mapping, date parsing, code lookups, cross-table ID resolution
- Unmapped tables are logged but not fatal

**Cross-table ID resolution:**
- Epic tables reference each other via internal IDs (e.g., `PAT_ID`, `ORDER_ID`, `PAT_ENC_CSN_ID`)
- Build an in-memory ID lookup index during Patient table parsing (patient IDs are small)
- For larger cross-references (orders → results), use a lightweight temp index or DB-side joins after insert
- Do NOT build a full in-memory graph of all table relationships — that will OOM on large exports

**Map key Epic tables to FHIR resources:**
- `PATIENT` → FHIR Patient
- `PROBLEM_LIST` / `MEDICAL_HX` → FHIR Condition
- `ORDER_RESULTS` / `ORDER_RESULT_COMPONENTS` → FHIR Observation
- `MEDICATIONS` / `ORDER_MED` → FHIR MedicationRequest
- `ALLERGIES` → FHIR AllergyIntolerance
- `IMMUNIZATIONS` → FHIR Immunization
- `ENCOUNTERS` / `PAT_ENC` → FHIR Encounter
- `PROCEDURES` / `ORDER_PROC` → FHIR Procedure
- `DOC_INFORMATION` → FHIR DocumentReference
- Handle Epic-specific date formats, ID formats, and coded values
- Normalize all output into FHIR R4B resources before storage
- Log unmapped tables/fields for future coverage

#### FHIR R4 JSON Parser — Large Bundle Handling (`services/ingestion/fhir_parser.py`)

FHIR bundles can also be large (10k+ entries). Use streaming JSON parsing:
- For files > 10MB: use `ijson` (streaming JSON parser) to iterate over `entry` array items without loading the full bundle into memory
- For files ≤ 10MB: standard `json.loads()` is fine
- Batch DB inserts: same 100-record batch pattern as Epic parser
- Track progress: update ingestion status with entry count progress

### Phase 2 Scaffolding (Build Interfaces, Not Execution)

Build these interfaces and scaffolding NOW so Phase 2 integration is clean, but do NOT make any external API calls:

#### LangExtract Integration Scaffold (`services/ingestion/langextract_scaffold.py`)
- Define the extraction schema (few-shot examples) for clinical note entity extraction:
  - Medications (name, dosage, route, frequency)
  - Conditions/diagnoses (name, date, status)
  - Procedures (name, date, body site)
  - Lab values (test name, value, units, reference range, date)
  - Vitals (type, value, date)
  - Providers (name, specialty, role)
- Define the FHIR R4B mapping for each extracted entity type
- Build the prompt/example configuration that would be passed to `lx.extract()`
- Store config as JSON fixtures in `backend/app/services/ingestion/langextract_config/`
- **Do NOT install `langextract` or any AI SDK. Do NOT call `lx.extract()`.** Only build the config, mapping layer, and response parser.

#### OCR + Scan Processing Scaffold (`services/ingestion/ocr_scaffold.py`)
- Build the text extraction pipeline: PyMuPDF for digital PDFs, Tesseract for image-based OCR
- Text extraction itself IS autonomous (no API key needed)
- For AI-enhanced post-processing (correcting OCR errors, extracting entities from OCR text): build the prompt templates only, following the prompt-only pattern from Phase 4
- Define the expected structured output format for OCR extraction results

### Test Fixtures — User-Provided Real Files

The user will provide:
1. **A test FHIR R4 JSON file** (or bundle) — place in `backend/tests/fixtures/user_provided_fhir.json`
2. **A test Epic EHI Tables export directory** — place in `backend/tests/fixtures/epic_export/`

**The Epic export may be very large (hundreds of files, gigabytes total).** Test strategy must handle this:

#### Test Fixture Sampling for Large Exports
```python
# In conftest.py — create a sampled subset for fast tests
import csv, os, shutil
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLED_DIR = FIXTURES_DIR / "epic_export_sampled"
MAX_ROWS_PER_TABLE = 50  # enough to test parsing without slow tests

@pytest.fixture(scope="session", autouse=True)
def prepare_sampled_epic_fixtures():
    """One-time: create a sampled subset of large Epic export for fast test runs."""
    source = FIXTURES_DIR / "epic_export"
    if not source.exists():
        return  # fall back to synthetic
    
    if SAMPLED_DIR.exists():
        return  # already sampled
    
    SAMPLED_DIR.mkdir(parents=True)
    for tsv_path in sorted(source.glob("*.tsv")):
        with open(tsv_path, "r", encoding="utf-8-sig") as src:
            reader = csv.reader(src, delimiter="\t")
            header = next(reader)
            rows = []
            for i, row in enumerate(reader):
                if i >= MAX_ROWS_PER_TABLE:
                    break
                rows.append(row)
        
        with open(SAMPLED_DIR / tsv_path.name, "w", encoding="utf-8") as dst:
            writer = csv.writer(dst, delimiter="\t")
            writer.writerow(header)
            writer.writerows(rows)
    
    yield
    # Don't clean up — reuse across test runs

@pytest.fixture
def epic_export_dir():
    """Use sampled dir for unit tests, full dir for integration tests."""
    sampled = FIXTURES_DIR / "epic_export_sampled"
    full = FIXTURES_DIR / "epic_export"
    synthetic = FIXTURES_DIR / "sample_epic_tsv"
    if sampled.exists():
        return sampled
    elif full.exists():
        return full
    return synthetic
```

#### Test tiers for large data:
1. **Unit tests (fast, always run)**: Use sampled fixtures (50 rows per table). Test column mapping, date parsing, FHIR conversion for every mapper. Should complete in seconds.
2. **Integration tests (`@pytest.mark.integration`)**: Use sampled fixtures. Test full pipeline: upload → parse → DB insert → query back. Verify batch commit behavior.
3. **Full import tests (`@pytest.mark.slow`)**: Use complete user-provided export. Test that the entire import completes without OOM or errors. Measure memory usage. Measure time. These are opt-in: `pytest -m slow`.
4. **Memory safety tests (`@pytest.mark.slow`)**: Import a large file and assert that Python RSS stays under 2GB. Use `tracemalloc` to catch memory leaks in the streaming pipeline.

```python
@pytest.mark.slow
async def test_full_epic_import_memory_safe(epic_export_dir_full):
    """Verify full Epic import stays under memory budget."""
    import tracemalloc
    tracemalloc.start()
    
    await parse_epic_export(epic_export_dir_full, ...)
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 2 * 1024 * 1024 * 1024, f"Peak memory {peak / 1e9:.1f}GB exceeds 2GB limit"
```

**Build all parsers and tests against these real files.** Do not generate synthetic test data as the primary test target. Instead:
- Copy user-provided files into `backend/tests/fixtures/`
- Write parser tests that run against the actual structure of these files
- Extract the resource types, table names, and field patterns present in the real data
- If the real files contain PII, the test suite should work with them locally but never commit them to git — add `backend/tests/fixtures/user_provided_*` and `backend/tests/fixtures/epic_export/` to `.gitignore`
- Additionally, create minimal synthetic fixtures (`sample_fhir_bundle.json`, `sample_epic_tsv/`) for CI/CD that mirror the structure of the real files but contain fake data

### `.gitignore` Additions
```
# User-provided test data (may contain real PHI)
backend/tests/fixtures/user_provided_*
backend/tests/fixtures/epic_export/
backend/tests/fixtures/epic_export_sampled/

# Temp and upload data
*.env
data/uploads/
data/tmp/
```

---

## Deduplication System

### Detection Strategies

1. **Exact match**: Same FHIR resource type + code + effective date + value
2. **Fuzzy match**: Levenshtein distance on display text, date proximity (within 24h), code similarity
3. **File-level dedup**: SHA-256 hash of uploaded files to prevent re-ingestion
4. **Cross-source dedup**: Same clinical event imported from multiple sources (e.g., FHIR + Epic export)

### User Flow

1. System automatically detects potential duplicates and stores in `dedup_candidates`
2. User views candidates in side-by-side comparison UI
3. User chooses: **Merge** (pick primary, archive secondary), **Dismiss** (not duplicates), or **Flag** (unsure)
4. All merge actions create provenance records

---

## Frontend Design System: "Nostromo Earth Terminal"

### Visual Language
The frontend uses a retro CRT terminal aesthetic inspired by 1970s-80s space program consoles. All pages share this unified visual identity.

- **Color palette**: Dark earth tones with phosphor accents
  - Background: deep brown-black (`#0d0b08`), dark earth (`#1a1612`)
  - Primary text: warm amber (`#e09040`)
  - Secondary text: dusty gold (`#b8956a`)
  - Success/active: sage green (`#7a8c5a`)
  - Warning/alert: terracotta (`#c45a3c`)
  - Accent: ochre (`#d4a843`)
  - Borders: sienna (`#a0522d`)
  - Categories: Each record type has a distinct warm color (labs=sage, meds=amber, conditions=ochre, encounters=sienna, imaging=dusty rose, immunizations=olive)
- **Typography**: Monospace-first
  - Display/headings: Berkeley Mono (Google Fonts fallback: Space Mono)
  - Body text: Space Mono
  - Terminal output/data: VT323
- **Effects** (via CSS, defined in `globals.css`):
  - CRT scanline overlay (semi-transparent horizontal lines via `CRTOverlay.tsx`)
  - Phosphor glow on interactive elements (text-shadow with amber/green glow)
  - Vignette corner darkening (radial gradient overlay)
  - Noise texture backgrounds (CSS `filter` grain)
- **Layout**: Sidebar navigation (RetroNav) + main content area. Desktop-optimized (1024px+).
- **Motion**: Minimal — subtle glow pulses on hover, no transition delays.

### Custom Retro Components (`components/retro/`)
13 components that implement the design system:
1. **CRTOverlay** — Scanline + vignette overlay applied to the entire viewport
2. **GlowText** — Text with configurable phosphor glow color (amber, green, red)
3. **RetroCard** — Bordered card with sienna border and optional glow header
4. **RetroButton** — Earth-tone buttons with hover phosphor glow
5. **RetroTable** — Styled data table with amber headers and alternating rows
6. **RetroTabs** — Tab navigation bar with glowing active indicator
7. **RetroInput** — Form inputs with CRT-style focus glow
8. **RetroNav** — Sidebar navigation with icon + label items
9. **RetroBadge** — Colored status badges for record types
10. **RetroLoadingState** — Terminal-style loading animation
11. **StatusReadout** — Key-value pair display (like a cockpit readout)
12. **TerminalLog** — Scrollable terminal-style log output
13. **RecordDetailSheet** — Slide-over panel for record detail view

### Page Architecture
- **Home** (`/`) — Dashboard with stats cards, recent activity, quick actions
- **Timeline** (`/timeline`) — Vertical timeline of all records, filterable by type/date
- **Summaries** (`/summaries`) — AI prompt builder + prompt review + response paste-back
- **Admin Console** (`/admin`) — Unified 12-tab interface consolidating all category views:
  - HOME, ALL, LABS, MEDS, COND, ENC, IMM, IMG, UPLOAD, DEDUP, SUMM, SET
  - Each tab is a self-contained view with its own data fetching and UI
  - Category pages (`/labs`, `/medications`, etc.) redirect to the corresponding admin tab
- **Record Detail** (`/records/[id]`) — Full record view with FHIR resource JSON display

### Large Import UX (Epic EHI Exports)

Epic exports can take minutes to process. The frontend MUST handle this gracefully:

**Upload flow:**
1. User drags/drops ZIP or selects directory → UploadZone shows file count and total size
2. File transfer begins → UploadProgress shows transfer % (this is the network upload to backend)
3. Transfer completes → backend returns `upload_id` + `202 Accepted` immediately
4. Frontend switches to EpicImportProgress → polls `GET /api/v1/upload/:id/status` every 2 seconds

**EpicImportProgress component displays:**
```
┌─ Importing Epic Health Records ──────────────────────────────┐
│                                                               │
│  Status: Processing                                           │
│  ████████████░░░░░░░░ 47%                                     │
│                                                               │
│  Current file: MEDICATIONS.tsv (12 of 47 files)              │
│  Records ingested: 8,400                                      │
│  Errors: 3 (view details)                                     │
│  Elapsed: 2m 14s                                              │
│                                                               │
│  [Cancel Import]                                              │
└───────────────────────────────────────────────────────────────┘
```

**Design rules:**
- **Never block the UI.** User can navigate away and come back. Progress persists in the backend.
- **Poll, don't websocket.** Simple polling at 2-second intervals via TanStack Query's `refetchInterval`. No websocket complexity needed for this use case.
- **Show partial results.** Once the first batch of records is committed, they should appear in the timeline/records views even while the import is still running.
- **Surface errors without alarming.** Individual row failures are expected (malformed dates, unknown codes). Show error count with a "view details" link. Only show error toast if the entire import fails.
- **Cancel support.** Canceling a large import sets a flag in Redis that the ingestion worker checks between batches. Already-committed records remain in the database.

**TanStack Query polling pattern:**
```typescript
const { data: importStatus } = useQuery({
  queryKey: ['upload-status', uploadId],
  queryFn: () => api.get(`/upload/${uploadId}/status`),
  refetchInterval: (query) => {
    const status = query.state.data?.ingestion_status;
    // Stop polling when done or failed
    if (status === 'completed' || status === 'failed') return false;
    return 2000; // poll every 2s while processing
  },
  enabled: !!uploadId,
});
```

---

## API Design

> **Canonical contract**: See `docs/backend-handoff.md` for the full API specification with request/response schemas.

### Base URL: `/api/v1`

### Authentication
```
POST   /api/v1/auth/register     # Create account
POST   /api/v1/auth/login        # Get JWT tokens
POST   /api/v1/auth/refresh      # Refresh access token
POST   /api/v1/auth/logout       # Revoke tokens
```

### Records
```
GET    /api/v1/records            # List records (paginated, filterable)
GET    /api/v1/records/:id        # Get single record with FHIR resource
GET    /api/v1/records/search     # Full-text search
DELETE /api/v1/records/:id        # Soft delete
```

### Timeline
```
GET    /api/v1/timeline           # Timeline data (date-ordered, filterable)
GET    /api/v1/timeline/stats     # Aggregated stats for dashboard
```

### Upload & Ingestion
```
POST   /api/v1/upload             # Upload file(s) — multipart (JSON, ZIP, or individual TSVs)
POST   /api/v1/upload/epic-export # Upload Epic EHI Tables export (ZIP or multipart directory)
GET    /api/v1/upload/:id/status  # Ingestion job status (poll for progress on large imports)
GET    /api/v1/upload/:id/errors  # Ingestion errors for a specific upload (row-level details)
GET    /api/v1/upload/history     # Upload history with record counts
DELETE /api/v1/upload/:id         # Cancel in-progress import or delete upload record
```

### AI Summary Prompts (No External API Calls)
```
POST   /api/v1/summary/build-prompt   # Build de-identified prompt (returns prompt, NOT AI response)
GET    /api/v1/summary/prompts        # List previously built prompts
GET    /api/v1/summary/prompts/:id    # Get prompt detail (for re-copying)
POST   /api/v1/summary/paste-response # User pastes AI response back for storage
GET    /api/v1/summary/responses      # List stored responses
```

### Deduplication
```
GET    /api/v1/dedup/candidates   # List dedup candidates (supports ?page=1&limit=20 pagination)
POST   /api/v1/dedup/merge        # Merge two records (primary_record_id optional)
POST   /api/v1/dedup/dismiss      # Dismiss candidate pair
```

### Dashboard
```
GET    /api/v1/dashboard/overview # Dashboard summary data
GET    /api/v1/dashboard/labs     # Lab-specific dashboard data
```

---

## Build Phases & Execution Order

### Phase 1: Foundation — COMPLETE
1. Project scaffolding (both backend and frontend)
2. Git init, `.gitignore` with PHI-safe exclusions
3. Local PostgreSQL + Redis setup script (`scripts/setup-local.sh`)
4. Database models + Alembic migrations (unified `health_records` table)
5. User auth (register, login, JWT with bcrypt)
6. Basic API structure with health check
7. Frontend auth pages + dashboard shell

### Phase 2: Structured Data Ingestion — COMPLETE
1. File upload API with validation (accept JSON)
2. FHIR R4 JSON parser — parses Bundle resources, extracts entries, maps to `health_records`
3. Epic EHI Tables parser — 5 mappers built (problems, results, medications, encounters, documents)
4. Bulk inserter with batched DB writes
5. Upload UI with drag-and-drop in Admin Console
6. Ingestion status tracking and error reporting endpoints
7. Synthetic test fixtures (`sample_fhir_bundle.json`, `sample_epic_tsv/`)

### Phase 3: Record Display & Timeline — COMPLETE
1. Records list API with pagination + filtering + search
2. Timeline API with date aggregation + stats
3. Unified Admin Console with 12-tab interface (replaces individual category pages)
4. Record detail view with FHIR resource JSON display
5. Dashboard home page with overview stats + recent activity
6. Timeline page with type filtering

### Phase 4: AI Prompt Builder — COMPLETE
1. PHI scrubber / de-identification service
2. Prompt builder constructs de-identified prompts for `gemini-3-flash-preview`
3. Prompt API endpoints (build-prompt, list prompts, paste-response, list responses)
4. Summaries page with prompt build + review + copy + paste-back UI
5. AI disclaimer included in all prompt-related UI

### Phase 5: Deduplication — COMPLETE
1. Duplicate detection service (exact matching)
2. Dedup candidate storage + paginated API (`?page=1&limit=20`)
3. Merge and dismiss endpoints with proper response contracts
4. Dedup management UI in Admin Console tab

### Phase 6: Unstructured Data Scaffolding — NOT STARTED
_(Spec retained below for future implementation)_
1. LangExtract integration scaffold: extraction schemas, few-shot examples (config only, NO install)
2. FHIR mapping layer for LangExtract output
3. Response parser for pasted-back extraction results
4. OCR scaffold: PyMuPDF/Tesseract text extraction + AI post-processing prompts
5. Upload UI extension for unstructured files
6. Unstructured extraction prompt flow

### Phase 7: Polish & Testing — PARTIAL
1. 83 backend tests across 8 files — ALL PASSING
2. E2E testing: 3 flows verified manually via Playwright MCP (auth, upload+timeline, admin console)
3. No automated Playwright specs or Vitest frontend tests yet
4. Remaining: automated E2E specs, accessibility audit, HIPAA compliance checklist

---

## Testing Strategy

### Current Test Suite: 83 Backend Tests

All tests are in flat files under `backend/tests/`:

| File | Tests | Coverage |
|------|-------|----------|
| `test_auth.py` | 6 | Register, login, protected routes, token refresh |
| `test_records.py` | 12 | CRUD, pagination, filtering, search, soft delete |
| `test_dashboard.py` | 10 | Overview stats, labs endpoint, type counts |
| `test_timeline.py` | 8 | Timeline data, filtering, stats, total count |
| `test_upload.py` | 9 | Upload flow, status polling, error endpoint, history |
| `test_summary.py` | 12 | Prompt build, de-identification, paste-response, list |
| `test_dedup.py` | 15 | Candidates, merge, dismiss, pagination |
| `test_ingestion.py` | 11 | FHIR parser, Epic mappers (problems, results, meds, encounters, documents) |

### Test Helpers (in `conftest.py`)

```python
auth_headers(client, email, password)  # Register + login, return {"Authorization": "Bearer ..."}
create_test_patient(client, headers)    # Create a patient, return patient_id
seed_test_records(client, headers, patient_id, count=5)  # Seed health records
```

### Test Fixtures
- **Synthetic fixtures** (committed, always available): `sample_fhir_bundle.json`, `sample_epic_tsv/` (6 TSVs)
- **User-provided fixtures** (gitignored): `user_provided_fhir.json`, `epic_export/` — tests fall back to synthetic if not present

### Running Tests
```bash
# Run all 83 backend tests
cd backend && python -m pytest -x -v

# Run specific test file
cd backend && python -m pytest tests/test_dedup.py -v

# Run with short traceback
cd backend && python -m pytest -x -v --tb=short
```

### Frontend Testing
- **No automated tests configured yet** — no Vitest or Playwright automation
- **Manual E2E** verified via Playwright MCP browser testing:
  - Flow A: Register → Login → Dashboard loads
  - Flow B: Upload FHIR JSON → Records appear in timeline
  - Flow C: Admin Console tabs navigate correctly

---

## Environment Variables

```env
# Database (native Homebrew PostgreSQL — uses trust auth by default on macOS)
DATABASE_URL=postgresql+asyncpg://localhost:5432/medtimeline
DATABASE_ENCRYPTION_KEY=<32-byte-hex-key>

# Auth
JWT_SECRET_KEY=<random-64-char-string>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# AI Prompt Builder (NO API keys — prompts are built locally, user executes externally)
# GEMINI_API_KEY is intentionally NOT here — no external AI calls are made
PROMPT_TARGET_MODEL=gemini-3-flash-preview
PROMPT_SUGGESTED_TEMPERATURE=0.3
PROMPT_SUGGESTED_MAX_TOKENS=4096
PROMPT_SUGGESTED_THINKING_LEVEL=low

# Redis (for background jobs)
REDIS_URL=redis://localhost:6379/0

# File Storage
UPLOAD_DIR=./data/uploads
TEMP_EXTRACT_DIR=./data/tmp              # temp directory for ZIP extraction, cleaned after ingestion
MAX_FILE_SIZE_MB=500                     # single file upload limit (Epic TSVs can be large)
MAX_EPIC_EXPORT_SIZE_MB=5000             # total Epic export ZIP/directory limit (5GB)
INGESTION_BATCH_SIZE=100                 # records per DB batch insert
INGESTION_WORKER_CONCURRENCY=1           # single worker for memory safety on 16GB machine

# App
APP_ENV=development
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
```

---

## Coding Standards & Conventions

### Python (Backend)
- Python 3.12+ with type hints on ALL function signatures
- Async/await throughout (async SQLAlchemy, async httpx)
- Pydantic v2 for all data validation
- Use `from __future__ import annotations` in every file
- Docstrings on all public functions (Google style)
- No bare `except:` — always catch specific exceptions
- Use `logging` module, never `print()`
- Max line length: 100 chars (ruff formatter)
- Import ordering: stdlib → third-party → local (ruff isort)

### TypeScript (Frontend)
- Strict TypeScript (`strict: true` in tsconfig)
- Functional components only, no class components
- Named exports (no default exports except pages)
- Use TypeScript interfaces for all API response types
- Tailwind for all styling — no CSS modules, no styled-components
- Prefer server components; use `'use client'` only when needed
- All API calls through the centralized `lib/api.ts` client

### Git
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- One logical change per commit
- Keep commits atomic and buildable
- Tag phase milestones, use feature branches for risky changes
- See **Git Version Control** section for full commit strategy, revert patterns, and branch workflow

---

## Performance Constraints (M4 MacBook Air 16GB)

### System Resource Budget
- **PostgreSQL** (native Homebrew): shared_buffers=512MB, work_mem=32MB, maintenance_work_mem=256MB, effective_cache_size=2GB, max_connections=20, max_wal_size=2GB, checkpoint_timeout=15min. Tuning applied via `scripts/pg-tuning.sql` run once after install.
- **Redis** (native Homebrew): maxmemory=256MB, allkeys-lru eviction. Set in `/opt/homebrew/etc/redis.conf`.
- **Backend**: 2 Uvicorn workers (match efficiency cores). Single ingestion worker for large imports — never run two large imports concurrently.
- **Frontend**: Next.js dev server default settings
- **Python backend process**: Should never exceed ~2GB RSS during ingestion. Monitor with `resource.getrusage()` in ingestion coordinator.
- AI prompt building: No external API calls made, so no rate limiting needed. Prompt construction is CPU-only and fast.

### Large File Ingestion Strategy

Epic EHI exports can be **hundreds of TSV files totaling multiple gigabytes**. FHIR bundles can contain tens of thousands of entries. All ingestion MUST work within the 16GB memory envelope.

**Mandatory rules for all parsers:**

1. **Stream, never slurp.** Never call `.read()`, `.read_text()`, `json.loads(big_file.read())`, or `list(reader)` on large files. Use iterators and streaming parsers.
2. **Process one file at a time.** Never have two large TSV files open simultaneously. Finish one, close it, start the next.
3. **Batch inserts: 100 records per batch.** Accumulate records in a list, flush to DB with `executemany`/bulk insert at 100 records, then `batch.clear()`. Commit after each batch to keep transaction WAL small.
4. **Commit frequently.** Don't wrap an entire large import in one transaction. Commit per batch (every 100 records). This keeps PostgreSQL's WAL writer happy and avoids running out of shared memory.
5. **No full in-memory indexes of large tables.** For cross-table ID resolution in Epic, use small focused lookups (patient IDs are fine — there's typically one patient). For order→result joins, insert first, then use SQL joins.
6. **Background processing for large imports.** Any import that might take > 5 seconds (i.e., multi-file Epic exports) MUST run as an async background task (via `arq` or `FastAPI.BackgroundTasks`), not in the request handler. Return a job ID immediately and let the frontend poll for status.
7. **Report progress granularly.** Update ingestion status per-file and per-batch so the UI can show: "Processing file 12/47 (MEDICATIONS.tsv) — 8,400 records ingested"
8. **Temp directory cleanup.** If a ZIP is extracted to a temp dir, clean it up after processing. Use `tempfile.TemporaryDirectory()` as a context manager.

**Streaming JSON for large FHIR bundles:**
```python
# For FHIR bundles > 10MB, use ijson (streaming JSON parser)
import ijson  # add to dependencies

async def parse_large_fhir_bundle(file_path: Path, ...):
    with open(file_path, "rb") as f:
        entries = ijson.items(f, "entry.item")
        batch = []
        for entry in entries:
            resource = entry.get("resource")
            if resource:
                batch.append(map_fhir_resource(resource))
            if len(batch) >= 100:
                await bulk_insert_records(db, batch, ...)
                batch.clear()
                await db.commit()
        if batch:
            await bulk_insert_records(db, batch, ...)
            await db.commit()
```

**Upload size limits (adjusted for local machine):**
- Single file upload: 500MB max (Epic TSV files can be individually large)
- Total import batch: 5GB max (entire Epic export directory or ZIP)
- These limits are validated at the API layer BEFORE processing begins
- For ZIP uploads > 1GB, extract to temp directory with streaming (`zipfile` extractall), never to memory

**Database performance for large imports:**
- Disable per-row index updates during bulk import: use `SET LOCAL synchronous_commit = OFF` within import transaction batches for 2-3x write speed, re-enable after import completes
- After a large import completes, run `ANALYZE` on `health_records` table to update query planner statistics
- Partial indexes: the GIN index on `fhir_resource` JSONB is expensive. Consider deferring it (create after import) for imports > 10k records
- Connection pooling: use SQLAlchemy's pool with `pool_size=5, max_overflow=5` to avoid exhausting the 20-connection limit during parallel test runs

---

## Git Version Control

Claude Code MUST use local git for version control throughout the build. This enables safe rollback if a phase or feature breaks.

### Repository Setup (Phase 1, Step 1)
```bash
cd medtimeline
git init
git add -A
git commit -m "chore: initial project scaffolding"
```

### Commit Strategy
- **Commit after every logical unit of work.** Each build phase sub-step gets its own commit.
- **Commit BEFORE starting risky changes** (new parser, schema migration, major refactor).
- **Never commit user-provided test fixtures** (they're gitignored and may contain PHI).
- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- Keep commits atomic — each commit should build and pass existing tests.

### Example commit sequence for Phase 2:
```
feat: add FHIR R4 JSON parser with bundle support
test: add FHIR parser tests against user-provided fixtures
feat: add Epic EHI Tables base parser with streaming TSV reader
feat: add Epic patient table mapper
feat: add Epic problem_list and medical_hx mappers
feat: add Epic order_results mapper
feat: add Epic medications mapper
test: add Epic parser integration tests
feat: add FHIR normalization layer
feat: add upload API with file validation
feat: add upload UI with drag-and-drop
refactor: extract bulk_inserter from parsers
```

### Reverting on Failure
If a feature breaks the build or tests, Claude Code should:
1. First try to fix the issue directly
2. If the fix is non-obvious or cascading, revert to the last good commit:
```bash
# Revert last commit (keep changes in working tree for inspection)
git revert HEAD --no-commit

# Or hard reset to last known good state (discards changes)
git reset --hard HEAD~1

# Or reset to a specific commit
git log --oneline -10  # find the good commit
git reset --hard <commit-hash>
```
3. After reverting, attempt the feature again with a different approach.
4. If a migration breaks, revert both the migration and the code:
```bash
cd backend && alembic downgrade -1  # revert last migration
git reset --hard HEAD~1             # revert the code that generated it
```

### Branch Strategy (Optional but Recommended)
For risky features, Claude Code can use a feature branch:
```bash
git checkout -b feat/epic-parser
# ... build the feature with multiple commits ...
# If it works:
git checkout main && git merge feat/epic-parser
# If it fails:
git checkout main  # abandon the branch cleanly
```

### Tags for Phase Milestones
After each build phase passes all tests, tag it:
```bash
git tag -a phase-1-foundation -m "Phase 1 complete: auth, DB, API shell"
git tag -a phase-2-ingestion -m "Phase 2 complete: FHIR + Epic parsers"
git tag -a phase-3-display -m "Phase 3 complete: timeline, dashboard, records UI"
```
This gives safe rollback points if a later phase destabilizes earlier work.

---

## Absolute Rules for Claude Code

1. **NEVER generate diagnoses, treatment suggestions, or medical advice in any code, prompt template, or UI text.**
2. **NEVER make any external HTTP/API calls to AI services.** No `google-genai`, no `openai`, no `httpx.post()` to any AI endpoint. The app builds prompts ONLY.
3. **NEVER install any AI SDK or client library** (`google-genai`, `google-generativeai`, `openai`, `anthropic`, `langextract`, etc.). These must not appear in `pyproject.toml`, `requirements.txt`, or `package.json`. LangExtract config and mapping code is scaffolded, but the library itself is never installed.
4. **NEVER store, load, or reference API keys for AI services** in code, environment variables, config files, or .env templates. No `GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.
5. **NEVER include raw PII/PHI in any constructed prompt.** All health data in prompts must pass through the PHI scrubber first. Write tests that verify this.
6. **NEVER hard-delete health records.** Always soft-delete with `deleted_at`.
7. **NEVER expose stack traces or internal errors in API responses.**
8. **NEVER store passwords in plaintext.** Always bcrypt with cost ≥ 12.
9. **NEVER skip audit logging** on data access or mutation endpoints.
10. **NEVER commit user-provided test fixtures to git.** They may contain real PHI. Gitignore them.
11. **ALWAYS enforce user-scoped data access** — every DB query MUST filter by `user_id`.
12. **ALWAYS include the AI disclaimer** component wherever AI prompts or pasted-back responses are displayed.
13. **ALWAYS validate and sanitize file uploads** before processing.
14. **ALWAYS write tests** alongside new features — no untested code in services or parsers.
15. **ALWAYS build and test parsers against user-provided real files first** (with synthetic fallback for CI).
16. **Target ONLY `gemini-3-flash-preview`** in prompt metadata and suggested config. No other models.
17. **Use ONLY open-source, permissively-licensed libraries** (MIT, Apache 2.0, BSD). No GPL in runtime dependencies.

---

## Quick Start (for Claude Code to bootstrap)

```bash
# 1. Create project root and init git
mkdir -p medtimeline && cd medtimeline
git init

# 2. Copy this CLAUDE.md to root
# 3. Create .claude/settings.json (see companion file)

# 4. Prerequisites — ensure native services are running (user handles this before Claude Code starts)
#    brew install postgresql@16 redis node python@3.12
#    brew services start postgresql@16
#    brew services start redis
#    createdb medtimeline
#    psql medtimeline < scripts/init-db.sql    # pgcrypto, uuid-ossp, pg_trgm extensions
#    psql medtimeline < scripts/pg-tuning.sql  # performance tuning for large imports

# 5. Bootstrap backend
mkdir -p backend && cd backend
# Use uv or pip to init Python project with pyproject.toml
# Install: fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic pydantic-settings
#          python-jose[cryptography] passlib[bcrypt] python-multipart ijson
#          fhir.resources fhirpathpy httpx python-dotenv arq redis
#          pytest pytest-asyncio httpx factory-boy ruff
# Do NOT install: google-genai, google-generativeai, openai, anthropic, langextract

# 6. Bootstrap frontend
cd .. && npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir
cd frontend
# Install: @tanstack/react-query zustand next-auth react-dropzone recharts
#          date-fns zod lucide-react sonner next-themes
# Install shadcn: npx shadcn@latest init
# Add components: button card input label dialog sheet table badge tabs separator
#                 dropdown-menu command popover calendar toast alert avatar scroll-area

# 7. First commit
cd .. && git add -A && git commit -m "chore: initial project scaffolding"

# 8. Run migrations
cd backend && alembic upgrade head
git add -A && git commit -m "feat: initial database schema and migrations"

# 9. Place user-provided test fixtures
#    User will provide:
#      - FHIR JSON export → backend/tests/fixtures/user_provided_fhir.json
#      - Epic EHI Tables export dir → backend/tests/fixtures/epic_export/
#    Build and test parsers against these real files.
#    These are gitignored — never committed.

# 10. Start dev servers
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```
