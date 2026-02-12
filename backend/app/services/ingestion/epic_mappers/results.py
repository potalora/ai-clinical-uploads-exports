from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class OrderResultsMapper(EpicMapper):
    """Map ORDER_RESULTS rows to FHIR Observation resources."""

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        component_name = self.safe_get(row, "COMPONENT_ID_NAME")
        if not component_name:
            return None

        result_date = self.parse_epic_date(self.safe_get(row, "RESULT_DATE"))
        value = self.safe_get(row, "ORD_VALUE")
        num_value = self.safe_get(row, "ORD_NUM_VALUE")
        unit = self.safe_get(row, "REFERENCE_UNIT")
        ref_low = self.safe_get(row, "REFERENCE_LOW")
        ref_high = self.safe_get(row, "REFERENCE_HIGH")
        flag = self.safe_get(row, "RESULT_FLAG_C_NAME")
        status_raw = self.safe_get(row, "RESULT_STATUS_C_NAME").lower()

        status = "final"
        if "preliminary" in status_raw:
            status = "preliminary"
        elif "corrected" in status_raw:
            status = "corrected"

        resource = {
            "resourceType": "Observation",
            "status": status,
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "laboratory",
                            "display": "Laboratory",
                        }
                    ]
                }
            ],
            "code": {"text": component_name},
        }

        loinc = self.safe_get(row, "COMPON_LNC_ID_LNC_LONG_NAME")
        if loinc:
            resource["code"]["coding"] = [
                {"system": "http://loinc.org", "display": loinc}
            ]

        if result_date:
            resource["effectiveDateTime"] = result_date.isoformat()

        if num_value:
            try:
                resource["valueQuantity"] = {
                    "value": float(num_value),
                    "unit": unit or "",
                }
            except ValueError:
                resource["valueString"] = value
        elif value:
            resource["valueString"] = value

        if ref_low or ref_high:
            ref_range = {}
            if ref_low:
                try:
                    ref_range["low"] = {"value": float(ref_low), "unit": unit or ""}
                except ValueError:
                    pass
            if ref_high:
                try:
                    ref_range["high"] = {"value": float(ref_high), "unit": unit or ""}
                except ValueError:
                    pass
            if ref_range:
                resource["referenceRange"] = [ref_range]

        if flag:
            interpretation_code = "N"
            flag_lower = flag.lower()
            if "high" in flag_lower or "h" == flag_lower:
                interpretation_code = "H"
            elif "low" in flag_lower or "l" == flag_lower:
                interpretation_code = "L"
            elif "abnormal" in flag_lower:
                interpretation_code = "A"
            resource["interpretation"] = [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            "code": interpretation_code,
                        }
                    ]
                }
            ]

        return resource
