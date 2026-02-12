from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class DocInformationMapper(EpicMapper):
    """Map DOC_INFORMATION rows to FHIR DocumentReference resources."""

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        doc_type = self.safe_get(row, "DOC_INFO_TYPE_C_NAME")
        if not doc_type:
            return None

        doc_date = self.parse_epic_date(self.safe_get(row, "DOC_RECV_TIME"))
        status_raw = self.safe_get(row, "DOC_STAT_C_NAME").lower()

        status = "current"
        if "inactive" in status_raw or "deleted" in status_raw:
            status = "superseded"

        resource = {
            "resourceType": "DocumentReference",
            "status": status,
            "type": {"text": doc_type},
            "description": self.safe_get(row, "DOC_DESCR") or doc_type,
        }

        if doc_date:
            resource["date"] = doc_date.isoformat()

        author = self.safe_get(row, "RECV_BY_USER_ID_NAME")
        if author:
            resource["author"] = [{"display": author}]

        is_scanned = self.safe_get(row, "IS_SCANNED_YN")
        if is_scanned == "Y":
            resource["category"] = [{"text": "scanned"}]

        return resource
