# Idempotent Incremental Ingestion — Design (Phase 1: Structured)

**Date:** 2026-05-29
**Status:** Approved (design); pending implementation plan
**Branch:** `feat/idempotent-incremental-ingestion`

## Problem

EHR exports are cumulative: each new extract re-includes records from prior extracts.
Today the pipeline blindly inserts every incoming record as a new row, then runs a
post-insertion content/fuzzy/LLM dedup pass to mark duplicates. This causes:

1. **Write amplification** — re-uploading a 10k-record cumulative extract inserts 10k new
   rows, then runs an LLM-assisted scan to discover ~9.5k are duplicates.
2. **Fuzzy misses** — content matching can miss a true duplicate if the source tweaks a
   code or date between exports.
3. **No update path** — corrections from a newer extract (e.g. a problem flips
   `active → resolved`, a lab value is corrected) are treated as new records or dropped,
   rather than updating the existing record.

There is currently **no idempotency key**: the source system's own stable record id
(FHIR `resource.id`, CDA act `<id>`, Epic table primary key) is never extracted, indexed,
or matched on.

## Goal & Behavior Contract

Re-uploading a cumulative extract must **converge, not duplicate**. For every structured
record carrying a stable source id:

| Situation | Action |
|-----------|--------|
| Source id not seen before | **Insert** (new record) |
| Source id seen, content identical | **No-op** (skip — no insert, no dedup scan, no LLM) |
| Source id seen, content changed | **Update in place** + snapshot prior version (audit trail) |
| No stable source id (AI-extracted) | Fall through to existing content/fuzzy dedup (Phase 2 adds content-hash) |

**Update semantics:** update-in-place **with history** — the current row always reflects the
latest content; each prior version is snapshotted for a full audit trail (aligns with HIPAA
provenance). Decided over overwrite-no-history and skip-on-id-match.

**Scope:** both structured and unstructured, **built structured-first**.
- **Phase 1 (this spec):** stable-id upsert for FHIR / CDA / Epic. Validated against the real
  `HealthSummary_May_29_2026` IHE XDM extract.
- **Phase 2 (follow-on spec):** content-hash idempotency layer for AI-extracted/unstructured
  records (clinical note PDF, transcripts, phone notes), which have no stable source id.

## Architecture (Approach A — pre-insert identity gate, dedup pipeline unchanged)

A new `external_id` identity layer runs **before** `bulk_inserter`. For each incoming
structured record, extract its stable source key, look up existing rows by
`(user_id, source_system, external_id)`, and partition into insert / update / skip. The
existing content/fuzzy/LLM dedup pipeline is left intact and runs **after** the gate, but now
only sees genuinely new (inserted) records — so it does what it is good at (cross-source and
AI-extracted duplicates) without re-litigating records we positively identified by id.

Rejected alternatives:
- **B — fold identity into the dedup detector (post-insert):** keeps write amplification;
  update-in-place maps awkwardly onto merge semantics.
- **C — DB-level `ON CONFLICT DO UPDATE`:** "did it change? snapshot the old version" logic
  is clumsy inside `ON CONFLICT`; loses the clean update-vs-noop distinction and the
  version-capture hook; unstructured still needs a separate path.

```
incoming records ──► identity gate ──► [insert | update+snapshot | skip]
                          │                  │
                          │ (records w/o      └─► inserted records ──► existing content/fuzzy/LLM dedup
                          │  stable id)
                          └────────────────────► existing path unchanged
```

## Data Model

New nullable columns on `health_records`:
- `external_id` (TEXT) — normalized stable source identifier.
- `source_system` (TEXT) — namespace that scopes `external_id` (CDA root OID, FHIR system
  base, or `epic:<table>`).
- `content_hash` (TEXT) — sha256 of canonicalized `fhir_resource`; detects changed-vs-identical
  and serves as the Phase-2 unstructured key.
- `version` (INT, default 1) — current version number.

Indexes:
- **Partial unique index** on `(user_id, source_system, external_id)
  WHERE deleted_at IS NULL AND external_id IS NOT NULL` — at most one live row per identity
  per user (HIPAA rule 11: user-scoped access).

New table `record_versions`:
- `id` (UUID PK), `record_id` (FK → health_records), `version` (INT),
  `fhir_resource` (JSONB snapshot), `content_hash` (TEXT), `changed_fields` (JSONB),
  `source_file_id` (UUID — the upload that produced this version), `created_at`.
- Full-snapshot history of every correction. A `provenance` row with action
  `updated_on_reupload` is also written on each update.

**Backfill migration:** re-derive `external_id` / `source_system` / `content_hash` for
existing rows from their stored `fhir_resource`. Batched and idempotent (safe to re-run).

## Components

### `services/ingestion/identity.py` — format-aware identity extraction
`extract_identity(record_dict, source_format) -> Identity | None`

