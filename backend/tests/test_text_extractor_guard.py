from __future__ import annotations

import pytest

from app.services.extraction import text_extractor


@pytest.mark.asyncio
async def test_tiff_ocr_requires_gemini_key(monkeypatch, tmp_path):
    monkeypatch.setattr(text_extractor.settings, "gemini_api_key", "")
    # api_key="" simulates no Gemini available
    f = tmp_path / "x.tiff"
    f.write_bytes(b"II*\x00")  # minimal tiff magic
    with pytest.raises(ValueError, match="Vision OCR requires"):
        await text_extractor.extract_text_from_tiff(f, api_key="")
