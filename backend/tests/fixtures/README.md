# Test Fixtures

## User-Provided Files (gitignored — may contain real PHI)

Place your real health records here for testing:

1. **FHIR JSON export**: `user_provided_fhir.json`
2. **Epic EHI Tables export directory**: `epic_export/`

These files are gitignored and will never be committed.

## Synthetic Fixtures (committed — fake data)

- `sample_fhir_bundle.json` — Synthetic FHIR R4 bundle with Patient, Condition, Observation
- `sample_epic_tsv/` — Synthetic Epic EHI Tables TSV files (PATIENT, PROBLEM_LIST, ORDER_RESULTS, MEDICATIONS, ENCOUNTERS, ALLERGIES)

Tests will use user-provided files when available, falling back to synthetic fixtures.