- **FHIR:** `external_id = f"{resourceType}/{resource.id}"`; `source_system` from
  `meta.source` / fullUrl base, else `"fhir"`. Prefer `resource.identifier[0]` (system+value)
  when present.
- **CDA:** act-level `<id root extension>` → `source_system = root`, `external_id = extension`.
  **Must exclude** provider ids (`2.16.840.1.113883.4.6` NPI) and person ids (`…4.2`) — only
  the clinical-act id.
- **Epic TSV:** per-table primary key → `source_system = f"epic:{table}"`,
  `external_id = PK value`. Add `primary_key_columns` to each `TableSpec` / mapper.
- Returns `None` when no stable id is recoverable → record flows to the existing path
  unchanged. Extraction never raises into ingestion: on failure it logs and returns `None`.

> **Known risk — first verification spike.** The CDA path stores whatever `CcdaRenderer`
> (python-fhir-converter) emits (`cda_parser.py:94`). It is **not yet confirmed** that the
> renderer preserves the CDA `<id>` into FHIR `resource.identifier` / `resource.id`. The
> plan's first task is a **test that asserts identity is recoverable from the real
> `DOC0001.XML`**. If the renderer drops source ids, the CDA path gets a fallback that parses
> the act `<id>` directly from the CDA XML and attaches it. We prove this before building on it.

### `services/ingestion/content_hash.py` — canonical content hashing
`content_hash = sha256(canonical_json(fhir_resource))` with a canonicalization that **strips
volatile noise** (`meta.lastUpdated`, `_extraction_metadata`, narrative `text.div`) but
**preserves clinically meaningful fields**. Test-critical invariants:
- same clinical content + different `meta.lastUpdated` → **same** hash;
- status `active → resolved` (or any clinical field change) → **different** hash.

### `services/ingestion/idempotent_inserter.py` — upsert flow (replaces direct `bulk_insert` for structured paths)
Per batch:
1. Compute `(source_system, external_id, content_hash)` for each record.
2. Dedupe **within-batch** by identity (defends against cross-document repeats; complements
   `cda_dedup`).
3. **One** batch `SELECT` of existing rows by `(user_id, (source_system, external_id) IN …)`
   — index-backed, not N queries.
4. Partition → `insert` / `update+snapshot` / `skip`.
5. Return stats `{inserted, updated, unchanged}`. Only **inserted** records are forwarded to
   the existing content-dedup pipeline.

`coordinator.py:152` wiring changes from "insert → dedup-everything" to
"identity-gate → dedup-new-only".

## Error Handling & Safety

- **Never hard-delete** (rule 6) — updates snapshot the prior version; nothing is destroyed.
- **User-scoped** (rule 11) — every lookup filters by `user_id`.
- **Identity collision** (same `(source_system, external_id)`, divergent clinical meaning) →
  log a warning, trust the source id (Epic/CDA ids are reliable). Covered by an edge test.
- **Atomicity** — gate + version snapshot + insert run in one transaction per batch.
- **Low regression risk** — the existing dedup pipeline is untouched; only its input set
  narrows to genuinely new records.

## Test Strategy (expected-output-first)

Every unit gets its **expected output defined and a failing test written before
implementation** (per standing TDD rule):

- **Unit `identity.py`:** golden `(source_system, external_id)` per format, including negative
  cases (NPI / person id must NOT be selected as the record id).
- **Unit `content_hash.py`:** pinned hash-stability cases (meta noise → same hash; clinical
  field change → different hash).
- **Unit partitioner:** given existing + incoming sets → expected insert/update/skip
  classification + version increment + snapshot creation.
- **Integration:** ingest the XDM extract twice → 2nd run yields 0 inserts and 0 new
  duplicates; mutate one record's status in a copy → 1 update + 1 `record_versions` row.
- **Fidelity (real `HealthSummary_May_29_2026`):** first ingest = N records; re-ingest delta
  = 0; assert no `is_duplicate` explosion. Marked `@pytest.mark.fidelity`, skips when fixture
  data is absent.
- **Regression:** the full existing dedup / ingestion suite stays green.

## TDD-Gap Audit (deliverable)

As part of this work, audit and report gaps in the *existing* pipeline's tests, and fold the
critical fixes into the plan rather than silently working around them. Known starting points:
- `bulk_inserter` has **zero** direct unit tests.
- Content-dedup leans on real-data fixtures rather than pinned expected outputs.
- There are **no** idempotency / re-upload tests at all.

## Out of Scope (Phase 1)

- Unstructured/AI-extracted idempotency (Phase 2 — content-hash gate).
- A user-facing UI for browsing version history (data captured now; surfacing later).
- Changing the existing content/fuzzy/LLM dedup heuristics.

## Validation Plan (post-build, in order)

1. **The extract** — `HealthSummary_May_29_2026` IHE XDM (structured / CDA).
2. **A doc with medical records** — clinical note PDF (unstructured; exercises Phase 2 path
   once built).
3. **Non-standard records** — transcript, phone notes (unstructured; Phase 2).
