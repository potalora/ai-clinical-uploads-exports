from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion.bulk_inserter import bulk_insert_records
from app.services.ingestion.epic_mappers.base import EpicMapper
from app.services.ingestion.epic_mappers.documents import DocInformationMapper
from app.services.ingestion.epic_mappers.encounters import PatEncMapper
from app.services.ingestion.epic_mappers.medications import OrderMedMapper
from app.services.ingestion.epic_mappers.problems import MedicalHxMapper, ProblemListMapper
from app.services.ingestion.epic_mappers.results import OrderResultsMapper
from app.services.ingestion.fhir_parser import map_fhir_resource

logger = logging.getLogger(__name__)

EPIC_TABLE_MAPPERS: dict[str, EpicMapper] = {
    "PROBLEM_LIST": ProblemListMapper(),
    "PROBLEM_LIST_ALL": ProblemListMapper(),
    "MEDICAL_HX": MedicalHxMapper(),
    "ORDER_MED": OrderMedMapper(),
    "ORDER_RESULTS": OrderResultsMapper(),
    "PAT_ENC": PatEncMapper(),
    "DOC_INFORMATION": DocInformationMapper(),
}

RECORD_TYPE_MAP = {
    "Condition": "condition",
    "MedicationRequest": "medication",
    "Observation": "observation",
    "Encounter": "encounter",
    "DocumentReference": "document",
    "Immunization": "immunization",
    "Procedure": "procedure",
    "AllergyIntolerance": "allergy",
}


async def parse_epic_export(
    export_dir: Path,
    user_id: UUID,
    patient_id: UUID,
    source_file_id: UUID | None,
    db: AsyncSession,
    batch_size: int = 100,
    progress_callback: Any = None,
) -> dict:
    """Process an Epic EHI Tables export directory.

    Files are processed one at a time, rows streamed row-by-row.
    """
    tsv_files = sorted(export_dir.glob("*.tsv"))
    total_files = len(tsv_files)
    stats = {
        "total_files": total_files,
        "files_processed": 0,
        "records_inserted": 0,
        "records_skipped": 0,
        "errors": [],
    }

    for file_idx, tsv_path in enumerate(tsv_files):
        table_name = tsv_path.stem.upper()
        mapper = EPIC_TABLE_MAPPERS.get(table_name)
        if not mapper:
            stats["records_skipped"] += 1
            continue

        logger.info("Processing Epic table: %s (%d/%d)", table_name, file_idx + 1, total_files)
        batch = []
        row_count = 0

        try:
            with open(tsv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row_idx, row in enumerate(reader):
                    try:
                        fhir_resource = mapper.to_fhir(row)
                        if not fhir_resource:
                            continue

                        resource_type = fhir_resource.get("resourceType", "Unknown")
                        record_type = RECORD_TYPE_MAP.get(resource_type, resource_type.lower())

                        from app.services.ingestion.fhir_parser import (
                            extract_categories,
                            extract_coding,
                            extract_effective_date,
                            extract_effective_date_end,
                            extract_status,
                        )

                        code_system, code_value, code_display = extract_coding(fhir_resource)

                        mapped = {
                            "user_id": user_id,
                            "patient_id": patient_id,
                            "source_file_id": source_file_id,
                            "record_type": record_type,
                            "fhir_resource_type": resource_type,
                            "fhir_resource": fhir_resource,
                            "source_format": "epic_ehi",
                            "effective_date": extract_effective_date(fhir_resource),
                            "effective_date_end": extract_effective_date_end(fhir_resource),
                            "status": extract_status(fhir_resource),
                            "category": extract_categories(fhir_resource),
                            "code_system": code_system,
                            "code_value": code_value,
                            "code_display": code_display,
                            "display_text": fhir_resource.get("code", {}).get("text", "")
                            or fhir_resource.get("type", {}).get("text", "")
                            or fhir_resource.get("description", "")
                            or resource_type,
                        }

                        batch.append(mapped)
                        row_count += 1

                        if len(batch) >= batch_size:
                            count = await bulk_insert_records(db, batch)
                            stats["records_inserted"] += count
                            batch.clear()
                            await db.commit()

                    except Exception as e:
                        stats["errors"].append(
                            {"file": table_name, "row": row_idx, "error": str(e)}
                        )
                        continue

            if batch:
                count = await bulk_insert_records(db, batch)
                stats["records_inserted"] += count
                batch.clear()
                await db.commit()

        except Exception as e:
            stats["errors"].append({"file": table_name, "error": str(e)})
            logger.error("Error processing %s: %s", table_name, e)

        stats["files_processed"] += 1
        logger.info("Processed %s: %d rows", table_name, row_count)

        if progress_callback:
            await progress_callback(file_idx + 1, total_files, stats["records_inserted"])

    logger.info(
        "Epic export processing complete: %d files, %d records, %d errors",
        stats["files_processed"],
        stats["records_inserted"],
        len(stats["errors"]),
    )
    return stats
