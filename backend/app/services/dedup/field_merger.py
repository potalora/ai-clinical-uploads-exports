from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone

from app.services.ingestion.fhir_parser import build_display_text

logger = logging.getLogger(__name__)

# Fields that should never be overwritten during merge
PROTECTED_FIELDS = {"resourceType", "_extraction_metadata", "id", "meta"}


def apply_field_update(
    primary,
    secondary,
    field_overrides: list[str] | None = None,
) -> dict:
    """Apply field-level updates from secondary record to primary.

    If field_overrides is None, all changed fields are applied.
    If field_overrides is a list of field names, only those fields are applied.

    Returns a dict with:
    - updated_resource: The new FHIR resource for the primary record
    - display_text: Regenerated display text
    - merge_metadata: Provenance metadata including previous values
    """
    old_resource = copy.deepcopy(primary.fhir_resource or {})
    new_resource = copy.deepcopy(old_resource)
    secondary_resource = secondary.fhir_resource or {}

    # Determine which fields differ
    all_keys = set(old_resource.keys()) | set(secondary_resource.keys())
    changed_fields = []
    for key in all_keys:
        if key in PROTECTED_FIELDS:
            continue
        if old_resource.get(key) != secondary_resource.get(key):
            changed_fields.append(key)

    # Determine which fields to update
    if field_overrides is not None:
        fields_to_update = [f for f in field_overrides if f in changed_fields]
    else:
        fields_to_update = changed_fields

    fields_kept = [f for f in changed_fields if f not in fields_to_update]

    # Build previous values for undo support
    previous_values = {}
    for field in fields_to_update:
        if field in old_resource:
            previous_values[field] = copy.deepcopy(old_resource[field])
        else:
            previous_values[field] = None

    # Apply updates
    for field in fields_to_update:
        if field in secondary_resource:
            new_resource[field] = copy.deepcopy(secondary_resource[field])
        else:
            new_resource.pop(field, None)

    # Regenerate display text
    resource_type = new_resource.get("resourceType", primary.fhir_resource_type)
    display_text = build_display_text(new_resource, resource_type)

    merge_metadata = {
        "merged_from": str(secondary.id),
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "merge_type": "update",
        "fields_updated": fields_to_update,
        "fields_kept": fields_kept,
        "previous_values": previous_values,
    }

    return {
        "updated_resource": new_resource,
        "display_text": display_text,
        "merge_metadata": merge_metadata,
    }


def revert_field_update(record) -> None:
    """Revert a field-level merge using previous_values from merge_metadata.

    Modifies the record in place.
    """
    metadata = record.merge_metadata
    if not metadata or not metadata.get("previous_values"):
        return

    resource = record.fhir_resource or {}
    for field, old_value in metadata["previous_values"].items():
        if old_value is None:
            resource.pop(field, None)
        else:
            resource[field] = copy.deepcopy(old_value)

    record.fhir_resource = resource
    record.merge_metadata = None
