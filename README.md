# MedTimeline

Local-first personal health records app. Ingests structured clinical data (FHIR, Epic EHI, CDA XML) and unstructured documents (PDF, RTF, TIFF), normalizes everything into FHIR R4 in PostgreSQL, and displays it on a timeline. AI features are optional — works fine without an API key.

## How data flows

```
  Upload                    Detect & Route                     Parse                         Store
 ────────                  ──────────────                    ───────                       ───────

 .json ──────────────────► FHIR R4 parser ──────────────────────────────────────┐
                                                                                │
 .zip ───► extract ──┬───► Epic EHI parser (14 TSV mappers) ────────────────────┤
           │         │                                                          │
           │         ├───► IHE XDM (METADATA.XML → CDA docs → FHIR) ───────────┤
           │         │         └── cross-doc dedup before insert                │
           │         │                                                          │
           │         └───► Mixed content (TSV + JSON + PDF/RTF/TIFF) ───────────┤
           │                                                                    │
 .xml ─────┼────────────► Standalone CDA → python-fhir-converter → FHIR ────────┤
           │                                                                    ▼
 .pdf ─────┤                                                        ┌───────────────────────┐
 .rtf ─────┼──► Text extraction ──► PHI scrub ──► Entity extraction │                       │
 .tiff ────┘    (Gemini vision)     (18 HIPAA      (LangExtract)    │    health_records      │
                                     types)              │          │    (FHIR R4 JSONB)     │
                                                         ▼          │                       │
                                                 7 entity types ────►    + dedup engine      │
                                                 with confidence    │    + audit log         │
                                                 scores             │    + AES-256 at rest   │
                                                                    └───────────────────────┘
```

## Dedup pipeline

Every upload triggers a two-tier dedup scan against existing records:

```
  New records from upload
          │
          ▼
  ┌─────────────────┐     Bucketed by (record_type, code_value).
  │ Heuristic scorer │     Weighted score:
  │                  │       code_value   0.40
  │  score >= 0.95 ──┼──► auto-merge (mark secondary as duplicate)
  │                  │
  │  0.50 .. 0.94 ──┼──► send pair to LLM judge
  │                  │
  │  score < 0.50 ──┼──► no match, skip
  └─────────────────┘
          │
          ▼
  ┌─────────────────┐
  │  Gemini LLM     │     Classifies each pair:
  │  Judge          │
  │  "duplicate" ───┼──► auto-merge    (confidence >= 0.8)
  │  "distinct"  ───┼──► auto-dismiss  (confidence >= 0.8)
  │  "update"    ───┼──► pending review
  │  "related"   ───┼──► pending review
  └─────────────────┘
          │
          ▼
  User resolves pending pairs in Admin Console
  (merge / dismiss / field-level cherry-pick / undo)
```

## Ingestion formats

```
┌──────────────────┬───────────────┬──────────────────────────────────────────┐
│ Format           │ File type     │ What it produces                         │
├──────────────────┼───────────────┼──────────────────────────────────────────┤
│ FHIR R4 Bundle   │ .json         │ 18 resource types → health_records       │
│ Epic EHI Tables  │ .zip of .tsv  │ 14 table mappers → FHIR resources        │
│ CDA XML          │ .xml          │ ClinicalDocument → FHIR via converter    │
│ IHE XDM          │ .zip          │ METADATA.XML manifest → CDA docs → FHIR  │
│ Unstructured     │ .pdf/rtf/tiff │ Gemini OCR → entity extraction → FHIR    │
└──────────────────┴───────────────┴──────────────────────────────────────────┘

Epic EHI mappers:

  PROBLEM_LIST ─────► Condition          ALLERGY ──────────► AllergyIntolerance
  PROBLEM_LIST_ALL ─► Condition          IMMUNE ───────────► Immunization
  MEDICAL_HX ──────► Condition          ORDER_PROC ───────► Procedure
  ORDER_MED ───────► MedicationRequest  IP_FLWSHT_MEAS ──► Observation (vitals)
  ORDER_RESULTS ───► Observation        REFERRAL ─────────► ServiceRequest
  PAT_ENC ─────────► Encounter          PAT_ENC_DX ──────► Condition (enc-dx)
  DOC_INFORMATION ─► DocumentReference  SOCIAL_HX ────────► Observation (social)
                                         FAMILY_HX ────────► FamilyMemberHistory

FHIR parser handles: Condition, Observation, MedicationRequest, MedicationStatement,
AllergyIntolerance, Procedure, Encounter, Immunization, DiagnosticReport,
DocumentReference, ImagingStudy, ServiceRequest, CarePlan, Communication,
Appointment, CareTeam, ImmunizationRecommendation, QuestionnaireResponse
```

## AI modes

```
  Mode 1: Prompt-only (no API key)         Mode 2: Live API (needs GEMINI_API_KEY)
 ─────────────────────────────────         ────────────────────────────────────────

  health_records                            health_records
       │                                         │
       ▼                                         ▼
  PHI scrubber (strips 18 HIPAA IDs)        PHI scrubber
       │                                         │
       ▼                                         ▼
  Build prompt (system + user)              Build prompt
       │                                         │
       ▼                                         ▼
  Return to user as copyable text           Send to Gemini API
  User pastes into any LLM                       │
  User pastes response back (optional)           ▼
                                            Return summary (text / JSON / both)

  Summary types: full, category, date-range, single-record
  Models: gemini-3-flash-preview (summary + OCR), gemini-2.5-flash (entity extraction)
```

## Database

