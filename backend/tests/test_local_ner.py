"""Tests for the local clinical NER fast-path (WS-A).

The pure mapping layer (label → entity class, span → terminology coding) is
model-independent and always runs. The scispaCy NER itself is exercised only
when the model is installed; otherwise those tests skip (fail-open contract).
"""
from __future__ import annotations

import pytest

from app.services.extraction.local_ner import (
    LABEL_CHEMICAL,
    LABEL_DISEASE,
    LocalNerEngine,
    LocalSpan,
    ScispacyNer,
    get_local_ner,
    label_to_entity_class,
    span_to_coding,
)


def _span(text: str, label: str) -> LocalSpan:
    return LocalSpan(text=text, label=label, start_char=0, end_char=len(text))


# --- label → entity class --------------------------------------------------


def test_label_maps_chemical_to_medication():
    assert label_to_entity_class(LABEL_CHEMICAL) == "medication"


def test_label_maps_disease_to_condition():
    assert label_to_entity_class(LABEL_DISEASE) == "condition"


def test_label_mapping_is_case_insensitive():
    assert label_to_entity_class("chemical") == "medication"
    assert label_to_entity_class("Disease") == "condition"


def test_unknown_label_maps_to_none():
    assert label_to_entity_class("GENE") is None
    assert label_to_entity_class(None) is None


# --- span → terminology coding (uses the bundled RxNorm/ICD-10 indexes) -----


def test_chemical_span_codes_to_rxnorm_medication():
    coding = span_to_coding(_span("metformin", LABEL_CHEMICAL))
    assert coding is not None
    # RxNorm system; non-empty code.
    assert "rxnorm" in coding.system.lower()
    assert coding.code


def test_disease_span_codes_to_icd10_condition():
    coding = span_to_coding(_span("hypertension", LABEL_DISEASE))
    assert coding is not None
    assert coding.code


def test_unknown_term_stays_uncoded():
    # A nonsense token must never receive a (wrong) code.
    assert span_to_coding(_span("zzzqxnotaword", LABEL_CHEMICAL)) is None


def test_unknown_label_span_is_uncoded():
    assert span_to_coding(_span("anything", "GENE")) is None


# --- engine contract -------------------------------------------------------


def test_engine_singleton_is_stable():
    assert get_local_ner() is get_local_ner()


def test_scispacy_engine_satisfies_protocol():
    assert isinstance(ScispacyNer(), LocalNerEngine)


def test_engine_extract_empty_text_returns_empty():
    # No model load required for empty/whitespace input.
    assert ScispacyNer().extract("") == []
    assert ScispacyNer().extract("   ") == []


# --- scispaCy NER (model-gated) --------------------------------------------


def _model_available() -> bool:
    return get_local_ner().available


@pytest.mark.skipif(not _model_available(), reason="scispaCy en_ner_bc5cdr_md not installed")
def test_scispacy_recognizes_chemical_and_disease():
    spans = get_local_ner().extract(
        "Patient takes metformin for type 2 diabetes mellitus."
    )
    labels = {s.label for s in spans}
    texts = " ".join(s.text.lower() for s in spans)
    assert spans, "expected at least one entity span"
    assert LABEL_CHEMICAL in labels or LABEL_DISEASE in labels
    assert "metformin" in texts or "diabetes" in texts


@pytest.mark.skipif(not _model_available(), reason="scispaCy en_ner_bc5cdr_md not installed")
def test_scispacy_spans_resolve_to_codes():
    spans = get_local_ner().extract("Started lisinopril for hypertension.")
    coded = [span_to_coding(s) for s in spans]
    assert any(c is not None for c in coded)
