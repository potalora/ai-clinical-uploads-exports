"""WS-E smoke test: Synthea-generated FHIR bundles ingest through fhir_parser.

Skips when no Synthea fixtures are present (generate via
``backend/scripts/generate_synthea_fixtures.py``) — mirroring the fidelity-fixture
pattern, so CI without the (gitignored, large) corpus stays green.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ingestion.fhir_parser import build_reference_name_map, map_fhir_resource

SYNTHEA_FHIR_DIR = Path(__file__).parent / "fixtures" / "synthea" / "fhir"


def _smallest_patient_bundle() -> Path | None:
    if not SYNTHEA_FHIR_DIR.is_dir():
        return None
    bundles = [
        p
        for p in SYNTHEA_FHIR_DIR.glob("*.json")
        # Synthea org/practitioner bundles are not patient records.
        if not p.name.startswith(("hospitalInformation", "practitionerInformation"))
    ]
    if not bundles:
        return None
    return min(bundles, key=lambda p: p.stat().st_size)


def test_synthea_bundle_maps_to_health_records():
    bundle_path = _smallest_patient_bundle()
    if bundle_path is None:
        pytest.skip(
            "No Synthea fixtures — run backend/scripts/generate_synthea_fixtures.py"
        )

    data = json.loads(bundle_path.read_text())
    entries = [
        e["resource"]
        for e in data.get("entry", [])
        if isinstance(e, dict) and isinstance(e.get("resource"), dict)
    ]
    assert entries, "bundle had no resource entries"

    ref_map = build_reference_name_map(entries)
    mapped = [map_fhir_resource(r, ref_map) for r in entries]
    records = [m for m in mapped if m]

    # A real Synthea lifetime yields many mappable records...
    assert len(records) > 20, f"expected >20 mapped records, got {len(records)}"
    # ...spanning the core clinical types the parser supports.
    types = {m["record_type"] for m in records}
    assert {"condition", "observation"} & types, f"expected clinical types, got {sorted(types)}"
    # Every mapped record carries the fields the inserter needs.
    for m in records:
        assert m["record_type"]
        assert m["fhir_resource_type"]
        assert m["fhir_resource"]
