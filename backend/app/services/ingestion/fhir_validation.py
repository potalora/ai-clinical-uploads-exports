"""WS-D — FHIR structural validation (log-only, fail-open, non-latching).

This is the *structural* validation layer ("is this a well-formed FHIR R4B
resource — required fields, types, cardinality?"). It complements — and never
duplicates — the existing *terminology* validation in
``services/extraction/terminology.py`` ("is this a real ICD-10 / RxNorm / LOINC
code?").

Posture (mirrors the existing PHI-NER / medication-refresh design):

* **Fail-open, non-latching.** Any exception inside validation is caught and
  logged; it must NEVER block ingestion, and a transient failure must not
  permanently disable validation (no process-global "disabled" latch).
* **Log-only by default.** ``settings.fhir_validation`` is one of
  ``off`` | ``log`` | ``strict``. In ``log`` mode problems are logged at
  WARNING and the resource is still returned/ingested. ``strict`` is NEVER
  applied to AI-built (partial) resources — it is downgraded to ``log`` for
  them.
* **Lenient required-field posture.** The app intentionally builds partial
  resources: the patient is a DB column (not an embedded ``subject``/``patient``
  reference) and AI resources carry a non-FHIR ``_extraction_metadata`` block.
  Those are stripped/ignored so intentionally-partial resources don't generate
  false-failure noise. Genuine structural drift (wrong types, malformed nested
  objects, missing ``status``/``code``/``intent`` the app *does* set) is still
  reported.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from pydantic import ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

# Resource types the app actually builds: the 18 ``SUPPORTED_RESOURCE_TYPES``
# in ``fhir_parser.py`` plus the extraction outputs from
# ``entity_to_fhir._build_fhir_resource`` (notably ``FamilyMemberHistory``).
# Anything outside this set is skipped (not failed) — "if no model matches a
# built type, treat as skip, not fail".
_VALIDATED_TYPES: frozenset[str] = frozenset(
    {
        # SUPPORTED_RESOURCE_TYPES (fhir_parser.py)
        "Condition",
        "Observation",
        "MedicationRequest",
        "MedicationStatement",
        "AllergyIntolerance",
        "Procedure",
        "Encounter",
        "Immunization",
        "DiagnosticReport",
        "DocumentReference",
        "ImagingStudy",
        "ServiceRequest",
        "CarePlan",
        "Communication",
        "Appointment",
        "CareTeam",
        "ImmunizationRecommendation",
        "QuestionnaireResponse",
        # Extraction outputs (entity_to_fhir._build_fhir_resource)
        "FamilyMemberHistory",
    }
)

# App-internal keys that are NOT FHIR and would otherwise trip the model's
# extra-fields-forbidden guard. Stripped (shallow) before validation.
_APP_INTERNAL_KEYS: frozenset[str] = frozenset({"_extraction_metadata"})

# Required fields the app intentionally omits because the relationship is
# tracked elsewhere (patient is a ``health_records.patient_id`` column, not an
# embedded reference). A ``missing`` error for one of these top-level fields is
# expected, not drift, so it is dropped.
_LENIENT_MISSING_FIELDS: frozenset[str] = frozenset({"subject", "patient"})

# Cache of successfully-resolved R4B model classes. Only *successes* are cached
# so an import hiccup is retried on the next call (non-latching).
_MODEL_CACHE: dict[str, Any] = {}


def _get_model(resource_type: str) -> Any | None:
    """Resolve a FHIR ``resourceType`` to its ``fhir.resources`` R4B model class.

    Returns ``None`` (skip, don't fail) when the type isn't one we validate or
    the model can't be imported. Never raises.
    """
    if resource_type not in _VALIDATED_TYPES:
        return None
    cached = _MODEL_CACHE.get(resource_type)
    if cached is not None:
        return cached
    module = importlib.import_module(f"fhir.resources.R4B.{resource_type.lower()}")
    model = getattr(module, resource_type)
    _MODEL_CACHE[resource_type] = model
    return model


def _format_problems(resource_type: str, exc: ValidationError) -> list[str]:
    """Render a pydantic ``ValidationError`` into human-readable strings,
    dropping the lenient (intentionally-omitted) required-field errors."""
    problems: list[str] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        err_type = err.get("type", "")
        # Drop intentional patient-binding omissions (column-tracked).
        if err_type == "missing" and loc and str(loc[0]) in _LENIENT_MISSING_FIELDS:
            continue
        loc_path = ".".join(str(part) for part in loc) or "(root)"
        msg = err.get("msg", "invalid")
        problems.append(f"{resource_type}.{loc_path}: {msg} [{err_type}]")
    return problems


def validate_fhir_structure(resource: Any, record_type: str | None = None) -> list[str]:
    """Validate a FHIR resource's *structure* against its R4B model.

    Returns a list of human-readable structural problems; an empty list means
    valid (or intentionally skipped — non-dict input, missing/unknown
    ``resourceType``, or a partial resource whose only issues are leniently
    allowed). Never raises: any unexpected internal error is swallowed
    (fail-open) and reported as "no problems" so ingestion always proceeds.

    ``record_type`` is the app's record type (e.g. ``"observation"``); it is
    informational — model selection is driven by ``resourceType``.
    """
    try:
        if not isinstance(resource, dict):
            return []
        resource_type = resource.get("resourceType")
        if not resource_type:
            return []
        model = _get_model(resource_type)
        if model is None:
            return []
        # Strip app-internal, non-FHIR keys so they don't trip extra-field guards.
        cleaned = {k: v for k, v in resource.items() if k not in _APP_INTERNAL_KEYS}
        try:
            model.model_validate(cleaned)
        except ValidationError as exc:
            return _format_problems(resource_type, exc)
        return []
    except Exception:
        # Fail-open, non-latching: a library/validation hiccup must never block
        # ingestion, and we keep no "disabled" flag so the next call retries.
        logger.debug("FHIR structural validation crashed; failing open", exc_info=True)
        return []


def validate_and_log_fhir(
    resource: Any, record_type: str | None = None, *, ai_built: bool = False
) -> list[str]:
    """Thin wrapper that honors ``settings.fhir_validation`` and logs problems.

    * ``off``  — skip entirely (no validation, no log).
    * ``log``  — validate; log any problems at WARNING. (default)
    * ``strict`` — like ``log`` but log at ERROR for bundle (non-AI) resources;
      for AI-built resources it is downgraded to WARNING ("strict is never
      applied to AI resources").

    Always returns the problem list (possibly empty) and NEVER raises or blocks
    — the resource is always still ingested. Production call sites use it purely
    for its logging side-effect.
    """
    mode = getattr(settings, "fhir_validation", "log")
    if mode == "off":
        return []

    problems = validate_fhir_structure(resource, record_type)
    if not problems:
        return []

    resource_type = resource.get("resourceType", "?") if isinstance(resource, dict) else "?"
    context = f"resourceType={resource_type} record_type={record_type} ai_built={ai_built}"
    detail = "; ".join(problems)

    # ``strict`` is never applied to AI-built resources -> downgrade severity.
    if mode == "strict" and not ai_built:
        logger.error("FHIR structural drift (strict): %s | %s", context, detail)
    else:
        logger.warning("FHIR structural drift: %s | %s", context, detail)

    return problems
