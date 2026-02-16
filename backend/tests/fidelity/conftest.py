"""Fidelity test fixtures and markers.

Real-data tests are marked with @pytest.mark.fidelity and skip
gracefully when real test data is not present (CI-safe).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
EPIC_EXPORT_DIR = FIXTURES_DIR / "epic_export"
USER_FHIR_PATH = FIXTURES_DIR / "user_provided_fhir.json"
SYNTHETIC_EPIC_DIR = FIXTURES_DIR / "sample_epic_tsv"


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "fidelity: marks tests requiring real user-provided data (skip when absent)"
    )


@pytest.fixture(scope="module")
def real_epic_dir():
    """Path to real Epic EHI Tables export directory. Skips if absent."""
    if not EPIC_EXPORT_DIR.exists():
        pytest.skip("No real Epic export at tests/fixtures/epic_export/")
    tsv_files = list(EPIC_EXPORT_DIR.glob("*.tsv"))
    if not tsv_files:
        pytest.skip("No TSV files in tests/fixtures/epic_export/")
    return EPIC_EXPORT_DIR


@pytest.fixture(scope="module")
def real_fhir_bundle():
    """Parsed real FHIR bundle. Skips if absent."""
    if not USER_FHIR_PATH.exists():
        pytest.skip("No real FHIR bundle at tests/fixtures/user_provided_fhir.json")
    return json.loads(USER_FHIR_PATH.read_text(encoding="utf-8-sig"))


@pytest.fixture(scope="module")
def synthetic_epic_dir():
    """Path to synthetic Epic TSV fixtures (always available)."""
    return SYNTHETIC_EPIC_DIR
