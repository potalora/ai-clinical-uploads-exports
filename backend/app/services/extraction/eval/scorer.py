"""Pure scorer for clinical entity-extraction quality evaluation.

Compares ground-truth labels against extracted entities and returns precision/recall/F1
(overall + per type) plus negation and speaker-attribution accuracy. Deterministic; no I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.extraction.entity_extractor import ExtractedEntity

_SYNONYMS = {
    "htn": "hypertension",
    "dm2": "type 2 diabetes",
    "t2dm": "type 2 diabetes",
    "dm": "diabetes",
    "sob": "shortness of breath",
    "cp": "chest pain",
    "gerd": "gastroesophageal reflux disease",
    # Fix A — pharmacy abbreviation
    "pcn": "penicillin",
    # Fix A — oncology abbreviations (whole-word substitution handles substrings too)
    "breast ca": "breast cancer",
    "colon ca": "colon cancer",
    "ca": "cancer",
}

# Fix B — entity classes that map to None in ENTITY_TO_RECORD_TYPE (provider, dosage,
# route, frequency, duration, date).  These are attribute-only / non-storable sub-entities
# produced by the extractor that should never count as false positives against a ground-truth
# set which only contains storable record-level entities.
# Mirrors the None-mapped classes in app.services.extraction.entity_to_fhir.ENTITY_TO_RECORD_TYPE.
_NON_SCORED_CLASSES: frozenset[str] = frozenset(
    {"provider", "dosage", "route", "frequency", "duration", "date"}
)

# Regex used for spoken blood pressure normalization (Fix A).
_SPOKEN_BP_RE = re.compile(r"(\d+)\s+over\s+(\d+)")


def normalize(text: str) -> str:
    t = (text or "").lower()
    # Fix A — convert spoken BP "142 over 90" → "142/90" before punctuation stripping
    t = _SPOKEN_BP_RE.sub(r"\1/\2", t)
    t = re.sub(r"[^\w\s/]", " ", t)  # keep "/" so "142/90" survives
    t = re.sub(r"\s+", " ", t).strip()
    # Fix A — apply synonyms as whole-word substring replacements so both whole-string
    # ("pcn" → "penicillin") and substring ("mom breast ca" → "mom breast cancer") work.
    for src, dst in _SYNONYMS.items():
        t = re.sub(r"\b" + re.escape(src) + r"\b", dst, t)
    return t


def _texts_match(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


@dataclass
class PRF:
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


def _prf(tp: int, fp: int, fn: int) -> PRF:
    precision = tp / (tp + fp) if (tp + fp) else (1.0 if fn == 0 else 0.0)
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return PRF(round(precision, 4), round(recall, 4), round(f1, 4))


@dataclass
class EvalReport:
    overall: PRF
    per_type: dict[str, PRF]
    negation_accuracy: float
    attribution_accuracy: float
    false_extractions: list[dict] = field(default_factory=list)
    missed: list[dict] = field(default_factory=list)


def _matches(item: dict, extracted: list[ExtractedEntity]) -> bool:
    return any(
        e.entity_class == item["entity_class"] and _texts_match(e.text, item["text"])
        for e in extracted
    )


def score(ground_truth: dict[str, Any], extracted: list[ExtractedEntity]) -> EvalReport:
    expected: list[dict] = ground_truth.get("expected", [])
    must_not: list[dict] = ground_truth.get("must_not_extract", [])
    expected_fh: list[dict] = ground_truth.get("expected_family_history", [])

    # Fix B — exclude non-storable sub-entities from precision / FP accounting.
    scored_extracted = [e for e in extracted if e.entity_class not in _NON_SCORED_CLASSES]

    matched_expected = [e for e in expected if _matches(e, scored_extracted)]
    missed = [e for e in expected if e not in matched_expected]
    tp = len(matched_expected)
    fn = len(missed)
    fp = sum(
        1 for e in scored_extracted
        if not any(
            e.entity_class == x["entity_class"] and _texts_match(e.text, x["text"])
            for x in expected
        )
    )
    overall = _prf(tp, fp, fn)

    per_type: dict[str, PRF] = {}
    for cls in {x["entity_class"] for x in expected}:
        exp_c = [x for x in expected if x["entity_class"] == cls]
        # Fix B — also exclude non-storable classes from per-type FP count
        ext_c = [e for e in scored_extracted if e.entity_class == cls]
        t = sum(1 for x in exp_c if _matches(x, scored_extracted))
        f = sum(1 for e in ext_c if not any(_texts_match(e.text, x["text"]) for x in exp_c))
        per_type[cls] = _prf(t, f, len(exp_c) - t)

    false_extractions = [m for m in must_not if _matches(m, extracted)]

    neg = [m for m in must_not if m.get("reason") == "negation"]
    neg_violated = [m for m in neg if _matches(m, extracted)]
    negation_accuracy = 1.0 if not neg else round(1 - len(neg_violated) / len(neg), 4)

    attr = [m for m in must_not if m.get("reason") == "attribution"]
    attr_violated = [m for m in attr if _matches(m, extracted)]
    fh_present = sum(
        1 for fh in expected_fh
        if any(e.entity_class == "family_history" and _texts_match(e.text, fh["text"]) for e in extracted)
    )
    attr_total = len(attr) + len(expected_fh)
    attr_correct = (len(attr) - len(attr_violated)) + fh_present
    attribution_accuracy = 1.0 if attr_total == 0 else round(attr_correct / attr_total, 4)

    return EvalReport(
        overall=overall,
        per_type=per_type,
        negation_accuracy=negation_accuracy,
        attribution_accuracy=attribution_accuracy,
        false_extractions=false_extractions,
        missed=missed,
    )
