from __future__ import annotations

import re
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Regex patterns for all 18 HIPAA identifiers
PATTERNS = {
    "ssn": (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    "phone": (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    "fax": (re.compile(r"\b(?:fax|facsimile)[:\s]*(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", re.IGNORECASE), "[FAX]"),
    "email": (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    "mrn": (re.compile(r"\b(?:MRN|mrn|Medical Record Number)[:\s]*\d+\b"), "[MRN]"),
    "mrn_numeric": (re.compile(r"\b\d{8,12}\b"), None),  # Only scrub in context
    "ip_address": (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP]"),
    "url": (re.compile(r"https?://[^\s<>\"]+"), "[URL]"),
    "zip_code": (re.compile(r"\b\d{5}(?:-\d{4})?\b"), "[ZIP]"),
    "date_full": (
        re.compile(r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/\d{4}\b"),
        None,
    ),
    "account": (re.compile(r"\b(?:account|acct)[:\s#]*\d+\b", re.IGNORECASE), "[ACCOUNT]"),
    "license": (
        re.compile(r"\b(?:license|certificate|DEA)[:\s#]*[A-Z0-9]+\b", re.IGNORECASE),
        "[LICENSE]",
    ),
    "vehicle_id": (re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"), "[VIN]"),
    "device_id": (
        re.compile(r"\b(?:serial|UDI|device\s*(?:id|identifier))[:\s#]*[A-Za-z0-9\-]+\b", re.IGNORECASE),
        "[DEVICE_ID]",
    ),
    "biometric_id": (
        re.compile(r"\b(?:biometric|fingerprint|retina|voiceprint)[:\s#]*[A-Za-z0-9\-]+\b", re.IGNORECASE),
        "[BIOMETRIC]",
    ),
    "health_plan_number": (
        re.compile(r"\b(?:plan|policy|member|group|subscriber|beneficiary)\s*(?:number|no|#|id)[:\s#]*[A-Za-z0-9\-]+\b", re.IGNORECASE),
        "[HEALTH_PLAN]",
    ),
}


def scrub_phi(
    text: str,
    patient_names: list[str] | None = None,
    patient_dob: str | None = None,
    patient_address: str | None = None,
    patient_mrn: str | None = None,
    enable_ner: bool | None = None,
) -> tuple[str, dict[str, int]]:
    """Remove PHI from text and return scrubbed text + de-identification report.

    Args:
        enable_ner: Run the spaCy NER pass for free-text person names (providers,
            family, anyone not in the patient record). Defaults to
            ``settings.phi_ner_enabled`` when None. The pass fails open if the
            model is unavailable.

    Returns:
        tuple: (scrubbed_text, report_dict)
    """
    report: dict[str, int] = {}
    scrubbed = text

    # Scrub known patient names first (targeted)
    if patient_names:
        for name in patient_names:
            if not name:
                continue
            for part in name.split():
                if len(part) < 2:
                    continue
                # Use word boundaries for short names to reduce false positives
                if len(part) <= 3:
                    pattern = re.compile(r"\b" + re.escape(part) + r"\b", re.IGNORECASE)
                else:
                    pattern = re.compile(re.escape(part), re.IGNORECASE)
                matches = pattern.findall(scrubbed)
                if matches:
                    report["names_scrubbed"] = report.get("names_scrubbed", 0) + len(matches)
                    scrubbed = pattern.sub("[PATIENT]", scrubbed)

    # Scrub known MRN
    if patient_mrn:
        pattern = re.compile(re.escape(patient_mrn))
        matches = pattern.findall(scrubbed)
        if matches:
            report["mrns_removed"] = len(matches)
            scrubbed = pattern.sub("[MRN]", scrubbed)

    # Scrub known address
    if patient_address:
        for part in patient_address.split(","):
            part = part.strip()
            if len(part) > 3:
                pattern = re.compile(re.escape(part), re.IGNORECASE)
                matches = pattern.findall(scrubbed)
                if matches:
                    report["addresses_removed"] = report.get("addresses_removed", 0) + len(matches)
                    scrubbed = pattern.sub("[LOCATION]", scrubbed)

    # Scrub known DOB
    if patient_dob:
        pattern = re.compile(re.escape(patient_dob))
        matches = pattern.findall(scrubbed)
        if matches:
            report["dobs_removed"] = len(matches)
            scrubbed = pattern.sub("[DATE]", scrubbed)

    # Apply regex patterns
    for key, (pattern, replacement) in PATTERNS.items():
        if replacement is None:
            continue
        matches = pattern.findall(scrubbed)
        if matches:
            report_key = f"{key}_scrubbed"
            report[report_key] = len(matches)
            scrubbed = pattern.sub(replacement, scrubbed)

    # Generalize specific dates to month/year
    date_pattern = re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    )
    date_matches = date_pattern.findall(scrubbed)
    if date_matches:
        report["dates_generalized"] = len(date_matches)
        for m in date_matches:
            parts = re.split(r"[\s,]+", m)
            if len(parts) >= 3:
                scrubbed = scrubbed.replace(m, f"{parts[0]} {parts[-1]}")

    # NER pass: redact free-text person names the patterns/known-identifier
    # passes can't catch (providers, family members). Runs last, after known
    # patient names are already replaced. Fails open if the model is missing.
    use_ner = settings.phi_ner_enabled if enable_ner is None else enable_ner
    if use_ner:
        from app.services.ai.phi_ner import redact_person_names

        scrubbed, ner_count = redact_person_names(scrubbed)
        if ner_count:
            report["ner_names_scrubbed"] = ner_count

    return scrubbed, report
