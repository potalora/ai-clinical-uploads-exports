from __future__ import annotations

from app.services.ingestion.epic_mappers.base import EpicMapper


class ReferralMapper(EpicMapper):
    """Map REFERRAL rows to FHIR ServiceRequest resources."""

    source_table = "REFERRAL"
    primary_key_columns = ["REFERRAL_ID"]

    def to_fhir(self, row: dict[str, str]) -> dict | None:
        reason = self.safe_get(row, "RSN_FOR_RFL_C_NAME")
        referral_prov = self.safe_get(row, "REFERRAL_PROV_ID_PROV_NAME")
        referring_prov = self.safe_get(row, "REFERRING_PROV_ID_REFERRING_PROV_NAM")

        if not reason and not referral_prov:
            return None

        start_date = self.parse_epic_date(self.safe_get(row, "START_DATE"))
        exp_date = self.parse_epic_date(self.safe_get(row, "EXP_DATE"))
        status_raw = self.safe_get(row, "RFL_STATUS_C_NAME").lower()

        status = "active"
        if "completed" in status_raw or "closed" in status_raw:
            status = "completed"
        elif "cancelled" in status_raw or "canceled" in status_raw:
            status = "revoked"
        elif "pending" in status_raw:
            status = "draft"

        resource: dict = {
            "resourceType": "ServiceRequest",
            "status": status,
            "intent": "order",
            "category": [{"text": "referral"}],
        }

        if reason:
            resource["code"] = {"text": reason}

        if start_date:
            resource["authoredOn"] = start_date.isoformat()

        if start_date or exp_date:
            occurrence: dict = {}
            if start_date:
                occurrence["start"] = start_date.isoformat()
            if exp_date:
                occurrence["end"] = exp_date.isoformat()
            resource["occurrencePeriod"] = occurrence

        if referring_prov:
            resource["requester"] = {"display": referring_prov}

        if referral_prov:
            resource["performer"] = [{"display": referral_prov}]

        return resource
