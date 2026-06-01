"""Extract and backfill patient demographics during ingestion.

De-identification has a deterministic layer (`services/ai/patient_phi`) that
strips the *known* patient's name / MRN / DOB from free text before it reaches
Gemini. That layer is only effective if the ``patients`` row actually carries
those encrypted identifiers. Historically ``get_or_create_patient`` stored only
``fhir_id`` + ``gender``, leaving ``name_encrypted`` NULL — so the deterministic
scrubber was a no-op and the patient's own name could reach the LLM.

This module extracts demographics from each structured source (FHIR Patient
resource, IHE-XDM manifest, Epic ``PATIENT.tsv``) and backfills any missing
encrypted fields on the patient record. Names are normalized so separators
(``^`` in HL7 PID-5, ``,`` in Epic ``LAST,FIRST``) become spaces — ``scrub_phi``
splits on whitespace and redacts each name *part* case-insensitively, so
``Pedro``/``Otalora`` then get stripped in every form across all records.
"""
from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.encryption import encrypt_field
from app.models.patient import Patient

logger = logging.getLogger(__name__)

# HL7 PID-5 (``Last^First^Middle``) and Epic (``LAST,FIRST``) use these as name
# component separators; normalize them to spaces so name parts split cleanly.
_NAME_SEP = re.compile(r"[\^,|]+")
_WS = re.compile(r"\s+")


def normalize_name(raw: str | None) -> str:
    """Normalize a name into whitespace-separated parts.

    ``"Otalora^Pedro^^^^"`` -> ``"Otalora Pedro"``; ``"OTALORA,PEDRO"`` ->
    ``"OTALORA PEDRO"``. Returns ``""`` when there is nothing usable.
    """
    if not raw:
        return ""
    return _WS.sub(" ", _NAME_SEP.sub(" ", raw)).strip()


def extract_fhir_demographics(resource: dict) -> dict[str, str | None]:
    """Pull name / MRN / DOB / gender from a FHIR Patient resource."""
    name: str | None = None
    names = resource.get("name") or []
    if names:
        hn = names[0] or {}
        if hn.get("text"):
            name = hn["text"]
        else:
            parts = list(hn.get("given") or [])
            if hn.get("family"):
                parts.append(hn["family"])
            name = " ".join(p for p in parts if p) or None

    mrn: str | None = None
    for ident in resource.get("identifier") or []:
        coding = (ident.get("type") or {}).get("coding") or []
        if any(c.get("code") == "MR" for c in coding):
            mrn = ident.get("value")
            break
    if mrn is None:
        idents = resource.get("identifier") or []
        if idents:
            mrn = idents[0].get("value")

    return {
        "name": normalize_name(name) or None,
        "mrn": mrn,
        "dob": resource.get("birthDate"),
        "gender": resource.get("gender"),
    }


def extract_epic_demographics(tsv_dir: Path) -> dict[str, str | None]:
    """Pull demographics from an Epic ``PATIENT.tsv`` in ``tsv_dir`` (first row)."""
    patient_file = tsv_dir / "PATIENT.tsv"
    if not patient_file.is_file():
        return {}
    try:
        with open(patient_file, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            row = next(reader, None)
    except (OSError, csv.Error):
        logger.warning("Could not read Epic PATIENT.tsv for demographics", exc_info=True)
        return {}
    if not row:
        return {}

    dob = row.get("BIRTH_DATE")
    if dob:
        dob = dob.split(" ", 1)[0]  # drop "12:00:00 AM" time component
    return {
        "name": normalize_name(row.get("PAT_NAME")) or None,
        "mrn": row.get("PAT_MRN_ID") or None,
        "dob": dob or None,
        "gender": row.get("SEX") or row.get("GENDER") or None,
    }


async def backfill_patient_demographics(
    db: AsyncSession,
    patient: Patient,
    *,
    name: str | None = None,
    mrn: str | None = None,
    dob: str | None = None,
    gender: str | None = None,
    commit: bool = True,
) -> bool:
    """Encrypt and set any demographic fields currently missing on ``patient``.

    Only fills blanks (never overwrites an existing value), so the first source
    that supplies a field wins and later uploads can't clobber it. Returns True
    if anything changed.
    """
    changed = False

    norm_name = normalize_name(name)
    if norm_name and patient.name_encrypted is None:
        patient.name_encrypted = encrypt_field(norm_name)
        changed = True
    if mrn and patient.mrn_encrypted is None:
        patient.mrn_encrypted = encrypt_field(mrn)
        changed = True
    if dob and patient.birth_date_encrypted is None:
        patient.birth_date_encrypted = encrypt_field(dob)
        changed = True
    if gender and not patient.gender:
        patient.gender = gender
        changed = True

    if changed and commit:
        await db.commit()
        await db.refresh(patient)
        logger.info("Backfilled patient demographics for %s", patient.id)
    return changed
