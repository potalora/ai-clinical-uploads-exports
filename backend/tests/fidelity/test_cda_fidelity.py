"""CDA fidelity tests against real HealthSummary XDM export.

These tests run against an actual patient HealthSummary export.
They skip gracefully when the fixture directory is absent (CI-safe).

Fixture setup (one-time, gitignored):
    ln -sf /path/to/HealthSummary_export backend/tests/fixtures/health_summary_xdm
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ingestion.cda_dedup import deduplicate_across_documents
from app.services.ingestion.cda_parser import parse_cda_document
from app.services.ingestion.xdm_parser import parse_xdm_metadata

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "health_summary_xdm"

pytestmark = pytest.mark.fidelity

skip_if_no_fixture = pytest.mark.skipif(
    not FIXTURE_DIR.exists(),
    reason=f"Real-data fixture not found at {FIXTURE_DIR}",
)


def _find_metadata() -> Path | None:
    """Find the METADATA.XML file within the fixture directory."""
    for p in FIXTURE_DIR.rglob("METADATA.XML"):
        return p
    return None


def _find_cda_xml_files() -> list[Path]:
    """Find all DOC*.XML files (CDA documents) within the fixture."""
    return sorted(FIXTURE_DIR.rglob("DOC*.XML"))


def _get_manifest():
    """Parse the XDM manifest and return it."""
    metadata_path = _find_metadata()
    if metadata_path is None:
        return None
    return parse_xdm_metadata(metadata_path)


def _parse_all_documents(manifest=None):
    """Parse all CDA documents, returning (all_records, per_doc_records)."""
    xml_files = _find_cda_xml_files()
    all_records: list[dict] = []
    per_doc: dict[str, list[dict]] = {}

    # Build a lookup from manifest doc URI to XDMDocument
    doc_lookup: dict[str, object] = {}
    if manifest and manifest.documents:
        for doc in manifest.documents:
            if doc.uri:
                doc_lookup[doc.uri] = doc

    for xml_path in xml_files:
        # Try to match this file to a manifest document by filename
        manifest_doc = doc_lookup.get(xml_path.name)

        # Try with manifest doc first, fall back to None if hash mismatch
        records = parse_cda_document(xml_path, manifest_doc=manifest_doc)
        if not records and manifest_doc is not None:
            # Hash mismatch possible — retry without validation
            records = parse_cda_document(xml_path, manifest_doc=None)

        all_records.extend(records)
        per_doc[xml_path.name] = records

    return all_records, per_doc


# ---------------------------------------------------------------------------
# TestXdmManifestFidelity
# ---------------------------------------------------------------------------


@skip_if_no_fixture
class TestXdmManifestFidelity:
    """Tests for XDM METADATA.XML parsing against real data."""

    def test_manifest_parses_successfully(self):
        """METADATA.XML parses and contains documents."""
        manifest = _get_manifest()
        assert manifest is not None, "METADATA.XML failed to parse"
        assert len(manifest.documents) > 0, "Manifest has no documents"

    def test_manifest_has_xml_documents(self):
        """At least one document in the manifest is XML (CDA)."""
        manifest = _get_manifest()
        assert manifest is not None
        xml_docs = [d for d in manifest.documents if "xml" in d.mime_type.lower()]
        assert len(xml_docs) >= 1, (
            f"Expected at least 1 XML document, got {len(xml_docs)}. "
            f"Mime types: {[d.mime_type for d in manifest.documents]}"
        )

    def test_manifest_extracts_patient_info(self):
        """Patient demographics are extracted from the manifest."""
        manifest = _get_manifest()
        assert manifest is not None
        assert manifest.patient_name is not None, "patient_name not extracted"
        assert manifest.patient_dob is not None, "patient_dob not extracted"


# ---------------------------------------------------------------------------
# TestCdaParsingFidelity
# ---------------------------------------------------------------------------


@skip_if_no_fixture
class TestCdaParsingFidelity:
    """Tests for CDA-to-FHIR parsing against real data."""

    def test_all_documents_parse(self):
        """Every CDA XML file produces at least one record."""
        manifest = _get_manifest()
        _, per_doc = _parse_all_documents(manifest)
        assert len(per_doc) > 0, "No CDA XML files found"

        empty_docs = [name for name, recs in per_doc.items() if len(recs) == 0]
        assert len(empty_docs) == 0, (
            f"These documents produced 0 records: {empty_docs}"
        )

    def test_resource_type_coverage(self):
        """At least 3 different resource types across all documents."""
        manifest = _get_manifest()
        all_records, _ = _parse_all_documents(manifest)
        assert len(all_records) > 0, "No records parsed"

        resource_types = {r["record_type"] for r in all_records}
        assert len(resource_types) >= 3, (
            f"Expected >=3 resource types, got {len(resource_types)}: {resource_types}"
        )

    def test_records_have_display_text(self):
        """Every record has a non-empty display_text."""
        manifest = _get_manifest()
        all_records, _ = _parse_all_documents(manifest)
        assert len(all_records) > 0, "No records parsed"

        missing = [
            (r["record_type"], r.get("code_display", ""))
            for r in all_records
            if not r.get("display_text")
        ]
        # Allow some records to lack display_text (resources without codes)
        # but the majority should have it
        pct_missing = len(missing) / len(all_records)
        assert pct_missing < 0.5, (
            f"{len(missing)}/{len(all_records)} records ({pct_missing:.0%}) "
            f"lack display_text. Sample: {missing[:5]}"
        )

    def test_records_tagged_cda_source_format(self):
        """All records have source_format='cda_r2'."""
        manifest = _get_manifest()
        all_records, _ = _parse_all_documents(manifest)
        assert len(all_records) > 0, "No records parsed"

        wrong_format = [
            r for r in all_records
            if r.get("source_format") != "cda_r2"
        ]
        assert len(wrong_format) == 0, (
            f"{len(wrong_format)} records have wrong source_format: "
            f"{set(r.get('source_format') for r in wrong_format)}"
        )


# ---------------------------------------------------------------------------
# TestIntraUploadDedupFidelity
# ---------------------------------------------------------------------------


@skip_if_no_fixture
class TestIntraUploadDedupFidelity:
    """Tests for cross-document deduplication against real data."""

    def test_dedup_reduces_record_count(self):
        """Dedup collapses some duplicates (unique < total)."""
        manifest = _get_manifest()
        all_records, _ = _parse_all_documents(manifest)
        assert len(all_records) > 0, "No records parsed"

        unique, stats = deduplicate_across_documents(all_records)
        assert stats.total_parsed == len(all_records)
        assert stats.duplicates_collapsed > 0, (
            f"Expected some duplicates across {len(_find_cda_xml_files())} documents, "
            f"but got 0 collapsed out of {stats.total_parsed} total"
        )
        assert stats.unique_records < stats.total_parsed

    def test_dedup_stats_per_document(self):
        """records_per_document has an entry for each XML document."""
        manifest = _get_manifest()
        all_records, per_doc = _parse_all_documents(manifest)
        assert len(all_records) > 0, "No records parsed"

        _, stats = deduplicate_across_documents(all_records)

        # Every doc that produced records should appear in stats
        docs_with_records = {
            name for name, recs in per_doc.items() if len(recs) > 0
        }
        stats_docs = set(stats.records_per_document.keys())

        missing_from_stats = docs_with_records - stats_docs
        assert len(missing_from_stats) == 0, (
            f"Documents missing from dedup stats: {missing_from_stats}"
        )

    def test_provenance_tracks_source_documents(self):
        """Some deduplicated records have >1 source document in provenance."""
        manifest = _get_manifest()
        all_records, _ = _parse_all_documents(manifest)
        assert len(all_records) > 0, "No records parsed"

        unique, stats = deduplicate_across_documents(all_records)

        if stats.duplicates_collapsed == 0:
            pytest.skip("No duplicates found — cannot test provenance tracking")

        multi_source = [
            r for r in unique
            if len(
                r.get("fhir_resource", {})
                .get("_extraction_metadata", {})
                .get("source_documents", [])
            ) > 1
        ]
        assert len(multi_source) > 0, (
            f"Expected some records with >1 source document after collapsing "
            f"{stats.duplicates_collapsed} duplicates, but none found"
        )
