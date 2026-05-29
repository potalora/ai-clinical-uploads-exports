# TDD-Gap Audit — Ingestion & Dedup Pipeline

**Date:** 2026-05-29  
**Scope:** `app/services/ingestion/` (bulk inserter, idempotent inserter, coordinator, Epic/FHIR/CDA parsers) and `app/services/dedup/`  
**Context:** Gaps surfaced during the idempotent incremental ingestion build (Phase 15).

---

## Gaps Found and Their Status

### 1. `bulk_inserter` had no direct tests

**Gap:** `bulk_insert_records(db, records) -> int` in `app/services/ingestion/bulk_inserter.py` was the fundamental write primitive for structured ingestion — every FHIR, Epic, and CDA record flows through it — yet it had zero dedicated tests. It was only exercised indirectly through higher-level pipeline integration tests.

**Risk:** A regression in argument handling (e.g., a missing required field, a wrong column name, or a silent truncation) would surface only as a cascade failure in an integration test, making root-cause analysis slower and less precise.

**Status:** CLOSED. Added `tests/test_bulk_inserter.py` (2 tests):
- `test_bulk_insert_empty_returns_zero` — verifies early-exit contract for an empty batch.
- `test_bulk_insert_count_and_persistence` — inserts 3 records, commits, and asserts both the return value and the DB row count against a real test database.

---

### 2. No idempotency or re-upload tests existed at all

**Gap:** The pipeline had no tests covering what happens when the same file (or overlapping records) is uploaded more than once. The prior `bulk_insert_records` simply appended rows unconditionally, so repeated uploads silently multiplied records in the database without any test catching it.

**Risk:** Silent data corruption. Users re-uploading an updated export (a common real-world action) would accumulate duplicate rows for every re-upload with no visibility into the duplication.

**Status:** CLOSED. Three new test files cover this end-to-end:
- `tests/test_idempotent_inserter.py` (12 tests) — unit and DB-level tests for `plan_batch` and `idempotent_insert_records`, including within-batch version/stats edge cases.
- `tests/test_incremental_ingestion.py` — convergence test: repeated ingestion of the same batch stabilises at a fixed record count.
- `tests/fidelity/test_incremental_fidelity.py` — real-data fidelity test using April → May Epic extract pairs (skipped in CI when fixtures are absent).

---

### 3. A real bug was caught only by a DB-level test

**Gap:** The `update_pending` branch of the within-batch deduplication logic (handling two records with the same identity in a single batch) updated the in-memory `BatchPlan` entry but did not increment `version` on the row that was subsequently inserted. This produced contradictory stats: `inserted=0` while a row was persisted, and `inserted != len(inserted_records)`.

The pure-logic tests (`test_within_batch_duplicate_changed_second_is_update_of_first`) passed because they only inspected the plan object, not the DB state. The bug was invisible until `test_within_batch_update_pending_db_level` checked the committed row's `version` field and the invariant `inserted == len(inserted_records)`.

**Risk:** Any DB-effecting branch that is only tested at the logic level will pass even when its DB effect is wrong. The pattern "assert what was planned" is insufficient; you must also "assert what was committed."

**Lesson:** For any code path whose correctness depends on a database side-effect, write at least one test that commits and queries the persisted state. Pure-logic tests are a necessary but not sufficient gate.

**Status:** CLOSED. Bug fixed; `test_within_batch_update_pending_db_level` added as a regression guard.

---

### 4. PK column references were wrong for 6 of 14 Epic mappers

**Gap:** Six Epic mapper classes referenced primary-key column names that did not match the actual EHI Tables export headers. The discrepancies were undetectable from the column-spec documentation alone and only became visible when running fidelity tests against a real export.

**Risk:** Silent row drops. If the gate column (PK) is absent, a mapper skips the row rather than erroring, so the wrong column name produces quietly incomplete ingestion with no test failure.

**Lesson:** Do not derive column-name assumptions from API docs or sample files alone. Validate against real export headers as part of the fidelity test suite. The `gate_columns` list in each `TableSpec` must enumerate all fallback columns so the fidelity tests can clear them to exercise the skip path.

**Status:** CLOSED. All 6 mappers corrected; `tests/fidelity/test_epic_fidelity.py` guards against regression.

---

