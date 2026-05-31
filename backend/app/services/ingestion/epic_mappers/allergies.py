from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class AllergyMapper(EpicMapper):
    """Map ALLERGY rows to FHIR AllergyIntolerance resources."""

    source_table = "ALLERGY"
    primary_key_columns = ["ALLERGY_ID"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        allergen = self.safe_get(row, "ALLERGEN_ID_ALLERGEN_NAME")
        if not allergen:
            return None

        date_noted = self.parse_epic_date(self.safe_get(row, "DATE_NOTED"))
        severity_raw = self.safe_get(row, "SEVERITY_C_NAME").lower()
        status_raw = self.safe_get(row, "ALRGY_STATUS_C_NAME").lower()

        # Map clinical status
        clinical_status = "active"
        if "inactive" in status_raw or "deleted" in status_raw:
            clinical_status = "inactive"
        elif "resolved" in status_raw:
            clinical_status = "resolved"

        # Map severity
        severity = None
        if "severe" in severity_raw or "high" in severity_raw:
            severity = "severe"
        elif "moderate" in severity_raw:
            severity = "moderate"
        elif "mild" in severity_raw or "low" in severity_raw:
            severity = "mild"

        resource: dict = {
            "resourceType": "AllergyIntolerance",
            "code": {"text": allergen},
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": clinical_status,
                    }
                ]
            },
        }

        if date_noted:
            resource["recordedDate"] = date_noted.isoformat()

        reaction_text = self.safe_get(row, "REACTION")
        if reaction_text:
            reaction: dict = {"manifestation": [{"text": reaction_text}]}
            if severity:
                reaction["severity"] = severity
            resource["reaction"] = [reaction]
        elif severity:
            resource["reaction"] = [{"severity": severity}]

        return resource
