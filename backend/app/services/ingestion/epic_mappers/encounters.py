from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class PatEncMapper(EpicMapper):
    """Map PAT_ENC rows to FHIR Encounter resources."""

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        contact_date = self.parse_epic_date(self.safe_get(row, "CONTACT_DATE"))
        if not contact_date:
            return None

        status_raw = self.safe_get(row, "APPT_STATUS_C_NAME").lower()
        status = "finished"
        if "completed" in status_raw or "complete" in status_raw:
            status = "finished"
        elif "cancelled" in status_raw or "canceled" in status_raw:
            status = "cancelled"
        elif "no show" in status_raw:
            status = "cancelled"
        elif "scheduled" in status_raw:
            status = "planned"

        enc_class = "AMB"
        fin_class = self.safe_get(row, "FIN_CLASS_C_NAME").lower()
        if "inpatient" in fin_class:
            enc_class = "IMP"
        elif "emergency" in fin_class:
            enc_class = "EMER"

        resource = {
            "resourceType": "Encounter",
            "status": status,
            "class": {"code": enc_class},
            "period": {"start": contact_date.isoformat()},
        }

        dept = self.safe_get(row, "DEPARTMENT_ID_EXTERNAL_NAME")
        if dept:
            resource["location"] = [{"location": {"display": dept}}]

        provider = self.safe_get(row, "VISIT_PROV_ID_PROV_NAME")
        title = self.safe_get(row, "VISIT_PROV_TITLE_NAME")
        if provider:
            display = f"{provider}, {title}" if title else provider
            resource["participant"] = [{"individual": {"display": display}}]

        discharge_date = self.parse_epic_date(self.safe_get(row, "HOSP_DISCHRG_TIME"))
        if discharge_date:
            resource["period"]["end"] = discharge_date.isoformat()

        reason = self.safe_get(row, "CONTACT_COMMENT")
        if reason:
            resource["reasonCode"] = [{"text": reason}]

        return resource
