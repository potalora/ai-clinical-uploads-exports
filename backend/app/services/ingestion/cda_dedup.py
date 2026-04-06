from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CdaDedupStats:
    """Statistics from cross-document deduplication."""

    total_parsed: int = 0
    unique_records: int = 0
    duplicates_collapsed: int = 0
    records_per_document: dict[str, int] = field(default_factory=dict)


def _build_dedup_key(record: dict) -> tuple[str, str, str, str]:
    """Build a dedup key from record fields.

    Args:
        record: Parsed record dict with record_type, code_value,
            code_system, and effective_date.

    Returns:
        Tuple of (record_type, code_value, code_system, effective_date_iso).
    """
    effective_date = record.get("effective_date")
    if isinstance(effective_date, datetime):
        date_str = effective_date.isoformat()
    else:
        date_str = str(effective_date)

    return (
        record.get("record_type", ""),
        record.get("code_value", ""),
        record.get("code_system", ""),
        date_str,
    )


def deduplicate_across_documents(
    records: list[dict],
) -> tuple[list[dict], CdaDedupStats]:
    """Collapse identical records across multiple CDA documents.

    Pure in-memory deduplication that runs after CDA parsing and before
    DB insertion. Records with the same (record_type, code_value,
    code_system, effective_date) are collapsed, with source documents
    tracked in provenance.

    Args:
        records: List of parsed record dicts from CDA parser.

    Returns:
        Tuple of (unique records list, dedup statistics).
    """
    stats = CdaDedupStats()
    seen: dict[tuple[str, str, str, str], dict] = {}
    unique_records: list[dict] = []

    for record in records:
        stats.total_parsed += 1

        # Track per-document counts
        source_doc = (
            record.get("fhir_resource", {})
            .get("_extraction_metadata", {})
            .get("source_document", "unknown")
        )
        stats.records_per_document[source_doc] = (
            stats.records_per_document.get(source_doc, 0) + 1
        )

        key = _build_dedup_key(record)

        if key in seen:
            # Duplicate — append source document to existing record's provenance
            existing = seen[key]
            metadata = existing["fhir_resource"].setdefault(
                "_extraction_metadata", {}
            )
            source_docs = metadata.setdefault("source_documents", [])
            if source_doc not in source_docs:
                source_docs.append(source_doc)
            stats.duplicates_collapsed += 1
            logger.debug(
                "Collapsed duplicate record: type=%s code=%s from %s",
                record.get("record_type"),
                record.get("code_value"),
                source_doc,
            )
        else:
            # New record — initialize source_documents list
            metadata = record.get("fhir_resource", {}).setdefault(
                "_extraction_metadata", {}
            )
            metadata.setdefault("source_documents", [source_doc])
            seen[key] = record
            unique_records.append(record)

    stats.unique_records = len(unique_records)

    if stats.duplicates_collapsed > 0:
        logger.info(
            "Cross-document dedup: %d parsed, %d unique, %d collapsed",
            stats.total_parsed,
            stats.unique_records,
            stats.duplicates_collapsed,
        )

    return unique_records, stats
