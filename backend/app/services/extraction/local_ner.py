"""Local clinical NER fast-path (WS-A).

A device-local named-entity recognizer for the two highest-volume clinical
entity types — **medications** (chemicals) and **conditions** (diseases) — so the
common case never needs a Gemini round-trip. Recognized spans are mapped to
standard codes using the *existing* bundled RxNorm/ICD-10 terminology indexes
(``terminology.py``); no UMLS dependency is introduced.

Design goals
------------
* **Swappable engine.** :class:`LocalNerEngine` is a small Protocol so the
  scispaCy implementation can later be replaced by GLiNER-biomed (or anything
  else) without touching the orchestrator. Engines emit plain :class:`LocalSpan`
  values — char offsets + a coarse label — never spaCy objects.
* **Fail-open, non-latching.** Mirrors ``phi_ner``: the model is loaded lazily as
  a singleton, a load *failure is never latched* (each call retries), and a
  missing model degrades to "no spans" rather than raising. Extraction must never
  crash because an optional ML model is absent.
* **Privacy win.** This path runs entirely on-device, so the text it handles
  never leaves the machine and needs no PHI de-identification round-trip (that
  obligation only attaches to the Gemini escalation path).

The default engine is scispaCy ``en_ner_bc5cdr_md`` (BioCreative V CDR), whose
NER produces two labels: ``CHEMICAL`` and ``DISEASE``. Everything else (labs,
vitals, procedures, allergies, imaging, social/family history, encounters,
assessment & plan) is out of scope for the local model and is handled by the
Gemini escalation path in ``hybrid`` mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.services.extraction import terminology

logger = logging.getLogger(__name__)

# Default local NER model: scispaCy en_ner_bc5cdr_md (BioCreative V CDR — CHEMICAL
# + DISEASE). Kept as a module constant rather than a config flag so adding the
# engine needs no config.py change; the orchestrator/engine accept an override.
DEFAULT_LOCAL_NER_MODEL = "en_ner_bc5cdr_md"

# scispaCy en_ner_bc5cdr_md entity labels.
LABEL_CHEMICAL = "CHEMICAL"
LABEL_DISEASE = "DISEASE"

# Map an engine-native NER label to one of our storable entity classes. Only the
# two bc5cdr labels are covered; an unknown label maps to ``None`` (ignored by
# the local path, left for Gemini escalation).
_LABEL_TO_ENTITY_CLASS: dict[str, str] = {
    LABEL_CHEMICAL: "medication",
    LABEL_DISEASE: "condition",
}


@dataclass(frozen=True)
class LocalSpan:
    """One entity span recognized by a local NER engine.

    Engine-agnostic: carries only the surface text, a coarse ``label`` (engine
    vocabulary, e.g. ``CHEMICAL``/``DISEASE``), the character offsets into the
    text the engine was given, and a best-effort ``confidence`` in ``[0, 1]``.
    scispaCy's statistical NER does not expose per-entity probabilities, so the
    raw span confidence defaults high and the *escalation* decision is driven by
    whether the span resolves to a real terminology code (see the orchestrator).
    """

    text: str
    label: str
    start_char: int
    end_char: int
    confidence: float = 0.85


@runtime_checkable
class LocalNerEngine(Protocol):
    """Pluggable local NER backend (scispaCy today, GLiNER tomorrow)."""

    @property
    def available(self) -> bool:
        """True when the underlying model is loaded and usable."""
        ...

    def extract(self, text: str) -> list[LocalSpan]:
        """Return entity spans for ``text`` (empty list if unavailable)."""
        ...


def label_to_entity_class(label: str | None) -> str | None:
    """Map an engine NER label to a storable entity class, or ``None``."""
    if not label:
        return None
    return _LABEL_TO_ENTITY_CLASS.get(label.upper())


def span_to_coding(span: LocalSpan) -> terminology.Coding | None:
    """Resolve a recognized span to a standard terminology coding.

    ``CHEMICAL`` → RxNorm via :func:`terminology.lookup_medication`;
    ``DISEASE`` → ICD-10-CM via :func:`terminology.lookup_condition`. Returns
    ``None`` for unknown labels or terms with no curated code (never a guess —
    preserves the "unknown stays uncoded" guarantee).
    """
    cls = label_to_entity_class(span.label)
    if cls == "medication":
        return terminology.lookup_medication(span.text)
    if cls == "condition":
        return terminology.lookup_condition(span.text)
    return None


class ScispacyNer:
    """:class:`LocalNerEngine` backed by a scispaCy NER model.

    The spaCy model is loaded lazily and cached. A load failure is **not
    latched** — each :meth:`extract`/:attr:`available` call re-attempts the load
    (warning logged once) so a transient failure can't silently disable the
    local path for the worker's lifetime, matching the ``phi_ner`` posture.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or DEFAULT_LOCAL_NER_MODEL
        self._nlp = None
        self._warned = False

    def _load(self):
        if self._nlp is not None:
            return self._nlp
        try:
            import spacy

            self._nlp = spacy.load(self._model_name)
            self._warned = False
            return self._nlp
        except Exception:  # noqa: BLE001 - missing model must not break extraction
            if not self._warned:
                logger.warning(
                    "scispaCy model %r unavailable; local NER disabled this call "
                    "(will retry; Gemini path unaffected)",
                    self._model_name,
                    exc_info=True,
                )
                self._warned = True
            return None

    @property
    def available(self) -> bool:
        return self._load() is not None

    def warm_load(self) -> bool:
        """Eagerly load the model (call at startup). Returns True when ready."""
        return self._load() is not None

    def extract(self, text: str) -> list[LocalSpan]:
        if not text or not text.strip():
            return []
        nlp = self._load()
        if nlp is None:
            return []
        doc = nlp(text)
        return [
            LocalSpan(
                text=ent.text,
                label=ent.label_,
                start_char=ent.start_char,
                end_char=ent.end_char,
            )
            for ent in doc.ents
        ]


# Process-wide singleton, lazily constructed. Non-latching: the engine object is
# cheap; the expensive model load inside it is what retries.
_ENGINE: ScispacyNer | None = None


def get_local_ner() -> ScispacyNer:
    """Return the shared scispaCy NER engine (constructed on first use)."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ScispacyNer()
    return _ENGINE


def warm_load_local_ner() -> bool:
    """Eagerly load the local NER model at startup. Returns True when ready."""
    return get_local_ner().warm_load()
