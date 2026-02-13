from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.services.extraction.entity_extractor import ExtractedEntity

logger = logging.getLogger(__name__)

# Map LangExtract entity classes to FHIR record types
ENTITY_TO_RECORD_TYPE: dict[str, tuple[str, str] | None] = {
    "medication": ("medication", "MedicationRequest"),
    "condition": ("condition", "Condition"),
    "lab_result": ("observation", "Observation"),
    "vital": ("observation", "Observation"),
    "procedure": ("procedure", "Procedure"),
    "allergy": ("allergy", "AllergyIntolerance"),
    # Non-storable types
    "provider": None,
    "dosage": None,
    "route": None,
    "frequency": None,
    "duration": None,
    "date": None,
}


def entity_to_health_record_dict(
    entity: ExtractedEntity,
    user_id: UUID,
    patient_id: UUID,
    source_file_id: UUID | None = None,
) -> dict | None:
    """Convert an extracted entity to a dict suitable for creating a HealthRecord.

    Returns None for entity types that should not be stored as individual records
    (e.g., dosage, route, frequency — these are attributes of medications).
    """
    mapping = ENTITY_TO_RECORD_TYPE.get(entity.entity_class)
    if mapping is None:
        return None

    record_type, fhir_resource_type = mapping
    fhir_resource = _build_fhir_resource(entity, fhir_resource_type)
    display_text = _build_display_text(entity)

    return {
        "id": uuid4(),
        "patient_id": patient_id,
        "user_id": user_id,
        "record_type": record_type,
        "fhir_resource_type": fhir_resource_type,
        "fhir_resource": fhir_resource,
        "source_format": "ai_extracted",
        "source_file_id": source_file_id,
        "effective_date": datetime.now(timezone.utc),
        "status": entity.attributes.get("status", "unknown"),
        "category": [record_type],
        "code_display": entity.text,
        "display_text": display_text,
        "is_duplicate": False,
        "confidence_score": entity.confidence,
        "ai_extracted": True,
    }


def _build_fhir_resource(entity: ExtractedEntity, resource_type: str) -> dict:
    """Build a minimal FHIR resource JSON from an extracted entity."""
    resource: dict = {"resourceType": resource_type}
    attrs = entity.attributes

    if resource_type == "MedicationRequest":
        resource["status"] = "active"
        resource["intent"] = "order"
        resource["medicationCodeableConcept"] = {"text": entity.text}
        # Attach grouped dosage info if available
        dosage_parts = []
        if attrs.get("medication_group"):
            dose_text = entity.text
            if "value" in attrs and "unit" in attrs:
                dose_text = f"{entity.text} {attrs['value']}{attrs['unit']}"
            dosage_parts.append(dose_text)
        if dosage_parts:
            resource["dosageInstruction"] = [{"text": " ".join(dosage_parts)}]

    elif resource_type == "Condition":
        status = attrs.get("status", "active")
        resource["clinicalStatus"] = {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": status}]
        }
        resource["code"] = {"text": entity.text}

    elif resource_type == "Observation":
        resource["status"] = "final"
        if entity.entity_class == "lab_result":
            resource["category"] = [{"coding": [{"code": "laboratory"}]}]
            resource["code"] = {"text": attrs.get("test", entity.text)}
            if "value" in attrs:
                try:
                    resource["valueQuantity"] = {
                        "value": float(attrs["value"]),
                        "unit": attrs.get("unit", ""),
                    }
                except (ValueError, TypeError):
                    resource["valueString"] = attrs.get("value", entity.text)
            if "ref_low" in attrs or "ref_high" in attrs:
                ref_range: dict = {}
                if "ref_low" in attrs:
                    try:
                        ref_range["low"] = {"value": float(attrs["ref_low"])}
                    except (ValueError, TypeError):
                        pass
                if "ref_high" in attrs:
                    try:
                        ref_range["high"] = {"value": float(attrs["ref_high"])}
                    except (ValueError, TypeError):
                        pass
                if ref_range:
                    resource["referenceRange"] = [ref_range]
        else:
            # vital
            resource["category"] = [{"coding": [{"code": "vital-signs"}]}]
            resource["code"] = {"text": attrs.get("type", entity.text)}
            resource["valueString"] = entity.text

    elif resource_type == "Procedure":
        resource["status"] = "completed"
        resource["code"] = {"text": entity.text}

    elif resource_type == "AllergyIntolerance":
        resource["clinicalStatus"] = {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]
        }
        resource["code"] = {"text": entity.text}
        if "reaction" in attrs:
            resource["reaction"] = [{"manifestation": [{"text": attrs["reaction"]}]}]

    # Store extraction metadata
    resource["_extraction_metadata"] = {
        "entity_class": entity.entity_class,
        "original_text": entity.text,
        "attributes": attrs,
        "start_pos": entity.start_pos,
        "end_pos": entity.end_pos,
        "confidence": entity.confidence,
    }

    return resource


def _build_display_text(entity: ExtractedEntity) -> str:
    """Build a human-readable display text for a given entity."""
    attrs = entity.attributes
    cls = entity.entity_class

    if cls == "medication":
        parts = [entity.text]
        if "value" in attrs and "unit" in attrs:
            parts.append(f"{attrs['value']}{attrs['unit']}")
        return " ".join(parts)

    if cls == "condition":
        status = attrs.get("status", "")
        if status:
            return f"{entity.text} ({status})"
        return entity.text

    if cls == "lab_result":
        parts = [attrs.get("test", entity.text)]
        if "value" in attrs:
            parts.append(f": {attrs['value']}{attrs.get('unit', '')}")
        return "".join(parts)

    if cls == "vital":
        return entity.text

    if cls == "procedure":
        date = attrs.get("date", "")
        if date:
            return f"{entity.text} ({date})"
        return entity.text

    if cls == "allergy":
        reaction = attrs.get("reaction", "")
        if reaction:
            return f"{entity.text} — {reaction}"
        return entity.text

    return entity.text
