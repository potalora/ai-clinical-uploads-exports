from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.extraction import text_extractor


@pytest.mark.asyncio
async def test_tiff_ocr_raises_when_no_vision_provider_configured(monkeypatch, tmp_path):
    """With no configured vision provider AND ``api_key=""`` there is nothing to try.

    The old hard guard ("Vision OCR requires GEMINI_API_KEY") is gone; OCR no longer
    *requires* a Gemini key up front, but it must still error clearly when no
    vision-capable provider is available to try.
    """
    monkeypatch.setattr(text_extractor.settings, "gemini_api_key", "")
    f = tmp_path / "x.tiff"
    f.write_bytes(b"II*\x00")  # minimal tiff magic

    # No candidate providers at all -> a clear error rather than a silent "".
    with patch.object(text_extractor, "_vision_candidates", return_value=[]):
        with pytest.raises(RuntimeError, match="No vision-capable provider"):
            await text_extractor.extract_text_from_tiff(f, api_key="")


@pytest.mark.asyncio
async def test_ocr_returns_empty_when_every_candidate_is_blocked(monkeypatch, tmp_path):
    """If candidates exist but all return no text (all blocked), OCR returns ""."""
    monkeypatch.setattr(text_extractor.settings, "gemini_api_key", "")
    f = tmp_path / "x.tiff"
    f.write_bytes(b"II*\x00")

    blocked = AsyncMock()
    blocked.complete.return_value = type(
        "R", (), {"text": ""}
    )()  # empty text, no exception
    with patch.object(
        text_extractor, "_vision_candidates", return_value=[("gemini", blocked)]
    ):
        out = await text_extractor.extract_text_from_tiff(f, api_key="")
    assert out == ""
