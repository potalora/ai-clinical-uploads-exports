from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class FamilyHxMapper(EpicMapper):
    """Map FAMILY_HX rows to FHIR FamilyMemberHistory resources."""

    source_table = "FAMILY_HX"
    primary_key_columns = ["PAT_ENC_CSN_ID", "LINE"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        dx_name = self.safe_get(row, "FAM_MEDICAL_DX_ID_DX_NAME")
        relation = self.safe_get(row, "RELATION_C_NAME")

        if not dx_name:
            return None

        resource: dict = {
            "resourceType": "FamilyMemberHistory",
            "status": "completed",
        }

        if relation:
            resource["relationship"] = {"text": relation}

        condition: dict = {"code": {"text": dx_name}}

        age_of_onset = self.safe_get(row, "AGE_OF_ONSET")
        if age_of_onset:
            try:
                condition["onsetAge"] = {
                    "value": int(age_of_onset),
                    "unit": "years",
                    "system": "http://unitsofmeasure.org",
                    "code": "a",
                }
            except ValueError:
                condition["onsetString"] = age_of_onset

        resource["condition"] = [condition]

        return resource
