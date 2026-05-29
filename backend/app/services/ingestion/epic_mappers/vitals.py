from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class VitalsMapper(EpicMapper):
    """Map IP_FLWSHT_MEAS rows to FHIR Observation (vital-signs) resources."""

    source_table = "IP_FLWSHT_MEAS"
    primary_key_columns = ["FSD_ID", "LINE"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        measure_name = (
            self.safe_get(row, "FLO_MEAS_NAME")
            or self.safe_get(row, "DISP_NAME")
            or self.safe_get(row, "FLO_MEAS_ID_FLO_MEAS_NAME")
        )
        value = self.safe_get(row, "MEAS_VALUE")
        if not measure_name or not value:
            return None

        recorded_date = self.parse_epic_date(
            self.safe_get(row, "RECORDED_TIME")
            or self.safe_get(row, "ENTRY_TIME")
        )

        resource: dict = {
            "resourceType": "Observation",
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "vital-signs",
                            "display": "Vital Signs",
                        }
                    ]
                }
            ],
            "code": {"text": measure_name},
        }

        if recorded_date:
            resource["effectiveDateTime"] = recorded_date.isoformat()

        # Try to parse numeric value
        unit = self.safe_get(row, "UNITS")
        try:
            numeric_val = float(value)
            resource["valueQuantity"] = {
                "value": numeric_val,
                "unit": unit or "",
            }
        except ValueError:
            resource["valueString"] = value

        return resource
