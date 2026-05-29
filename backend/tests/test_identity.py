from __future__ import annotations

from pathlib import Path

import pytest

# Real extract location (gitignored). Skip when absent.
_XDM_DOC = Path(__file__).resolve().parents[2] / (
    "HealthSummary_May_29_2026/IHE_XDM/Pedro1/DOC0001.XML"
)


@pytest.mark.fidelity
@pytest.mark.skipif(not _XDM_DOC.exists(), reason="real XDM extract not present")
def test_cda_renderer_preserves_source_id():
    """Probe: does CcdaRenderer carry the CDA <id> into resource.id/identifier?

    This is a discovery test. We assert that AT LEAST ONE clinical resource
    produced from the real CDA carries either a non-UUID `id` or a populated
    `identifier`. If this fails, identity.py CDA branch must parse <id> directly.
    """
    from fhir_converter.renderers import CcdaRenderer

    renderer = CcdaRenderer()
    bundle = renderer.render_to_fhir("CCD", _XDM_DOC.read_text(encoding="utf-8"))

    has_identifier = False
    has_meaningful_id = False
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") in {"Bundle", "Composition", "Patient"}:
            continue
        if res.get("identifier"):
            has_identifier = True
        rid = res.get("id", "")
        # A bare UUID id is renderer-generated, not source-stable.
        if rid and "-" not in rid:
            has_meaningful_id = True

    assert has_identifier or has_meaningful_id, (
        "CcdaRenderer dropped source <id>; identity.py CDA branch needs a "
        "direct-XML fallback (parse act <id root extension>)."
    )


from app.services.ingestion.identity import Identity, extract_identity


def test_explicit_fields_take_precedence():
    rec = {
        "source_format": "epic_ehi",
        "external_id": "ORDER_MED_123",
        "source_system": "epic:ORDER_MED",
        "fhir_resource": {"resourceType": "MedicationRequest", "id": "ignored"},
    }
    ident = extract_identity(rec)
    assert ident == Identity(source_system="epic:ORDER_MED", external_id="ORDER_MED_123")


def test_fhir_resource_id():
    rec = {
        "source_format": "fhir_r4",
        "fhir_resource": {"resourceType": "Condition", "id": "cond-1"},
    }
    ident = extract_identity(rec)
    assert ident == Identity(source_system="fhir", external_id="Condition/cond-1")


def test_fhir_identifier_preferred_over_id():
    rec = {
        "source_format": "fhir_r4",
        "fhir_resource": {
            "resourceType": "Condition",
            "id": "gen-uuid",
            "identifier": [{"system": "urn:epic", "value": "PROB-9"}],
        },
    }
    ident = extract_identity(rec)
    assert ident == Identity(source_system="urn:epic", external_id="Condition/PROB-9")


def test_fhir_no_id_returns_none():
    rec = {"source_format": "fhir_r4", "fhir_resource": {"resourceType": "Condition"}}
    assert extract_identity(rec) is None


def test_unknown_format_returns_none():
    rec = {"source_format": "mystery", "fhir_resource": {"resourceType": "X", "id": "1"}}
    assert extract_identity(rec) is None


def test_extraction_never_raises_on_bad_input():
    assert extract_identity({"source_format": "fhir_r4"}) is None
    assert extract_identity({"source_format": "fhir_r4", "fhir_resource": None}) is None
