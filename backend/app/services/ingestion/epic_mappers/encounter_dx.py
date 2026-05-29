from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class EncounterDxMapper(EpicMapper):
    """Map PAT_ENC_DX rows to FHIR Condition (encounter-diagnosis) resources."""

    source_table = "PAT_ENC_DX"
    primary_key_columns = ["PAT_ENC_CSN_ID", "LINE"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        dx_name = self.safe_get(row, "DX_ID_DX_NAME")
        if not dx_name:
            return None

        contact_date = self.parse_epic_date(self.safe_get(row, "CONTACT_DATE"))
        is_primary = self.safe_get(row, "PRIMARY_DX_YN") == "Y"

        resource: dict = {
            "resourceType": "Condition",
            "code": {"text": dx_name},
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                    }
                ]
            },
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                            "code": "encounter-diagnosis",
                            "display": "Encounter Diagnosis",
                        }
                    ]
                }
            ],
        }

        if contact_date:
            resource["recordedDate"] = contact_date.isoformat()

        if is_primary:
            resource["_primaryDiagnosis"] = True

        annotation = self.safe_get(row, "ANNOTATION")
        if annotation:
            resource["note"] = [{"text": annotation}]

        return resource
