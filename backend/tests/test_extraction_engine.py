"""Escalation-policy + engine tests for the local/hybrid orchestrator (WS-A).

These exercise the orchestration logic with FAKE NER / context / Gemini, so they
need no scispaCy model and no network — the policy is fully deterministic.
"""
from __future__ import annotations

import pytest

from app.services.extraction import extraction_engine as ee
from app.services.extraction.clinical_context import SpanAssertion
from app.services.extraction.entity_extractor import ExtractedEntity
from app.services.extraction.local_ner import LABEL_CHEMICAL, LABEL_DISEASE, LocalSpan
from app.services.extraction.section_parser import ParsedSection, SectionType

pytestmark = pytest.mark.asyncio


def _span(text: str, label: str) -> LocalSpan:
    return LocalSpan(text=text, label=label, start_char=0, end_char=len(text))


def _section(stype: SectionType, text: str) -> ParsedSection:
    return ParsedSection(stype, stype.value, text, (0, len(text)))


class FakeNer:
    """Returns predetermined spans keyed by section text."""

    def __init__(self, spans_by_text: dict[str, list[LocalSpan]]) -> None:
        self._m = spans_by_text

    @property
    def available(self) -> bool:
        return True

    def extract(self, text: str) -> list[LocalSpan]:
        return self._m.get(text, [])


class FakeContext:
    """Returns predetermined sections and per-span assertions."""

    def __init__(self, sections, assertions: dict[str, dict] | None = None) -> None:
        self._sections = sections
        self._assertions = assertions or {}

    def detect_sections(self, text: str):
        return self._sections

    def assert_spans(self, text: str, spans):
        return [SpanAssertion(span=s, **self._assertions.get(s.text, {})) for s in spans]


def _gemini_returning(entities):
    calls = {"n": 0}

    async def _extract(text: str):
        calls["n"] += 1
        return list(entities)

    return _extract, calls


# --- engine selection ------------------------------------------------------


async def test_local_engine_never_calls_gemini():
    sec = _section(SectionType.MEDICATIONS, "metformin and lisinopril")
    ner = FakeNer({sec.text: [_span("metformin", LABEL_CHEMICAL)]})
    ctx = FakeContext([sec])
    gem, calls = _gemini_returning([])

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=gem, confidence_threshold=0.6,
    )
    assert calls["n"] == 0
    assert [e.entity_class for e in result.entities] == ["medication"]
    assert result.entities[0].text == "metformin"
    assert result.stats["escalated_sections"] == 0


async def test_unsupported_engine_raises():
    with pytest.raises(ValueError):
        await ee.run_clinical_extraction(
            "x", engine="gemini", ner=FakeNer({}), context=FakeContext([]),
            gemini_section_extract=None, confidence_threshold=0.6,
        )


# --- hybrid escalation -----------------------------------------------------


async def test_hybrid_escalates_lab_section_to_gemini():
    sec = _section(SectionType.LABS, "Glucose 95 mg/dL (70-99)")
    ner = FakeNer({sec.text: []})  # local NER finds nothing useful in a lab section
    ctx = FakeContext([sec])
    lab_entity = ExtractedEntity("lab_result", "Glucose 95 mg/dL", {"test": "Glucose"})
    gem, calls = _gemini_returning([lab_entity])

    result = await ee.run_clinical_extraction(
        sec.text, engine="hybrid", ner=ner, context=ctx,
        gemini_section_extract=gem, confidence_threshold=0.6,
    )
    assert calls["n"] == 1
    assert [e.entity_class for e in result.entities] == ["lab_result"]
    assert result.stats["escalated_sections"] == 1
    # Escalated entities get tagged with their source section.
    assert result.entities[0].attributes.get("_source_section") == "labs"


