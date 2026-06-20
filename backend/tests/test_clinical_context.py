"""Tests for the medspaCy clinical-context stage (WS-A).

Two parts:

1. **Postprocess parity** — the drop-rules migrated from ``entity_validator``
   must behave identically through the new stage API (``postprocess_entities``).
   These are model-independent and always run.
2. **ConText + section detection** — exercised only when medspaCy is installed
   (the stage fails open otherwise), so these skip when the pipeline can't load.
"""
from __future__ import annotations

import pytest

from app.services.extraction.clinical_context import (
    get_clinical_context,
    postprocess_entities,
)
from app.services.extraction.entity_extractor import ExtractedEntity
from app.services.extraction.local_ner import LABEL_DISEASE, LocalSpan
from app.services.extraction.section_parser import SectionType


def _e(entity_class: str, text: str, **attrs) -> ExtractedEntity:
    return ExtractedEntity(entity_class=entity_class, text=text, attributes=dict(attrs))


def _texts(entities) -> list[str]:
    return [e.text for e in entities]


# ===========================================================================
# Part 1 — postprocess drop-rule parity (migrated from test_entity_validator)
# ===========================================================================


def test_postprocess_drops_phi_placeholders():
    out = postprocess_entities([
        _e("procedure", "[NAME] (12+ YO)"),
        _e("condition", "[DATE]"),
        _e("medication", "[PATIENT]"),
        _e("condition", "Hypertension"),
    ])
    assert _texts(out) == ["Hypertension"]


def test_postprocess_drops_mentioned_not_performed_procedure():
    assert postprocess_entities([_e("procedure", "Colonoscopy")]) == []
    assert postprocess_entities([_e("procedure", "recommend colonoscopy")]) == []


def test_postprocess_keeps_performed_procedure():
    assert len(postprocess_entities([_e("procedure", "s/p Cystectomy")])) == 1
    assert len(postprocess_entities([_e("procedure", "Appendectomy")])) == 1
    assert len(postprocess_entities([_e("procedure", "Colonoscopy", date="01/2024")])) == 1


@pytest.mark.parametrize("text", ["2mg", "120/80", "98.6", "140"])
def test_postprocess_drops_value_only_fragments(text):
    assert postprocess_entities([_e("observation", text)]) == []


@pytest.mark.parametrize("text", ["CBC", "CMP", "A1c", "FIT"])
def test_postprocess_keeps_named_valueless_panels(text):
    assert _texts(postprocess_entities([_e("lab_result", text)])) == [text]


def test_postprocess_reclassifies_lifestyle_to_social_history():
    out = postprocess_entities([_e("observation", "Exercise: Tennis player")])
    assert len(out) == 1
    assert out[0].entity_class == "social_history"
    assert out[0].attributes.get("category") == "exercise"


def test_postprocess_drops_directive_counseling():
    assert postprocess_entities([_e("observation", "Alcohol: avoid alcohol")]) == []


@pytest.mark.parametrize("text", ["Go", "PPI", "SSRI", "NSAID", "LDN", "x7"])
def test_postprocess_drops_non_drug_medication_tokens(text):
    assert postprocess_entities([_e("medication", text)]) == []


@pytest.mark.parametrize("text", ["D", "K", "A", "C", "E"])
def test_postprocess_drops_bare_single_letter_supplements(text):
    assert postprocess_entities([_e("medication", text)]) == []


@pytest.mark.parametrize("text", ["B12", "D3", "vitamin D", "folate", "omega-3", "CoQ10"])
def test_postprocess_keeps_vitamins_and_supplements(text):
    assert _texts(postprocess_entities([_e("medication", text)])) == [text]


@pytest.mark.parametrize("text", ["Metformin", "Omeprazole", "Lisinopril"])
def test_postprocess_keeps_real_drug_names(text):
    assert _texts(postprocess_entities([_e("medication", text)])) == [text]


def test_postprocess_preserves_order_of_survivors():
    out = postprocess_entities([
        _e("condition", "Diabetes", status="active"),
        _e("procedure", "Colonoscopy"),  # dropped
        _e("medication", "Metformin"),
    ])
    assert _texts(out) == ["Diabetes", "Metformin"]


# ===========================================================================
# Part 2 — ConText assertions + section detection (medspaCy-gated)
# ===========================================================================


def _medspacy_available() -> bool:
    return get_clinical_context().available


skip_no_medspacy = pytest.mark.skipif(
    not _medspacy_available(), reason="medspaCy not installed"
)


def _span(text: str, full_text: str, label: str = LABEL_DISEASE) -> LocalSpan:
    i = full_text.find(text)
    return LocalSpan(text=text, label=label, start_char=i, end_char=i + len(text))


@skip_no_medspacy
def test_context_flags_negation():
    text = "No chest pain today. Patient denies diabetes."
    ctx = get_clinical_context()
    spans = [_span("chest pain", text), _span("diabetes", text)]
    asserts = ctx.assert_spans(text, spans)
    assert all(a.is_negated for a in asserts), asserts


@skip_no_medspacy
def test_context_flags_family():
    text = "Mother had breast cancer. Father with colon cancer."
    ctx = get_clinical_context()
    spans = [_span("breast cancer", text), _span("colon cancer", text)]
    asserts = ctx.assert_spans(text, spans)
    assert all(a.is_family for a in asserts), asserts


@skip_no_medspacy
def test_context_flags_historical():
    text = "History of asthma in childhood."
    ctx = get_clinical_context()
    asserts = ctx.assert_spans(text, [_span("asthma", text)])
    assert asserts[0].is_historical


@skip_no_medspacy
def test_context_affirmed_finding_has_no_flags():
    text = "Patient has hypertension."
    ctx = get_clinical_context()
    a = ctx.assert_spans(text, [_span("hypertension", text)])[0]
    assert not (a.is_negated or a.is_family or a.is_historical or a.is_hypothetical)


@skip_no_medspacy
def test_detect_sections_identifies_known_headers():
    text = (
        "Past Medical History:\nType 2 diabetes, hypertension.\n\n"
        "Medications:\nlisinopril 10mg daily.\n\n"
        "Family History:\nMother: breast cancer.\n"
    )
    sections = get_clinical_context().detect_sections(text)
    cats = {s.section_type for s in sections}
    assert SectionType.MEDICATIONS in cats
    assert SectionType.HISTORY in cats
    assert SectionType.FAMILY_HISTORY in cats
    # Full coverage: section texts are non-empty slices of the document.
    assert all(s.text.strip() for s in sections)


@skip_no_medspacy
def test_detect_sections_falls_back_to_other_for_headerless_text():
    sections = get_clinical_context().detect_sections("just some free text with no headers")
    assert len(sections) == 1
    assert sections[0].section_type == SectionType.OTHER


def test_detect_sections_handles_empty_text():
    # Model-independent: empty input always yields a single OTHER section.
    sections = get_clinical_context().detect_sections("")
    assert len(sections) == 1
    assert sections[0].section_type == SectionType.OTHER
