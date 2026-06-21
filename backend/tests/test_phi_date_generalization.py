"""W13 (HIPAA DEID-02 / SEC-PHI-04) — year-only date generalization + age cap.

HIPAA Safe Harbor permits the YEAR of a date but NOT the month or day for dates
directly related to an individual, and requires ages over 89 to be aggregated to
a single "90+" category. The PHI scrubber previously generalized dates only to
month+year (an impermissible date element) and recognized just two date formats.

These tests drive the corrected behavior: every supported date format collapses
to the four-digit year only (month and day dropped), and over-89 ages cap to
"90+". ``enable_ner=False`` isolates the regex layer (no spaCy dependency).
"""
from __future__ import annotations

from app.services.ai.phi_scrubber import scrub_phi


def _scrub(text: str) -> str:
    return scrub_phi(text, enable_ner=False)[0]


def test_us_slash_date_generalized_to_year_only():
    """MM/DD/YYYY -> year only (month AND day dropped)."""
    out = _scrub("Collected: 07/14/2023")
    assert "2023" in out
    assert "07" not in out
    assert "14" not in out
    assert "07/14/2023" not in out
    assert "07/2023" not in out  # month must NOT survive


def test_iso_date_generalized_to_year_only():
    """ISO YYYY-MM-DD (ubiquitous in FHIR/OCR text) -> year only."""
    out = _scrub("Recorded on 2023-07-14 in chart.")
    assert "2023" in out
    assert "2023-07-14" not in out
    assert "2023-07" not in out
    assert "-07-14" not in out


def test_iso_slash_date_generalized_to_year_only():
    """YYYY/MM/DD -> year only."""
    out = _scrub("Visit 2023/07/14 documented.")
    assert "2023" in out
    assert "2023/07/14" not in out
    assert "2023/07" not in out


def test_day_first_month_name_date_generalized_to_year_only():
    """DD Month YYYY -> year only."""
    out = _scrub("Seen 14 July 2023 for follow-up.")
    assert "2023" in out
    assert "14 July 2023" not in out
    assert "July" not in out
    assert "14 July" not in out


def test_month_first_month_name_date_generalized_to_year_only():
    """Month DD, YYYY -> year only (previously kept the month)."""
    out = _scrub("Diagnosed July 14, 2023 per note.")
    assert "2023" in out
    assert "July 14, 2023" not in out
    assert "July" not in out
    assert "July 2023" not in out  # month must NOT survive


def test_over_89_age_capped_to_90_plus():
    """Ages over 89 aggregate to '90+' (Safe Harbor)."""
    out = _scrub("The 95-year-old patient was seen.")
    assert "90+" in out
    assert "95" not in out


def test_age_phrase_capped_to_90_plus():
    """'age 95' -> 'age 90+'."""
    out = _scrub("Patient age 92 with hypertension.")
    assert "90+" in out
    assert "92" not in out


def test_age_at_or_below_89_unchanged():
    """Control: a normal age (<=89) must NOT be altered."""
    out = _scrub("The 45-year-old patient was seen.")
    assert "45-year-old" in out
    assert "90+" not in out


def test_report_counts_generalized_dates():
    """The de-identification report records each generalized date."""
    text = "DOB 07/31/1996; collected 2023-02-16; noted 14 July 2024; per July 4, 2025"
    scrubbed, report = scrub_phi(text, enable_ner=False)
    assert report.get("dates_generalized", 0) >= 4
    for forbidden in ("07/31/1996", "2023-02-16", "14 July 2024", "July 4, 2025"):
        assert forbidden not in scrubbed
    for year in ("1996", "2023", "2024", "2025"):
        assert year in scrubbed