async def test_hybrid_keeps_coded_medication_section_local():
    sec = _section(SectionType.MEDICATIONS, "metformin 500mg")
    ner = FakeNer({sec.text: [_span("metformin", LABEL_CHEMICAL)]})
    ctx = FakeContext([sec])
    gem, calls = _gemini_returning([ExtractedEntity("medication", "SHOULD_NOT_APPEAR")])

    result = await ee.run_clinical_extraction(
        sec.text, engine="hybrid", ner=ner, context=ctx,
        gemini_section_extract=gem, confidence_threshold=0.6,
    )
    # metformin codes to RxNorm → high confidence → stays local, no escalation.
    assert calls["n"] == 0
    assert [e.text for e in result.entities] == ["metformin"]
    assert result.stats["escalated_sections"] == 0


async def test_hybrid_escalates_low_confidence_uncoded_section():
    sec = _section(SectionType.HISTORY, "zzzqxnotaword and another zzznonsense token here")
    # Spans that resolve to NO terminology code → low section confidence.
    ner = FakeNer({sec.text: [_span("zzzqxnotaword", LABEL_CHEMICAL)]})
    ctx = FakeContext([sec])
    gem, calls = _gemini_returning([ExtractedEntity("condition", "recovered")])

    result = await ee.run_clinical_extraction(
        sec.text, engine="hybrid", ner=ner, context=ctx,
        gemini_section_extract=gem, confidence_threshold=0.6,
    )
    assert calls["n"] == 1  # uncoded → confidence 0.5 < 0.6 → escalates
    assert result.stats["escalated_sections"] == 1


async def test_local_mode_keeps_uncoded_spans_without_escalating():
    sec = _section(SectionType.HISTORY, "zzzqxnotaword token")
    ner = FakeNer({sec.text: [_span("zzzqxnotaword", LABEL_DISEASE)]})
    ctx = FakeContext([sec])

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    # local mode never escalates; the uncoded disease is still captured.
    assert [e.entity_class for e in result.entities] == ["condition"]
    assert result.stats["escalated_sections"] == 0


# --- ConText-driven disposition --------------------------------------------


async def test_family_assertion_reclassifies_condition_to_family_history():
    sec = _section(SectionType.HISTORY, "mother had breast cancer")
    ner = FakeNer({sec.text: [_span("breast cancer", LABEL_DISEASE)]})
    ctx = FakeContext([sec], assertions={"breast cancer": {"is_family": True}})

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    assert [e.entity_class for e in result.entities] == ["family_history"]


async def test_negated_condition_dropped_by_default():
    sec = _section(SectionType.HISTORY, "no evidence of diabetes")
    ner = FakeNer({sec.text: [_span("diabetes", LABEL_DISEASE)]})
    ctx = FakeContext([sec], assertions={"diabetes": {"is_negated": True}})

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    # Default disposition "drop": an absent/refuted finding is not recorded as an
    # active condition (matches the Gemini baseline + eval fixtures).
    assert result.entities == []


async def test_negated_condition_recorded_as_inactive_when_configured(monkeypatch):
    monkeypatch.setattr(ee, "NEGATED_CONDITION_DISPOSITION", "inactive")
    sec = _section(SectionType.HISTORY, "no evidence of diabetes")
    ner = FakeNer({sec.text: [_span("diabetes", LABEL_DISEASE)]})
    ctx = FakeContext([sec], assertions={"diabetes": {"is_negated": True}})

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    # With disposition "inactive", the negated condition is kept with status
    # "negated" → entity_to_fhir maps it to FHIR inactive clinicalStatus.
    assert len(result.entities) == 1
    assert result.entities[0].attributes["status"] == "negated"


async def test_hybrid_escalates_unsectioned_other_narrative():
    sec = _section(SectionType.OTHER, "pt c/o HTN on lisinopril, no chest pain, mom breast ca")
    ner = FakeNer({sec.text: [_span("HTN", LABEL_DISEASE)]})
    ctx = FakeContext([sec])
    gem, calls = _gemini_returning([ExtractedEntity("allergy", "penicillin")])

    result = await ee.run_clinical_extraction(
        sec.text, engine="hybrid", ner=ner, context=ctx,
        gemini_section_extract=gem, confidence_threshold=0.6,
    )
    # A free-text OTHER section can't be trusted to the local NER → escalates.
    assert calls["n"] == 1
    assert result.stats["escalated_sections"] == 1


