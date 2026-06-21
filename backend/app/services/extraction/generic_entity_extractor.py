from __future__ import annotations

import json
import logging
from collections.abc import Callable

from app.services.ai.llm import LLMConfig, LLMMessage, LLMRequest, get_provider
from app.services.extraction.clinical_examples import CLINICAL_EXTRACTION_PROMPT
from app.services.extraction.entity_extractor import ExtractedEntity, ExtractionResult

logger = logging.getLogger(__name__)

_SCHEMA_HINT = """
Return ONLY JSON of the form:
{"entities": [{"entity_class": "<medication|condition|procedure|lab|vital|allergy|provider>",
  "text": "<verbatim span>", "attributes": {"<k>": "<v>", "confidence": 0.0-1.0}}]}
Extract only entities explicitly present. Do not infer. Omit negated/family-history items
as performed/active. If none, return {"entities": []}.
"""


async def generic_extract_entities_async(
    text: str,
    source_file: str,
    progress_callback: Callable[[str, int, int], None] | None = None,
    config: LLMConfig | None = None,
) -> ExtractionResult:
    """Provider-agnostic clinical entity extraction via JSON-mode completion.

    ``config`` carries the per-user resolved routing/credentials; when ``None``
    the global ``.env`` config is used (back-compat).
    """
    llm = get_provider("extraction", config or LLMConfig.from_settings())
    prompt = f"{CLINICAL_EXTRACTION_PROMPT}\n{_SCHEMA_HINT}\n\nTEXT:\n{text}"
    try:
        resp = await llm.complete(
            LLMRequest(
                messages=[LLMMessage("user", prompt)],
                model="",
                max_output_tokens=4096,
                temperature=0.0,
                json_mode=True,
            )
        )
        data = json.loads(resp.text)
        raw = data.get("entities", []) if isinstance(data, dict) else []
        entities: list[ExtractedEntity] = []
        for item in raw:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            attrs = item.get("attributes") or {}
            conf = 0.8
            try:
                conf = max(0.0, min(1.0, float(attrs.get("confidence", 0.8))))
            except (ValueError, TypeError):
                pass
            entities.append(
                ExtractedEntity(
                    entity_class=str(item.get("entity_class", "other")),
                    text=str(item["text"]),
                    attributes=attrs,
                    confidence=conf,
                )
            )
        if progress_callback is not None:
            try:
                progress_callback("extracting_entities", 1, len(entities))
            except Exception:  # progress is best-effort, never fail extraction
                logger.debug("progress_callback raised; ignoring", exc_info=True)
        return ExtractionResult(
            source_file=source_file,
            source_text=text,
            entities=entities,
        )
    except Exception as e:
        logger.error("Generic entity extraction failed for %s: %s", source_file, e)
        return ExtractionResult(source_file=source_file, source_text=text, error=str(e))
