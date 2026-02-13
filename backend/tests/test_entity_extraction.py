from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.services.extraction.entity_extractor import ExtractedEntity
from app.services.extraction.entity_to_fhir import (
    entity_to_health_record_dict,
    _build_display_text,
)

HAS_API_KEY = bool(os.environ.get("GEMINI_API_KEY"))
USER_ID = uuid4()
PATIENT_ID = uuid4()
SOURCE_FILE_ID = uuid4()


# ---------- entity_to_fhir mapping ----------

def test_entity_to_fhir_medication():
    entity = ExtractedEntity(
        entity_class="medication",
        text="Metformin",
        attributes={"medication_group": "Metformin"},
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID, SOURCE_FILE_ID)
    assert result is not None
    assert result["record_type"] == "medication"
    assert result["fhir_resource_type"] == "MedicationRequest"
    assert result["ai_extracted"] is True
    assert result["source_format"] == "ai_extracted"
    fhir = result["fhir_resource"]
    assert fhir["resourceType"] == "MedicationRequest"
    assert fhir["medicationCodeableConcept"]["text"] == "Metformin"


def test_entity_to_fhir_condition():
    entity = ExtractedEntity(
        entity_class="condition",
        text="hypertension",
        attributes={"status": "active"},
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID)
    assert result is not None
    assert result["record_type"] == "condition"
    assert result["fhir_resource_type"] == "Condition"
    fhir = result["fhir_resource"]
    assert fhir["code"]["text"] == "hypertension"
    assert fhir["clinicalStatus"]["coding"][0]["code"] == "active"


def test_entity_to_fhir_lab_result():
    entity = ExtractedEntity(
        entity_class="lab_result",
        text="HbA1c 6.8%",
        attributes={
            "test": "HbA1c",
            "value": "6.8",
            "unit": "%",
            "ref_low": "4.0",
            "ref_high": "5.6",
        },
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID)
    assert result is not None
    assert result["record_type"] == "observation"
    fhir = result["fhir_resource"]
    assert fhir["valueQuantity"]["value"] == 6.8
    assert fhir["valueQuantity"]["unit"] == "%"
    assert fhir["referenceRange"][0]["low"]["value"] == 4.0
    assert fhir["referenceRange"][0]["high"]["value"] == 5.6


def test_entity_to_fhir_vital():
    entity = ExtractedEntity(
        entity_class="vital",
        text="BP 120/80 mmHg",
        attributes={"type": "blood_pressure"},
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID)
    assert result is not None
    assert result["record_type"] == "observation"
    fhir = result["fhir_resource"]
    assert fhir["category"][0]["coding"][0]["code"] == "vital-signs"


def test_entity_to_fhir_allergy():
    entity = ExtractedEntity(
        entity_class="allergy",
        text="Penicillin",
        attributes={"reaction": "rash"},
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID)
    assert result is not None
    assert result["record_type"] == "allergy"
    fhir = result["fhir_resource"]
    assert fhir["resourceType"] == "AllergyIntolerance"
    assert fhir["reaction"][0]["manifestation"][0]["text"] == "rash"


def test_entity_to_fhir_procedure():
    entity = ExtractedEntity(
        entity_class="procedure",
        text="Colonoscopy",
        attributes={"date": "01/2024"},
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID)
    assert result is not None
    assert result["record_type"] == "procedure"
    fhir = result["fhir_resource"]
    assert fhir["code"]["text"] == "Colonoscopy"


def test_entity_to_fhir_provider_skipped():
    entity = ExtractedEntity(
        entity_class="provider",
        text="Dr. Smith",
        attributes={"specialty": "Cardiology"},
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID)
    assert result is None


def test_entity_to_fhir_dosage_skipped():
    entity = ExtractedEntity(
        entity_class="dosage",
        text="500mg",
        attributes={},
    )
    result = entity_to_health_record_dict(entity, USER_ID, PATIENT_ID)
    assert result is None


# ---------- Display text formatting ----------

def test_display_text_medication():
    entity = ExtractedEntity(
        entity_class="medication", text="Metformin",
        attributes={"value": "500", "unit": "mg"},
    )
    assert _build_display_text(entity) == "Metformin 500mg"


def test_display_text_condition():
    entity = ExtractedEntity(
        entity_class="condition", text="Diabetes",
        attributes={"status": "active"},
    )
    assert _build_display_text(entity) == "Diabetes (active)"


def test_display_text_lab_result():
    entity = ExtractedEntity(
        entity_class="lab_result", text="HbA1c 6.8%",
        attributes={"test": "HbA1c", "value": "6.8", "unit": "%"},
    )
    assert _build_display_text(entity) == "HbA1c: 6.8%"


def test_display_text_allergy():
    entity = ExtractedEntity(
        entity_class="allergy", text="Penicillin",
        attributes={"reaction": "rash"},
    )
    assert _build_display_text(entity) == "Penicillin — rash"


def test_display_text_procedure_with_date():
    entity = ExtractedEntity(
        entity_class="procedure", text="Colonoscopy",
        attributes={"date": "01/2024"},
    )
    assert _build_display_text(entity) == "Colonoscopy (01/2024)"


# ---------- LangExtract integration (slow, requires API) ----------

@pytest.mark.slow
@pytest.mark.skipif(not HAS_API_KEY, reason="Requires GEMINI_API_KEY")
def test_extract_entities_from_clinical_text():
    """Run LangExtract on synthetic clinical text and verify entities are found."""
    from app.services.extraction.entity_extractor import extract_entities

    text = (
        "Patient takes Metformin 500mg PO BID for type 2 diabetes. "
        "HbA1c 7.2% (ref 4.0-5.6). Allergic to Penicillin (anaphylaxis). "
        "BP 130/85 mmHg. Dr. Johnson, Internal Medicine."
    )

    result = extract_entities(text, "test_clinical_note.txt", os.environ["GEMINI_API_KEY"])
    assert result.error is None
    assert len(result.entities) > 0

    entity_classes = {e.entity_class for e in result.entities}
    # Should find at least some of these
    expected = {"medication", "condition", "lab_result", "allergy"}
    found = entity_classes & expected
    assert len(found) >= 2, f"Expected >=2 clinical entity types, found: {found}"
