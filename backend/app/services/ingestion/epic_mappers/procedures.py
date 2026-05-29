from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class OrderProcMapper(EpicMapper):
    """Map ORDER_PROC rows to FHIR Procedure resources."""

    source_table = "ORDER_PROC"
    primary_key_columns = ["ORDER_PROC_ID"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        # Try multiple column name patterns for procedure name
        proc_name = (
            self.safe_get(row, "DESCRIPTION")
            or self.safe_get(row, "PROC_NAME")
            or self.safe_get(row, "ORDER_TYPE_C_NAME")
            or self.safe_get(row, "DISPLAY_NAME")
        )
        if not proc_name:
            return None

        order_date = self.parse_epic_date(
            self.safe_get(row, "ORDER_INST")
            or self.safe_get(row, "ORDERING_DATE")
            or self.safe_get(row, "ORDER_DATE")
        )
        status_raw = self.safe_get(row, "ORDER_STATUS_C_NAME").lower()

        status = "completed"
        if "pending" in status_raw or "ordered" in status_raw:
            status = "preparation"
        elif "cancel" in status_raw or "discontinue" in status_raw:
            status = "not-done"
        elif "in progress" in status_raw:
            status = "in-progress"

        resource: dict = {
            "resourceType": "Procedure",
            "status": status,
            "code": {"text": proc_name},
        }

        if order_date:
            resource["performedDateTime"] = order_date.isoformat()

        provider = (
            self.safe_get(row, "AUTHRZING_PROV_ID_PROV_NAME")
            or self.safe_get(row, "ORD_PROV_ID_PROV_NAME")
        )
        if provider:
            resource["performer"] = [{"actor": {"display": provider}}]

        return resource
