from __future__ import annotations
from app.config import settings


def test_llm_provider_defaults_to_gemini():
    assert settings.llm_provider == "gemini"


def test_openai_compatible_defaults_present():
    assert settings.openai_base_url.endswith("/v1")
    assert settings.ollama_base_url == "http://localhost:11434/v1"
    assert settings.lmstudio_base_url == "http://localhost:1234/v1"
    assert settings.openrouter_base_url == "https://openrouter.ai/api/v1"


def test_per_operation_provider_overrides_blank_by_default():
    assert settings.llm_summary_provider == ""
    assert settings.llm_section_provider == ""
    assert settings.llm_dedup_provider == ""
    assert settings.llm_extraction_provider == ""