async def test_hypothetical_finding_is_dropped():
    sec = _section(SectionType.HISTORY, "if you develop sepsis call us")
    ner = FakeNer({sec.text: [_span("sepsis", LABEL_DISEASE)]})
    ctx = FakeContext([sec], assertions={"sepsis": {"is_hypothetical": True}})

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    assert result.entities == []


async def test_negated_medication_is_dropped():
    sec = _section(SectionType.MEDICATIONS, "not taking metformin")
    ner = FakeNer({sec.text: [_span("metformin", LABEL_CHEMICAL)]})
    ctx = FakeContext([sec], assertions={"metformin": {"is_negated": True}})

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    assert result.entities == []


async def test_historical_condition_gets_historical_status():
    sec = _section(SectionType.HISTORY, "history of hypertension")
    ner = FakeNer({sec.text: [_span("hypertension", LABEL_DISEASE)]})
    ctx = FakeContext([sec], assertions={"hypertension": {"is_historical": True}})

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    assert result.entities[0].attributes["status"] == "historical"


# --- dedup -----------------------------------------------------------------


# --- real-model integration (no Gemini; model-gated) ----------------------


def _models_available() -> bool:
    from app.services.extraction.clinical_context import get_clinical_context
    from app.services.extraction.local_ner import get_local_ner

    return get_local_ner().available and get_clinical_context().available


_STRUCTURED_NOTE = (
    "Past Medical History:\n"
    "Type 2 diabetes mellitus, hypertension, hypothyroidism, asthma.\n\n"
    "Medications:\n"
    "metformin 500mg twice daily\n"
    "lisinopril 10mg daily\n"
    "levothyroxine 75mcg daily\n"
    "atorvastatin 20mg nightly\n"
)


@pytest.mark.skipif(not _models_available(), reason="scispaCy/medspaCy not installed")
async def test_local_engine_extracts_structured_note_without_gemini():
    """End-to-end on real models: a structured med/problem-list note yields the
    expected conditions + medications entirely on-device (no escalation)."""
    from app.services.extraction.clinical_context import get_clinical_context
    from app.services.extraction.local_ner import get_local_ner

    result = await ee.run_clinical_extraction(
        _STRUCTURED_NOTE, engine="local",
        ner=get_local_ner(), context=get_clinical_context(),
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    meds = {e.text.lower() for e in result.entities if e.entity_class == "medication"}
    conds = {e.text.lower() for e in result.entities if e.entity_class == "condition"}
    assert {"metformin", "lisinopril", "levothyroxine", "atorvastatin"} <= meds
    assert {"hypertension", "hypothyroidism", "asthma"} <= conds
    assert any("diabetes" in c for c in conds)


@pytest.mark.skipif(not _models_available(), reason="scispaCy/medspaCy not installed")
async def test_hybrid_keeps_structured_note_fully_local():
    """Hybrid must NOT escalate a clean structured note — the local fast-path
    covers it, so no Gemini callback is invoked."""
    from app.services.extraction.clinical_context import get_clinical_context
    from app.services.extraction.local_ner import get_local_ner

    calls = {"n": 0}

    async def _gem(text):
        calls["n"] += 1
        return []

    result = await ee.run_clinical_extraction(
        _STRUCTURED_NOTE, engine="hybrid",
        ner=get_local_ner(), context=get_clinical_context(),
        gemini_section_extract=_gem, confidence_threshold=0.6,
    )
    assert calls["n"] == 0
    assert result.stats["escalated_sections"] == 0


async def test_within_document_dedup_collapses_repeats():
    sec = _section(SectionType.MEDICATIONS, "metformin metformin")
    ner = FakeNer({sec.text: [
        _span("metformin", LABEL_CHEMICAL),
        _span("metformin", LABEL_CHEMICAL),
    ]})
    ctx = FakeContext([sec])

    result = await ee.run_clinical_extraction(
        sec.text, engine="local", ner=ner, context=ctx,
        gemini_section_extract=None, confidence_threshold=0.6,
    )
    assert len([e for e in result.entities if e.text == "metformin"]) == 1
