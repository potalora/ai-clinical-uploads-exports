from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class ImmuneMapper(EpicMapper):
    """Map IMMUNE rows to FHIR Immunization resources."""

    source_table = "IMMUNE"
    primary_key_columns = ["IMMUNE_ID"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        vaccine_name = self.safe_get(row, "IMMUNZATN_ID_NAME")
        if not vaccine_name:
            return None

        immune_date = self.parse_epic_date(self.safe_get(row, "IMMUNE_DATE"))
        status_raw = self.safe_get(row, "IMMNZTN_STATUS_C_NAME").lower()

        status = "completed"
        if "not done" in status_raw or "refused" in status_raw:
            status = "not-done"
        elif "entered-in-error" in status_raw:
            status = "entered-in-error"

        resource: dict = {
            "resourceType": "Immunization",
            "status": status,
            "vaccineCode": {"text": vaccine_name},
        }

        if immune_date:
            resource["occurrenceDateTime"] = immune_date.isoformat()

        dose = self.safe_get(row, "DOSE")
        route = self.safe_get(row, "ROUTE_C_NAME")
        site = self.safe_get(row, "SITE_C_NAME")

        if dose:
            resource["doseQuantity"] = {"value": dose}
        if route:
            resource["route"] = {"text": route}
        if site:
            resource["site"] = {"text": site}

        manufacturer = self.safe_get(row, "MFG_C_NAME")
        if manufacturer:
            resource["manufacturer"] = {"display": manufacturer}

        lot = self.safe_get(row, "LOT")
        if lot:
            resource["lotNumber"] = lot

        return resource
