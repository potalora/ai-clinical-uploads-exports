from __future__ import annotations

from app.config import settings


def test_section_extraction_concurrency_raised():
    assert settings.section_extraction_concurrency == 10


def test_section_concurrency_within_global_cap():
    # The global Gemini semaphore is the hard ceiling; section concurrency must not exceed it.
    assert settings.section_extraction_concurrency <= settings.gemini_concurrency_limit
