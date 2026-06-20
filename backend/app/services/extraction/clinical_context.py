"""medspaCy-based clinical context stage (WS-A).

Replaces three hand-rolled pieces of the extraction pipeline with validated OSS
(`medspaCy <https://github.com/medspacy/medspacy>`_), used **only** on the local
extraction fast-path:

1. **Section detection** (``medspacy_sectionizer``) → replaces the Gemini-powered
   ``section_parser`` for the local path (rule-based, on-device, milliseconds —
   no LLM round-trip).
2. **ConText assertion** (``medspacy_context``) → replaces the negation +
   family/experiencer guards previously delegated to the Gemini prompt. Negated
   findings are flagged (a negated condition still maps to FHIR ``inactive``
   clinicalStatus downstream — see ``entity_to_fhir``); family-attributed
   findings are flagged so they become ``family_history`` instead of an active
   condition; hypothetical mentions are flagged for dropping.
3. **Postprocess drop-rules** (:func:`postprocess_entities`) → the precision
   guards that drop/repair over-extracted entities. To keep parity *provable*,
   these reuse the proven, engine-agnostic ``entity_validator`` logic; the
   migrated test (``test_clinical_context``) exercises the same expectations
   through this stage's API.

Posture mirrors ``phi_ner``: the spaCy pipeline is a lazily-loaded singleton,
load failure is **non-latching** (each call retries; warned once), and a missing
library degrades gracefully (sections collapse to a single ``OTHER`` block; no
assertions) rather than raising. The local extraction path must never crash
because an optional component is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.extraction.entity_extractor import ExtractedEntity
from app.services.extraction.entity_validator import validate_entities
from app.services.extraction.local_ner import LocalSpan
from app.services.extraction.section_parser import ParsedSection, SectionType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpanAssertion:
    """ConText assertion outcome for one span (all default ``False``)."""

    span: LocalSpan
    is_negated: bool = False
    is_family: bool = False
    is_historical: bool = False
    is_hypothetical: bool = False
    is_uncertain: bool = False


# medspaCy default section categories → our SectionType vocabulary. Unknown /
# None (preamble, unrecognized headers) fall through to OTHER.
_MEDSPACY_TO_SECTION: dict[str, SectionType] = {
    "medications": SectionType.MEDICATIONS,
    "allergies": SectionType.ALLERGIES,
    "past_medical_history": SectionType.HISTORY,
    "history_of_present_illness": SectionType.HISTORY,
    "problem_list": SectionType.ASSESSMENT,
    "diagnoses": SectionType.ASSESSMENT,
    "medical_assessment": SectionType.ASSESSMENT,
    "assessment_and_plan": SectionType.ASSESSMENT_PLAN,
    "observation_and_plan": SectionType.ASSESSMENT_PLAN,
    "labs_and_studies": SectionType.LABS,
    "imaging": SectionType.IMAGING,
    "vital_signs": SectionType.VITALS,
    "physical_exam": SectionType.PHYSICAL_EXAM,
    "review_of_systems": SectionType.REVIEW_OF_SYSTEMS,
    "family_history": SectionType.FAMILY_HISTORY,
    "social_history": SectionType.SOCIAL_HISTORY,
    "past_surgical_history": SectionType.PROCEDURES,
    "surgical_history": SectionType.PROCEDURES,
    "chief_complaint": SectionType.CLINICAL_NOTE,
    "hospital_course": SectionType.CLINICAL_NOTE,
}


def _map_section_category(category: str | None) -> SectionType:
    if not category:
        return SectionType.OTHER
    return _MEDSPACY_TO_SECTION.get(category, SectionType.OTHER)


class ClinicalContext:
    """Lazily-loaded medspaCy pipeline for sections + ConText assertions."""

    def __init__(self) -> None:
        self._nlp = None
        self._warned = False

    def _load(self):
        if self._nlp is not None:
            return self._nlp
        try:
            import medspacy  # noqa: F401 - importing registers the spaCy factories
            import spacy

            nlp = spacy.blank("en")
            nlp.add_pipe("sentencizer")  # ConText scopes modifiers by sentence
            nlp.add_pipe("medspacy_context")
            nlp.add_pipe("medspacy_sectionizer")
            self._nlp = nlp
            self._warned = False
            return nlp
        except Exception:  # noqa: BLE001 - missing medspaCy must not break extraction
            if not self._warned:
                logger.warning(
                    "medspaCy unavailable; clinical-context stage disabled this "
                    "call (sections collapse to OTHER, no assertions; will retry)",
                    exc_info=True,
                )
                self._warned = True
            return None

    @property
    def available(self) -> bool:
        return self._load() is not None

    def warm_load(self) -> bool:
        """Eagerly build the pipeline at startup. Returns True when ready."""
        return self._load() is not None

    # -- section detection --------------------------------------------------

    def detect_sections(self, text: str) -> list[ParsedSection]:
        """Segment ``text`` into clinical sections (rule-based, no LLM).

        Returns full-coverage :class:`ParsedSection` objects (the same shape the
        Gemini ``section_parser`` produces) so downstream code is engine-agnostic.
        Falls back to a single ``OTHER`` section if medspaCy is unavailable or the
        text is trivial.
        """
        if not text or not text.strip():
            return [ParsedSection(SectionType.OTHER, "Full Document", text or "", (0, len(text or "")))]

        nlp = self._load()
        if nlp is None:
            return [ParsedSection(SectionType.OTHER, "Full Document", text, (0, len(text)))]

        try:
            doc = nlp(text)
        except Exception:  # noqa: BLE001
            logger.warning("medspaCy section detection failed; single OTHER section", exc_info=True)
            return [ParsedSection(SectionType.OTHER, "Full Document", text, (0, len(text)))]

        sections: list[ParsedSection] = []
        for sec in doc._.sections:
            title_span = doc[sec.title_start:sec.title_end]
            body_span = doc[sec.body_start:sec.body_end]
            if len(title_span):
                start_char = title_span.start_char
            elif len(body_span):
                start_char = body_span.start_char
            else:
                continue
            end_char = body_span.end_char if len(body_span) else start_char
            section_text = text[start_char:end_char]
            if not section_text.strip():
                continue
            title = title_span.text.strip() if len(title_span) else "Preamble"
            sections.append(
                ParsedSection(
                    _map_section_category(sec.category),
                    title or "Preamble",
                    section_text,
                    (start_char, end_char),
                )
            )

        if not sections:
            return [ParsedSection(SectionType.OTHER, "Full Document", text, (0, len(text)))]
        return sections

    # -- ConText assertion --------------------------------------------------

    def assert_spans(self, text: str, spans: list[LocalSpan]) -> list[SpanAssertion]:
        """Annotate ``spans`` (char offsets into ``text``) with ConText flags.

        Returns one :class:`SpanAssertion` per input span, in order. If medspaCy
        is unavailable or a span can't be aligned, the assertion defaults to all
        ``False`` (affirmed) — fail-open: an unasserted finding is treated as a
        present finding, never dropped by accident.
        """
        if not spans:
            return []
        nlp = self._load()
        if nlp is None:
            return [SpanAssertion(span=s) for s in spans]

        try:
            from spacy.util import filter_spans

            doc = nlp.make_doc(text)
            doc = nlp.get_pipe("sentencizer")(doc)
            created: list = []
            for s in spans:
                cspan = doc.char_span(
                    s.start_char, s.end_char, label=s.label, alignment_mode="expand"
                )
                if cspan is not None:
                    created.append(cspan)
            doc.ents = filter_spans(created)
            doc = nlp.get_pipe("medspacy_context")(doc)
        except Exception:  # noqa: BLE001
            logger.warning("ConText assertion failed; treating all spans as affirmed", exc_info=True)
            return [SpanAssertion(span=s) for s in spans]

        # Index asserted ents by their char offsets for matching back to inputs.
        by_offset: dict[tuple[int, int], object] = {(e.start_char, e.end_char): e for e in doc.ents}

        out: list[SpanAssertion] = []
        for s in spans:
            ent = by_offset.get((s.start_char, s.end_char))
            if ent is None:
                # Find an ent overlapping the input span (expand alignment may
                # have shifted offsets).
                ent = next(
                    (e for e in doc.ents if e.start_char <= s.start_char < e.end_char
                     or s.start_char <= e.start_char < s.end_char),
                    None,
                )
            if ent is None:
                out.append(SpanAssertion(span=s))
                continue
            out.append(
                SpanAssertion(
                    span=s,
                    is_negated=bool(ent._.is_negated),
                    is_family=bool(ent._.is_family),
                    is_historical=bool(ent._.is_historical),
                    is_hypothetical=bool(ent._.is_hypothetical),
                    is_uncertain=bool(ent._.is_uncertain),
                )
            )
        return out


# Process-wide singleton, lazily constructed.
_CONTEXT: ClinicalContext | None = None


def get_clinical_context() -> ClinicalContext:
    """Return the shared :class:`ClinicalContext` (constructed on first use)."""
    global _CONTEXT
    if _CONTEXT is None:
        _CONTEXT = ClinicalContext()
    return _CONTEXT


def warm_load_clinical_context() -> bool:
    """Eagerly build the medspaCy pipeline at startup. True when ready."""
    return get_clinical_context().warm_load()


# -- Postprocess drop-rules (parity with entity_validator) ------------------


def postprocess_entities(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
    """Apply the precision drop-rules of the clinical-context stage.

    Equivalent to the legacy ``entity_validator.validate_entities`` backstop:
    drops mentioned-not-performed procedures, value-only fragments, lifestyle-
    as-observation, drug-class/garbage medications, and PHI-placeholder entities;
    reclassifies lifestyle observations to social_history. The logic is reused
    verbatim (engine-agnostic, lexical) so parity with the prior behavior is
    provable — the migrated guard tests run the same cases through this entry
    point.
    """
    return validate_entities(entities)
