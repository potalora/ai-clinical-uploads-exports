"""Stable source-identity extraction for incremental (idempotent) ingestion.

Given a parsed record dict, derive a `(source_system, external_id)` pair that
uniquely and stably identifies the upstream record, so that a re-uploaded
cumulative extract can be matched against records already in the database.

Returns None when no stable identity can be derived; such records fall through
to the existing content/fuzzy dedup pipeline unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# CDA <id> roots that identify people/providers, not clinical acts.
CDA_NON_ACT_ROOTS = frozenset({
    "2.16.840.1.113883.4.6",  # NPI (provider)
    "2.16.840.1.113883.4.2",  # SSN-ish / person
})


@dataclass(frozen=True)
class Identity:
    """A stable upstream identity for a health record."""

    source_system: str
    external_id: str


def extract_identity(record: dict[str, Any]) -> Identity | None:
    """Derive a stable identity from a parsed record dict, or None."""
    try:
        # 1. Explicit fields win (Epic parser sets these from table PKs).
        ext = record.get("external_id")
        sys = record.get("source_system")
        if ext and sys:
            return Identity(source_system=str(sys), external_id=str(ext))

        source_format = record.get("source_format")
        resource = record.get("fhir_resource")
        if not isinstance(resource, dict):
            return None

        if source_format == "fhir_r4":
            return _from_fhir(resource)
        if source_format == "cda_r2":
            return _from_cda(resource)
        return None
    except Exception:  # never break ingestion on identity extraction
        logger.exception("identity extraction failed; treating as no-identity")
        return None


def epic_identity(table: str, pk_columns: list[str], row: dict[str, str]) -> Identity | None:
    """Build an Identity from an Epic TSV row's primary-key column(s)."""
    parts: list[str] = []
    for col in pk_columns:
        val = (row.get(col) or "").strip()
        if not val:
            return None
        parts.append(val)
    if not parts:
        return None
    return Identity(source_system=f"epic:{table}", external_id="|".join(parts))


def _from_fhir(resource: dict[str, Any]) -> Identity | None:
    rtype = resource.get("resourceType")
    if not rtype:
        return None
    identifiers = resource.get("identifier")
    if isinstance(identifiers, list) and identifiers:
        first = identifiers[0]
        value = first.get("value")
        system = first.get("system") or "fhir"
        if value:
            return Identity(source_system=str(system), external_id=f"{rtype}/{value}")
    rid = resource.get("id")
    if rid:
        return Identity(source_system="fhir", external_id=f"{rtype}/{rid}")
    return None


def _strip_oid(system: str | None) -> str:
    """Normalize a FHIR system to a bare OID for root comparison."""
    s = system or ""
    return s[len("urn:oid:"):] if s.startswith("urn:oid:") else s


def _from_cda(resource: dict[str, Any]) -> Identity | None:
    rtype = resource.get("resourceType")
    if not rtype:
        return None
    identifiers = resource.get("identifier")
    if isinstance(identifiers, list):
        for ident in identifiers:
            if not isinstance(ident, dict):
                continue
            system = ident.get("system")
            value = ident.get("value")
            if not value or _strip_oid(system) in CDA_NON_ACT_ROOTS:
                continue
            return Identity(source_system=str(system or "cda"), external_id=f"{rtype}/{value}")
    rid = resource.get("id")
    # Ignore renderer UUIDs and non-string ids (e.g. {"nullFlavor": "UNK"}).
    if isinstance(rid, str) and rid and "-" not in rid:
        return Identity(source_system="cda", external_id=f"{rtype}/{rid}")
    return None