### 5. Backfill over real dev DB surfaced ~6,129 pre-existing duplicate records

**Gap:** Running the idempotency backfill script against the development database revealed approximately 6,129 rows whose derived identity (source format + resource type + resource `id`) collided for the same user. These records accumulated silently over months of testing because the prior pipeline had no idempotency layer.

The backfill script itself also exposed a secondary gap: the pagination used `ORDER BY created_at` without a tiebreaker, producing unstable page boundaries that caused some rows to be processed twice and others to be skipped.

**Risk (duplicate accumulation):** The deduplication pipeline operates on record pairs and has a quadratic cost for large candidate sets. Silent accumulation of duplicates degrades dedup performance and inflates record counts.

**Risk (unstable pagination):** Any backfill or batch-processing query ordered by a non-unique column can produce incorrect results on large datasets even without explicit bugs in logic.

**Status:** CLOSED for new uploads (idempotency gate prevents new accumulation). The unstable-pagination bug in the backfill script was fixed by adding `id` as a tiebreaker. Pre-existing duplicates in the dev DB were resolved by the backfill.

---

### 6. CDA idempotency is partial (documented limitation)

**Gap:** The CDA-to-FHIR renderer (`python-fhir-converter`) omits `resource.identifier` for `AllergyIntolerance` and `DocumentReference` resource types in the real extract. Without a stable identifier, the identity gate cannot derive a `(source, resource_type/id)` key, so those records fall through to unconditional insert on every re-upload.

**Measured impact:** Approximately 1.6% of a re-ingested real extract re-inserts rather than deduplicates via the identity gate. The existing content-dedup pipeline (`services/dedup/`) can catch these pairs in a subsequent dedup scan, but they still appear as separate rows initially.

**Status:** DOCUMENTED LIMITATION. The identity gate handles this gracefully (records without an id fall through to insert, consistent with the `no_identity_is_insert_fallthrough` test). Candidate future work: a raw-XML `<id root="...">` fallback extractor for resource types where the converter omits `identifier` (Phase 1.5 candidate).

---

### 7. Content-dedup fidelity relies on real-data fixtures (pre-existing gap)

**Gap:** The cross-document and content dedup tests in `tests/fidelity/test_cda_fidelity.py` assert that dedup reduces record count but do not pin the expected reduction to a specific number. This means the test passes as long as dedup reduces something, but would not catch a regression that reduces dedup effectiveness by half.

**Risk (low):** A change that partially breaks dedup detection would still pass the fidelity gate.

**Status:** REMAINING. Pinning exact expected counts requires stable fixture data (the real XDM extract). Acceptable as-is for now; address when the fixture set is locked down.

---

## Summary Table

| # | Gap | Risk | Status |
|---|-----|------|--------|
| 1 | `bulk_inserter` no direct tests | Regression invisible until integration failure | CLOSED |
| 2 | No idempotency / re-upload tests | Silent duplicate accumulation untested | CLOSED |
| 3 | DB-effecting branch tested only at logic level | Bug passed pure-logic tests, broke at DB level | CLOSED |
| 4 | Wrong PK column refs in 6 Epic mappers | Silent row drops on real export | CLOSED |
| 5 | ~6 k pre-existing duplicates + unstable pagination | Dedup cost inflation; incorrect batch processing | CLOSED |
| 6 | CDA idempotency partial (missing identifier) | ~1.6% re-insert on CDA re-upload | DOCUMENTED LIMITATION |
| 7 | Content-dedup fidelity unpinned | Partial dedup regressions not caught | REMAINING |

---

## Recommended Follow-ups

1. **CDA identifier fallback** (Phase 1.5): Add a raw-XML `<id root="...">` extractor in `cda_parser.py` for `AllergyIntolerance` and `DocumentReference` to close the partial idempotency gap.
2. **Pin dedup fidelity counts**: Once the XDM test fixture is locked, replace the "count > 0" assertion with an exact expected reduction count.
3. **Add `inserted == len(inserted_records)` invariant assertion** to any future test that calls `idempotent_insert_records` — make it a one-line helper to lower the barrier.
4. **Audit other write primitives** (e.g., `bulk_insert_provenance`, any direct `db.add_all` calls outside `bulk_inserter.py`) for missing direct tests using the same DB-level pattern.
