from __future__ import annotations

from app.services.extraction.entity_extractor import ExtractedEntity
from app.services.extraction.eval.scorer import normalize, score


def _ext(cls, text, **attrs):
    return ExtractedEntity(entity_class=cls, text=text, attributes=attrs)


def test_normalize_lowercases_and_collapses():
    assert normalize("  Type 2  DIABETES. ") == "type 2 diabetes"


def test_normalize_synonyms():
    assert normalize("HTN") == "hypertension"
    assert normalize("DM2") == "type 2 diabetes"


def test_perfect_match_scores_one():
    gt = {"expected": [
        {"entity_class": "condition", "text": "hypertension"},
        {"entity_class": "medication", "text": "lisinopril"},
    ]}
    extracted = [_ext("condition", "Hypertension"), _ext("medication", "lisinopril")]
    rep = score(gt, extracted)
    assert rep.overall.precision == 1.0 and rep.overall.recall == 1.0 and rep.overall.f1 == 1.0


def test_missed_entity_drops_recall():
    gt = {"expected": [
        {"entity_class": "condition", "text": "hypertension"},
        {"entity_class": "medication", "text": "lisinopril"},
    ]}
    rep = score(gt, [_ext("condition", "hypertension")])
    assert rep.overall.recall == 0.5
    assert any(m["text"] == "lisinopril" for m in rep.missed)


def test_extra_entity_drops_precision():
    gt = {"expected": [{"entity_class": "condition", "text": "hypertension"}]}
    rep = score(gt, [_ext("condition", "hypertension"), _ext("condition", "asthma")])
    assert rep.overall.precision == 0.5


def test_synonym_match_counts_as_hit():
    gt = {"expected": [{"entity_class": "condition", "text": "hypertension"}]}
    rep = score(gt, [_ext("condition", "HTN")])
    assert rep.overall.recall == 1.0


def test_partial_medication_match():
    gt = {"expected": [{"entity_class": "medication", "text": "omeprazole"}]}
    rep = score(gt, [_ext("medication", "omeprazole 20mg")])
    assert rep.overall.recall == 1.0


def test_per_type_breakdown():
    gt = {"expected": [
        {"entity_class": "condition", "text": "hypertension"},
        {"entity_class": "medication", "text": "lisinopril"},
    ]}
    rep = score(gt, [_ext("condition", "hypertension")])
    assert rep.per_type["condition"].recall == 1.0
    assert rep.per_type["medication"].recall == 0.0


def test_false_extraction_of_attribution_trap():
    gt = {
        "expected": [],
        "must_not_extract": [
            {"entity_class": "condition", "text": "colon cancer", "reason": "attribution"}
        ],
    }
    rep = score(gt, [_ext("condition", "colon cancer")])
    assert rep.false_extractions
    assert rep.attribution_accuracy == 0.0


def test_attribution_trap_respected():
    gt = {
        "expected": [],
        "must_not_extract": [
            {"entity_class": "condition", "text": "colon cancer", "reason": "attribution"}
        ],
    }
    rep = score(gt, [])
    assert rep.false_extractions == []
    assert rep.attribution_accuracy == 1.0


def test_negation_trap_respected_and_violated():
    gt = {
        "expected": [],
        "must_not_extract": [
            {"entity_class": "condition", "text": "diabetes", "reason": "negation"}
        ],
    }
    assert score(gt, []).negation_accuracy == 1.0
    bad = score(gt, [_ext("condition", "diabetes")])
    assert bad.negation_accuracy == 0.0
    assert bad.false_extractions


def test_expected_family_history_present():
    gt = {"expected": [], "expected_family_history": [{"text": "colon cancer"}]}
    assert score(gt, [_ext("family_history", "colon cancer")]).attribution_accuracy == 1.0
    assert score(gt, []).attribution_accuracy == 0.0
