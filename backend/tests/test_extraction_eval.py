"""Baseline extraction-quality evaluation.

Runs the real LangExtract extractor on labeled synthetic fixtures and scores
the output with the pure scorer. Logs P/R/F1, negation accuracy, attribution
accuracy, and the specific false extractions / missed entities so that the
results can be captured as a baseline findings doc.

Marked @pytest.mark.slow — requires GEMINI_API_KEY and an active network
connection. Run with:

    cd backend && .venv/bin/python -m pytest tests/test_extraction_eval.py \\
        -v -m slow -rs -s
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.config import settings
from app.services.extraction.entity_extractor import extract_entities_async
from app.services.extraction.eval.scorer import score

logger = logging.getLogger(__name__)

_FIX = Path(__file__).resolve().parent / "fixtures" / "extraction_eval"
_PAIRS = [
    ("transcript_visit.txt", "transcript_visit.expected.json"),
    ("phone_note.txt", "phone_note.expected.json"),
]


@pytest.mark.slow
@pytest.mark.skipif(not settings.gemini_api_key, reason="GEMINI_API_KEY required")
@pytest.mark.parametrize("txt,gt", _PAIRS)
@pytest.mark.asyncio
async def test_baseline_extraction_quality(txt: str, gt: str) -> None:
    """Run the extractor on each labeled fixture and assert a loose recall floor.

    The hard assertion (recall >= 0.5) is a safety net only — the primary
    purpose of this test is to MEASURE and LOG the baseline numbers that will
    be captured in the findings doc. False extractions are logged but NOT
    hard-asserted at this stage; that gate belongs to a later improvement task.
    """
    text = (_FIX / txt).read_text()
    ground_truth = json.loads((_FIX / gt).read_text())

    result = await extract_entities_async(text, txt, settings.gemini_api_key)
    rep = score(ground_truth, result.entities)

    logger.warning(
        "[eval %s] P=%.2f R=%.2f F1=%.2f negation=%.2f attribution=%.2f"
        " | false=%s | missed=%s | extracted=%s",
        txt,
        rep.overall.precision,
        rep.overall.recall,
        rep.overall.f1,
        rep.negation_accuracy,
        rep.attribution_accuracy,
        [f"{m['entity_class']}:{m['text']}" for m in rep.false_extractions],
        [f"{m['entity_class']}:{m['text']}" for m in rep.missed],
        [f"{e.entity_class}:{e.text}" for e in result.entities],
    )

    assert rep.overall.recall >= 0.5, (
        f"recall floor breached for {txt}: {rep.overall}"
    )
    # Attribution floor: trivially >= 0 but makes the assertion explicit so
    # future regressions are visible in the diff.
    assert rep.attribution_accuracy >= 0.0
