from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class SocialHxMapper(EpicMapper):
    """Map SOCIAL_HX rows to FHIR Observation (social-history) resources."""

    source_table = "SOCIAL_HX"
    primary_key_columns = ["PAT_ENC_CSN_ID", "CONTACT_DATE"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        # Social history tables vary; try common column patterns
        hx_type = (
            self.safe_get(row, "SOCIAL_HX_TYPE_C_NAME")
            or self.safe_get(row, "HX_TYPE")
            or self.safe_get(row, "TOBACCO_USER_C_NAME")
        )
        hx_value = (
            self.safe_get(row, "SOCIAL_HX_COMMENT")
            or self.safe_get(row, "COMMENT")
            or self.safe_get(row, "SMOKING_TOBA_USE_C_NAME")
        )

        if not hx_type and not hx_value:
            return None

        contact_date = self.parse_epic_date(
            self.safe_get(row, "CONTACT_DATE")
            or self.safe_get(row, "ENTRY_DATE")
        )

        resource: dict = {
            "resourceType": "Observation",
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "social-history",
                            "display": "Social History",
                        }
                    ]
                }
            ],
            "code": {"text": hx_type or "Social History"},
        }

        if contact_date:
            resource["effectiveDateTime"] = contact_date.isoformat()

        if hx_value:
            resource["valueString"] = hx_value

        return resource
