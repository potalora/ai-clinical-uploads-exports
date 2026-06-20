"""WS-D — FHIR structural validation (log-only, fail-open, non-latching).

Covers the four behaviors the design requires:
  1. A malformed resource (missing required field) returns a non-empty problem
     list, is logged in ``log`` mode, but is still returned/ingested.
  2. A well-formed resource returns ``[]`` and logs nothing.
  3. A representative *partial AI* resource produces no false-failure noise
     (the lenient required-field posture drops patient-binding refs the app
     tracks as columns, and strips the app-internal ``_extraction_metadata``).
  4. Validation raising internally is swallowed (fail-open) — ingestion proceeds.
"""

from __future__ import annotations

import logging

import pytest

from app.config import settings
from app.services.ingestion import fhir_validation as fv
from app.services.ingestion.fhir_parser import map_fhir_resource
from app.services.ingestion.fhir_validation import (
    validate_and_log_fhir,
    validate_fhir_structure,
)

# ---------------------------------------------------------------------------
# Sample resources
# ---------------------------------------------------------------------------


def _valid_condition() -> dict:
    return {
        "resourceType": "Condition",
        "subject": {"reference": "Patient/123"},
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "code": {"text": "Type 2 diabetes mellitus"},
    }


def _valid_observation() -> dict:
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {"text": "Glucose"},
        "subject": {"reference": "Patient/1"},
    }


def _partial_ai_condition() -> dict:
    """Exactly the shape ``entity_to_fhir._build_fhir_resource`` produces:

    no ``subject`` (patient is a DB column, not embedded) and a non-FHIR
    ``_extraction_metadata`` block.
    """
    return {
        "resourceType": "Condition",
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "code": {"text": "Hypertension"},
        "_extraction_metadata": {
            "entity_class": "condition",
            "original_text": "Hypertension",
            "attributes": {},
            "confidence": 0.8,
        },
    }


def _partial_ai_lab() -> dict:
    return {
        "resourceType": "Observation",
        "status": "final",
        "category": [{"coding": [{"code": "laboratory"}]}],
        "code": {"text": "Vitamin D"},
        "valueQuantity": {"value": 17.0, "unit": "ng/mL"},
        "_extraction_metadata": {"entity_class": "lab_result"},
    }


@pytest.fixture(autouse=True)
def _log_mode(monkeypatch):
    """Default every test to ``log`` mode unless it overrides."""
    monkeypatch.setattr(settings, "fhir_validation", "log")


# ---------------------------------------------------------------------------
# 1. Malformed resource: reported + logged + still ingested
# ---------------------------------------------------------------------------


def test_malformed_missing_required_field_reported():
    # Observation requires ``code``; this one omits it.
    bad = {"resourceType": "Observation", "valueString": "x", "subject": {"reference": "Patient/1"}}
    problems = validate_fhir_structure(bad, "observation")
    assert problems, "missing required field should produce a problem"
    assert any("code" in p for p in problems)
    assert any("Observation" in p for p in problems)


def test_malformed_resource_logged_but_still_ingests(caplog):
    bad = {"resourceType": "Observation", "valueString": "x"}  # missing code
    with caplog.at_level(logging.WARNING):
        problems = validate_and_log_fhir(bad, "observation")
    assert problems  # non-empty
    assert any("drift" in r.message.lower() for r in caplog.records)
    # Ingestion proceeds: map_fhir_resource still returns a mapped record dict.
    rec = map_fhir_resource(bad)
    assert rec is not None
    assert rec["record_type"] == "observation"


def test_malformed_wrong_type_reported():
    bad = {
        "resourceType": "Observation",
        "status": 123,  # must be a string
        "code": {"text": "x"},
        "subject": {"reference": "Patient/1"},
    }
    problems = validate_fhir_structure(bad, "observation")
    assert any("status" in p for p in problems)


# ---------------------------------------------------------------------------
# 2. Valid resource: no problems, no logs
# ---------------------------------------------------------------------------


def test_valid_observation_no_problems():
    assert validate_fhir_structure(_valid_observation(), "observation") == []


def test_valid_condition_no_problems():
    assert validate_fhir_structure(_valid_condition(), "condition") == []


def test_valid_resource_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        problems = validate_and_log_fhir(_valid_observation(), "observation")
    assert problems == []
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# ---------------------------------------------------------------------------
# 3. Partial AI resources: no false-failure noise
# ---------------------------------------------------------------------------


def test_partial_ai_condition_no_noise():
    assert validate_fhir_structure(_partial_ai_condition(), "condition") == []


