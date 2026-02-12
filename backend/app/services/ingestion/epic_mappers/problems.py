from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class ProblemListMapper(EpicMapper):
    """Map PROBLEM_LIST rows to FHIR Condition resources."""

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        dx_name = self.safe_get(row, "DX_ID_DX_NAME")
        description = self.safe_get(row, "DESCRIPTION") or dx_name
        if not description:
            return None

        noted_date = self.parse_epic_date(self.safe_get(row, "NOTED_DATE"))
        resolved_date = self.parse_epic_date(self.safe_get(row, "RESOLVED_DATE"))
        status_raw = self.safe_get(row, "PROBLEM_STATUS_C_NAME").lower()

        clinical_status = "active"
        if "resolved" in status_raw or resolved_date:
            clinical_status = "resolved"
        elif "inactive" in status_raw:
            clinical_status = "inactive"

        resource = {
            "resourceType": "Condition",
            "code": {"text": description},
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": clinical_status,
                    }
                ]
            },
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                            "code": "problem-list-item",
                            "display": "Problem List Item",
                        }
                    ]
                }
            ],
        }

        if noted_date:
            resource["onsetDateTime"] = noted_date.isoformat()
        if resolved_date:
            resource["abatementDateTime"] = resolved_date.isoformat()

        chronic = self.safe_get(row, "CHRONIC_YN")
        if chronic == "Y":
            resource["category"].append({"text": "chronic"})

        comment = self.safe_get(row, "PROBLEM_CMT")
        if comment:
            resource["note"] = [{"text": comment}]

        return resource


class MedicalHxMapper(EpicMapper):
    """Map MEDICAL_HX rows to FHIR Condition resources."""

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        dx_name = self.safe_get(row, "DX_ID_DX_NAME")
        if not dx_name:
            return None

        hx_date = self.parse_epic_date(self.safe_get(row, "MEDICAL_HX_DATE"))

        resource = {
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
                            "code": "problem-list-item",
                        }
                    ],
                    "text": "Medical History",
                }
            ],
        }

        if hx_date:
            resource["onsetDateTime"] = hx_date.isoformat()

        annotation = self.safe_get(row, "MED_HX_ANNOTATION")
        if annotation:
            resource["note"] = [{"text": annotation}]

        return resource
