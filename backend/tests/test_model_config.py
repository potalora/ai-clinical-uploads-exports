from __future__ import annotations

from app.config import settings


def test_extraction_model_is_3_5_flash():
    assert settings.gemini_extraction_model == "gemini-3.5-flash"


def test_text_summary_model_is_3_5_flash():
    assert settings.gemini_model == "gemini-3.5-flash"