def test_partial_ai_lab_no_noise():
    assert validate_fhir_structure(_partial_ai_lab(), "observation") == []


def test_partial_ai_medication_no_noise():
    ai_med = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"text": "Metformin"},
        "_extraction_metadata": {"entity_class": "medication"},
    }
    assert validate_fhir_structure(ai_med, "medication") == []


def test_partial_ai_family_history_no_noise():
    ai_fhx = {
        "resourceType": "FamilyMemberHistory",
        "status": "completed",
        "relationship": {"coding": [{"code": "MTH", "display": "Mother"}]},
        "condition": [{"code": {"text": "Diabetes"}}],
        "_extraction_metadata": {"entity_class": "family_history"},
    }
    assert validate_fhir_structure(ai_fhx, "condition") == []


def test_partial_ai_built_resource_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        problems = validate_and_log_fhir(_partial_ai_condition(), "condition", ai_built=True)
    assert problems == []
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# ---------------------------------------------------------------------------
# Mode handling: off / strict
# ---------------------------------------------------------------------------


def test_off_mode_skips_entirely(monkeypatch, caplog):
    monkeypatch.setattr(settings, "fhir_validation", "off")
    bad = {"resourceType": "Observation"}  # missing code
    with caplog.at_level(logging.WARNING):
        problems = validate_and_log_fhir(bad, "observation")
    assert problems == []
    assert caplog.records == []


def test_strict_logs_error_for_bundle_resource(monkeypatch, caplog):
    monkeypatch.setattr(settings, "fhir_validation", "strict")
    bad = {
        "resourceType": "Observation",
        "status": 123,
        "code": {"text": "x"},
        "subject": {"reference": "Patient/1"},
    }
    with caplog.at_level(logging.WARNING):
        problems = validate_and_log_fhir(bad, "observation", ai_built=False)
    assert problems
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_strict_never_applied_to_ai_built(monkeypatch, caplog):
    """``strict`` is downgraded to a WARNING for AI-built resources (never ERROR,
    never raises, never blocks)."""
    monkeypatch.setattr(settings, "fhir_validation", "strict")
    ai_bad = {
        "resourceType": "Observation",
        "status": 123,  # real structural problem
        "code": {"text": "x"},
        "_extraction_metadata": {},
    }
    with caplog.at_level(logging.WARNING):
        problems = validate_and_log_fhir(ai_bad, "observation", ai_built=True)
    assert problems  # still reported as a drift signal
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert all(r.levelno != logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------------
# Skips: unmapped type, non-dict
# ---------------------------------------------------------------------------


def test_unmapped_resource_type_skipped():
    # ``Basic`` is a real FHIR type but not one the app builds -> skip, not fail.
    assert validate_fhir_structure({"resourceType": "Basic", "code": {"text": "x"}}, None) == []


def test_missing_resource_type_skipped():
    assert validate_fhir_structure({"code": {"text": "x"}}, None) == []


def test_non_dict_input_skipped():
    assert validate_fhir_structure(None, None) == []
    assert validate_fhir_structure("not-a-dict", None) == []
    assert validate_fhir_structure([1, 2, 3], None) == []


# ---------------------------------------------------------------------------
# 4. Fail-open, non-latching
# ---------------------------------------------------------------------------


def test_internal_exception_is_swallowed(monkeypatch):
    def boom(_resource_type):
        raise RuntimeError("model registry exploded")

    monkeypatch.setattr(fv, "_get_model", boom)
    # Both the core validator and the wrapper fail open (return []), never raise.
    assert validate_fhir_structure(_valid_observation(), "observation") == []
    assert validate_and_log_fhir(_valid_observation(), "observation") == []


def test_ingestion_proceeds_when_validation_raises(monkeypatch):
    class _Boom:
        @staticmethod
        def model_validate(_data):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(fv, "_get_model", lambda _rt: _Boom)
    # A library hiccup must never block ingestion — map_fhir_resource still maps.
    rec = map_fhir_resource(_valid_condition())
    assert rec is not None
    assert rec["record_type"] == "condition"


def test_fail_open_is_non_latching(monkeypatch):
    """A failure on one call must not disable validation for the next."""

    def boom(_resource_type):
        raise RuntimeError("transient")

    monkeypatch.setattr(fv, "_get_model", boom)
    assert validate_fhir_structure(_valid_observation(), "observation") == []
    # Remove the fault; validation must work again immediately (no latched flag).
    monkeypatch.undo()
    monkeypatch.setattr(settings, "fhir_validation", "log")
    bad = {"resourceType": "Observation", "valueString": "x"}
    assert validate_fhir_structure(bad, "observation"), "validation must recover after a transient failure"
