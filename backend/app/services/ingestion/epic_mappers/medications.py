from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class OrderMedMapper(EpicMapper):
    """Map ORDER_MED rows to FHIR MedicationRequest resources."""

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        med_name = self.safe_get(row, "DISPLAY_NAME") or self.safe_get(
            row, "MEDICATION_ID_MEDICATION_NAME"
        )
        if not med_name:
            return None

        start_date = self.parse_epic_date(self.safe_get(row, "START_DATE"))
        end_date = self.parse_epic_date(self.safe_get(row, "END_DATE"))
        authored = self.parse_epic_date(self.safe_get(row, "ORDERING_DATE"))
        status_raw = self.safe_get(row, "ORDER_STATUS_C_NAME").lower()

        status = "active"
        if "completed" in status_raw or "sent" in status_raw:
            status = "completed"
        elif "cancel" in status_raw or "discontinue" in status_raw:
            status = "cancelled"

        resource = {
            "resourceType": "MedicationRequest",
            "status": status,
            "intent": "order",
            "medicationCodeableConcept": {"text": med_name},
            "category": [{"text": "community"}],
        }

        if authored:
            resource["authoredOn"] = authored.isoformat()

        dosage = self.safe_get(row, "DOSAGE")
        description = self.safe_get(row, "DESCRIPTION")
        if dosage or description:
            resource["dosageInstruction"] = [{"text": dosage or description}]

        quantity = self.safe_get(row, "QUANTITY")
        refills = self.safe_get(row, "REFILLS")
        if quantity or refills:
            disp = {}
            if quantity:
                disp["quantity"] = {"value": quantity}
            if refills:
                disp["numberOfRepeatsAllowed"] = refills
            resource["dispenseRequest"] = disp

        if start_date or end_date:
            period = {}
            if start_date:
                period["start"] = start_date.isoformat()
            if end_date:
                period["end"] = end_date.isoformat()
            resource["effectivePeriod"] = period

        prescriber = self.safe_get(row, "MED_PRESC_PROV_ID_PROV_NAME")
        if prescriber:
            resource["requester"] = {"display": prescriber}

        route = self.safe_get(row, "MED_ROUTE_C_NAME")
        if route and resource.get("dosageInstruction"):
            resource["dosageInstruction"][0]["route"] = {"text": route}

        return resource
