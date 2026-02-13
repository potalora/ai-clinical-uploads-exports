from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import langextract as lx

from app.config import settings
from app.services.extraction.clinical_examples import (
    CLINICAL_EXAMPLES,
    CLINICAL_EXTRACTION_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """A single entity extracted from clinical text."""

    entity_class: str
    text: str
    attributes: dict = field(default_factory=dict)
    start_pos: int | None = None
    end_pos: int | None = None
    confidence: float = 0.8


@dataclass
class ExtractionResult:
    """Result of entity extraction from a document."""

    source_file: str
    source_text: str
    entities: list[ExtractedEntity] = field(default_factory=list)
    error: str | None = None


def extract_entities(text: str, source_file: str, api_key: str) -> ExtractionResult:
    """Extract clinical entities from text using LangExtract.

    This is synchronous because LangExtract is synchronous.
    Use extract_entities_async() from async callers.
    """
    try:
        result = lx.extract(
            text_or_documents=text,
            prompt_description=CLINICAL_EXTRACTION_PROMPT,
            examples=CLINICAL_EXAMPLES,
            model_id=settings.gemini_extraction_model,
            api_key=api_key,
            max_char_buffer=2000,
            max_workers=4,
        )

        entities = []
        for extraction in result.extractions:
            start_pos = None
            end_pos = None
            if extraction.char_interval:
                start_pos = extraction.char_interval.start_pos
                end_pos = extraction.char_interval.end_pos

            entities.append(
                ExtractedEntity(
                    entity_class=extraction.extraction_class,
                    text=extraction.extraction_text,
                    attributes=extraction.attributes or {},
                    start_pos=start_pos,
                    end_pos=end_pos,
                )
            )

        logger.info(
            "Extracted %d entities from %s", len(entities), source_file
        )
        return ExtractionResult(
            source_file=source_file,
            source_text=text,
            entities=entities,
        )

    except Exception as e:
        logger.error("Entity extraction failed for %s: %s", source_file, e)
        return ExtractionResult(
            source_file=source_file,
            source_text=text,
            error=str(e),
        )


async def extract_entities_async(
    text: str, source_file: str, api_key: str
) -> ExtractionResult:
    """Async wrapper around synchronous LangExtract call."""
    return await asyncio.to_thread(extract_entities, text, source_file, api_key)