```
┌──────────────────┬────────────────────────────────────────────────────────┐
│ Table            │ Purpose                                                │
├──────────────────┼────────────────────────────────────────────────────────┤
│ users            │ Auth (email/password encrypted, lockout after 5 fails) │
│ revoked_tokens   │ JWT blacklist (JTI-indexed)                            │
│ patients         │ Demographics (all PII fields AES-256 encrypted)        │
│ health_records   │ All clinical data: FHIR R4 JSONB, soft-delete only     │
│ uploaded_files   │ Upload tracking, extraction state, ingestion progress   │
│ ai_summary_prompts│ De-identified prompts + responses                     │
│ dedup_candidates │ Duplicate pairs with scores + LLM classification       │
│ provenance       │ Data lineage (who changed what, from which file)        │
│ audit_log        │ HIPAA audit trail on all 19+ data endpoints             │
└──────────────────┴────────────────────────────────────────────────────────┘

All tables: UUID PKs, created_at/updated_at timestamps.
PII encrypted at rest via AES-256/pgcrypto.
```

## HIPAA controls

```
  Authentication          Data protection         Monitoring
 ────────────────        ──────────────────       ────────────

  bcrypt (cost 12+)       AES-256 at rest          Audit log on all
  JWT 15-min access       PHI scrub before AI      data endpoints
  7-day refresh           Soft delete only          Rate limiting
  Token revocation        User-scoped queries       Account lockout
  Password complexity     UUID upload filenames     30-min idle timeout
  HSTS + CSP headers      No PII in error msgs     CORS hardening
```

## Tech stack

**Backend**: Python 3.12 / FastAPI / SQLAlchemy 2 async / PostgreSQL 16 / Alembic / Gemini API / LangExtract / python-fhir-converter

**Frontend**: Next.js 15 / TypeScript / Tailwind CSS 4 / shadcn/ui / TanStack Query / Zustand / NextAuth.js

**Infra**: PostgreSQL 16 + Redis 7 via Homebrew, macOS. No Docker.

## Project structure

```
backend/
├── app/
│   ├── main.py, config.py, database.py
│   ├── middleware/          # auth, audit, encryption, security headers, rate limit
│   ├── models/              # user, patient, record, uploaded_file, ai_summary, dedup, provenance, audit
│   ├── api/                 # auth, records, timeline, upload, summary, dedup, review, dashboard
│   └── services/
│       ├── ingestion/       # coordinator, fhir_parser, epic_parser, cda_parser, xdm_parser,
│       │                    # cda_dedup, bulk_inserter, epic_mappers/ (14)
│       ├── ai/              # prompt_builder, summarizer, phi_scrubber
│       ├── extraction/      # text_extractor, entity_extractor, section_parser, entity_to_fhir
│       └── dedup/           # detector, orchestrator, llm_judge, field_merger
├── tests/                   # 26 test files, 517 tests
└── alembic/                 # migrations

frontend/src/
├── app/(dashboard)/         # home, timeline, upload (+review), summaries, admin (4-tab), records/[id]
├── components/retro/        # 16 custom components (Mature Zen theme)
└── lib/                     # api.ts, utils.ts, constants.ts
```

## Setup

```bash
# 1. infra
brew services start postgresql@16 && brew services start redis
createdb medtimeline && createdb medtimeline_test
psql medtimeline < scripts/init-db.sql
psql medtimeline_test -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# 2. env
cp .env.example .env
# edit: DATABASE_ENCRYPTION_KEY, JWT_SECRET_KEY
# optional: GEMINI_API_KEY (for live AI features)

# 3. backend
cd backend && pip install -e ".[dev]"
alembic upgrade head
DATABASE_URL=postgresql+asyncpg://localhost:5432/medtimeline_test alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 4. frontend
cd frontend && npm install && npm run dev
# open http://localhost:3000
```

## Tests

```bash
cd backend
python -m pytest -x -v                            # ~440 fast tests
python -m pytest -x -v --run-slow                  # all 517 (needs GEMINI_API_KEY for 7 slow)
python -m pytest tests/test_hipaa_compliance.py -v # HIPAA suite (28 tests)
python -m pytest tests/fidelity/ -v                # fidelity checks (Epic + FHIR + CDA)
```

```
Test coverage by area:

  auth ··················  10    ingestion ···········  59    dedup orchestrator ··  12
  records ···············  15    pipeline integration ·  21    llm judge ···········   9
  dashboard ·············  10    xdm parser ··········   8    field merger ·········   6
  timeline ··············   8    xdm ingestion ·······   5    review api ··········   7
  upload ················  10    cda parser ··········   9    hipaa compliance ····  28
  summary ···············  10    cda dedup ···········   7    epic fidelity ·······  138
  dedup ·················   9    text extraction ·····  12    fhir fidelity ·······  33
  summarization ·········   9    entity extraction ···  19    cda fidelity ········  10
  unstructured upload ···  22    expanded extraction ·  20
                                 section parser ······  11
```

Tests hit `medtimeline_test` (auto-derived from `DATABASE_URL`). Fidelity tests skip when real-data fixtures are absent.

## API

Full contract: [`docs/backend-handoff.md`](docs/backend-handoff.md)

```
POST   /auth/register, /login, /refresh, /logout     GET  /dashboard/overview, /labs, /patients
GET    /records, /records/:id, /records/search        GET  /timeline
DELETE /records/:id                                   GET  /dedup/candidates
POST   /upload                                        POST /dedup/merge, /dedup/dismiss
POST   /upload/unstructured, /unstructured-batch      GET  /upload/:id/review
GET    /upload/:id/status, /errors, /extraction       POST /upload/:id/review/resolve, /undo-merge
POST   /upload/:id/confirm-extraction                 POST /summary/build-prompt, /generate
GET    /upload/history, /pending-extraction            POST /summary/paste-response
POST   /upload/trigger-extraction                     GET  /summary/prompts, /prompts/:id, /responses
```

## License

[MIT](LICENSE)
