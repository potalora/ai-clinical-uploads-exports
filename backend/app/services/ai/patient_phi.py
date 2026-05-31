"""Build targeted PHI-scrubbing arguments from known patient demographics.

`scrub_phi` can remove a patient's name / MRN / birth date when those known
values are supplied. The production callers (unstructured extraction, summary
prompt builder, live summarizer) historically called `scrub_phi(text)` with no
patient context, so the patient's own identifiers were never stripped before
text was sent to Gemini. This module decrypts a patient record into the keyword
arguments `scrub_phi` expects, closing that gap.

Scope: this is *targeted* de-identification — it removes identifiers we already
know from the patient record. It does NOT detect arbitrary person names (e.g.
ordering providers, family members) in free text; that requires NER and is
tracked as a follow-up.
"""

from __future__ import annotations

import logging

from app.middleware.encryption import decrypt_field
from app.models.patient import Patient

logger = logging.getLogger(__name__)


def _safe_decrypt(blob: bytes | None) -> str | None:
    """Decrypt an encrypted patient field, returning None on absence or failure.

    A decryption error must never break the de-identification pipeline: failing
    open to the regex-based scrubber is far safer than crashing the caller
    (which could otherwise abort before any scrubbing happened). Errors are
    logged without the plaintext.
    """
    if not blob:
        return None
    try:
        value = decrypt_field(blob)
    except Exception:  # noqa: BLE001 - any crypto/format error must be non-fatal
        logger.warning(
            "Failed to decrypt patient field for PHI scrubbing; "
            "falling through to pattern-based scrubbing",
            exc_info=True,
        )
        return None
    value = value.strip()
    return value or None


def patient_scrub_args(
    patients: Patient | list[Patient] | None,
) -> dict[str, object]:
    """Build ``scrub_phi`` keyword arguments from known patient record(s).

    Decrypts each patient's name / MRN / birth date so ``scrub_phi`` can strip
    the patient's own identifiers from free text before it is sent to Gemini.

    Returns an empty dict when there is nothing to scrub, so the result is
    always safe to splat: ``scrub_phi(text, **patient_scrub_args(patient))``.

    Args:
        patients: A single Patient, a list of Patients (e.g. all patients owned
            by a user), or None.

    Returns:
        A dict containing any of ``patient_names`` (list[str]), ``patient_mrn``
        (str), and ``patient_dob`` (str) that could be decrypted.
    """
    if patients is None:
        return {}
    if isinstance(patients, Patient):
        patients = [patients]

    names: list[str] = []
    mrn: str | None = None
    dob: str | None = None

    for patient in patients:
        name = _safe_decrypt(patient.name_encrypted)
        if name and name not in names:
            names.append(name)
        # MRN / DOB are single-valued in scrub_phi; take the first available.
        if mrn is None:
            mrn = _safe_decrypt(patient.mrn_encrypted)
        if dob is None:
            dob = _safe_decrypt(patient.birth_date_encrypted)

    args: dict[str, object] = {}
    if names:
        args["patient_names"] = names
    if mrn:
        args["patient_mrn"] = mrn
    if dob:
        args["patient_dob"] = dob
    return args
