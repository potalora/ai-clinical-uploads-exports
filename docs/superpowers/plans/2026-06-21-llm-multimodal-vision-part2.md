# Multimodal Vision (Part 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]`.

**Goal:** Make LLM input type-agnostic — text + images + PDFs route through the facade to any vision-capable provider — and route OCR (scanned PDF / TIFF) through the user's configured `vision` provider instead of being hard-pinned to Gemini.

**Architecture:** `LLMMessage.content` becomes `str | list[ContentPart]` (TextPart/ImagePart/DocumentPart). Each vision provider maps parts to its SDK shape (Gemini `Part.from_bytes`; Anthropic image/document blocks; OpenAI `image_url` + `file`). `text_extractor` builds a multimodal `LLMRequest` and calls `get_provider("vision", config)`, with capability gating + Gemini fallback. Text-only callers (a plain `str`) are byte-for-byte unchanged.

**Tech Stack:** google-genai, openai, anthropic SDKs; pytest.

## Global Constraints

- Back-compat: `content: str` keeps working identically (wrapped as one TextPart internally). All existing text operations unchanged.
- De-identify before every call — OCR text isn't de-identified pre-OCR (it's raw document bytes → that's the input), but the EXTRACTED text is de-identified downstream before any further LLM call, as today. (OCR is the de-id boundary's input, unchanged from current Gemini behavior.)
- Vision is provider/model-dependent. A provider that can't handle a part type raises `LLMBadRequestError`; OCR falls back to Gemini when a Gemini key exists, else a clear error.
- Type hints + `from __future__ import annotations`; Ruff 100-char; no bare except; logging not print.
- New deps: NONE (Gemini/Anthropic/OpenAI all take native PDF; images via base64).

---

### Task 1: Content part types

**Files:** Modify `backend/app/services/ai/llm/types.py`; Modify `backend/app/services/ai/llm/__init__.py` (export parts). Test: `backend/tests/test_llm_content_parts.py`.

**Interfaces:**
- Produces: `@dataclass TextPart(text: str)`, `@dataclass ImagePart(data: bytes, mime: str)`, `@dataclass DocumentPart(data: bytes, mime: str)`, `ContentPart = TextPart | ImagePart | DocumentPart`. `LLMMessage.content: str | list[ContentPart]`. Helper `as_parts(content) -> list[ContentPart]` (wraps str → `[TextPart(str)]`).

- [ ] **Step 1: failing test**

```python
# backend/tests/test_llm_content_parts.py
from __future__ import annotations
from app.services.ai.llm.types import (
    LLMMessage, TextPart, ImagePart, DocumentPart, as_parts)


def test_str_content_normalizes_to_textpart():
    parts = as_parts("hello")
    assert parts == [TextPart("hello")]


def test_list_content_passthrough():
    img = ImagePart(b"\x89PNG", "image/png")
    parts = as_parts([TextPart("describe"), img])
    assert parts[1] is img


def test_message_accepts_parts():
    m = LLMMessage("user", [DocumentPart(b"%PDF", "application/pdf")])
    assert isinstance(m.content, list)
```

- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3: implement** — add to `types.py`:

```python
@dataclass
class TextPart:
    text: str

@dataclass
class ImagePart:
    data: bytes
    mime: str

@dataclass
class DocumentPart:
    data: bytes
    mime: str

ContentPart = TextPart | ImagePart | DocumentPart

def as_parts(content: "str | list[ContentPart]") -> list[ContentPart]:
    """Normalize message content to a list of parts (str -> one TextPart)."""
    if isinstance(content, str):
        return [TextPart(content)]
    return list(content)
```
Change `LLMMessage.content` annotation to `str | list[ContentPart]` (keep default behavior). Export the three parts + `as_parts` from `__init__.py` and add to `__all__`.

- [ ] **Step 4: run → PASS. Step 5: commit** `feat(llm-vision): content-part types (text/image/document)`

---

### Task 2: Gemini vision mapping

**Files:** Modify `backend/app/services/ai/llm/gemini.py`. Test: `backend/tests/test_llm_gemini_vision.py`.

**Interfaces:** Consumes Task 1 parts. `complete` builds a `contents` list from parts: TextPart→str, Image/DocumentPart→`gtypes.Part.from_bytes(data, mime_type=mime)`.

- [ ] **Step 1: failing test** (mock genai.Client; assert the `contents` passed to generate_content contains a Part built from bytes for an image message)

```python
# backend/tests/test_llm_gemini_vision.py
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from app.services.ai.llm.gemini import GeminiProvider
from app.services.ai.llm.types import LLMMessage, LLMRequest, ImagePart, TextPart


@pytest.mark.asyncio
async def test_gemini_sends_image_bytes():
    prov = GeminiProvider(api_key="k", model_default="gemini-3.5-flash")
    resp = SimpleNamespace(text="extracted", usage_metadata=None,
                           candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))])
    fake = MagicMock(); fake.aio.models.generate_content = AsyncMock(return_value=resp)
    captured = {}
    def from_bytes(data, mime_type):
        captured["mime"] = mime_type; captured["len"] = len(data)
        return f"PART({mime_type})"
    with patch("app.services.ai.llm.gemini.genai.Client", return_value=fake), \
         patch("app.services.ai.llm.gemini.gtypes.Part.from_bytes", side_effect=from_bytes):
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("Extract text"), ImagePart(b"IMG", "image/tiff")])],
            model="gemini-3.5-flash", max_output_tokens=64))
    assert captured["mime"] == "image/tiff" and captured["len"] == 3
    sent = fake.aio.models.generate_content.call_args.kwargs["contents"]
    assert "Extract text" in sent and 'PART(image/tiff)' in sent
```

- [ ] **Step 2: run → FAIL. Step 3: implement** — in `complete`, replace the `contents = "\n\n".join(...)` line with a builder:

```python
    contents: list = []
    for m in request.messages:
        if m.role == "system":
            continue
        for part in as_parts(m.content):
            if isinstance(part, TextPart):
                contents.append(part.text)
            else:  # ImagePart | DocumentPart
                contents.append(gtypes.Part.from_bytes(data=part.data, mime_type=part.mime))
    # Gemini accepts a single string or a list; keep a string when it's all text
    if len(contents) == 1 and isinstance(contents[0], str):
        contents = contents[0]
```
Import `as_parts, TextPart` (and Image/DocumentPart as needed) from `app.services.ai.llm.types`.

- [ ] **Step 4: run → PASS (+ existing `test_llm_gemini.py`). Step 5: commit** `feat(llm-vision): Gemini image/PDF parts`

---

### Task 3: Anthropic vision mapping

**Files:** Modify `backend/app/services/ai/llm/anthropic.py`. Test: `backend/tests/test_llm_anthropic_vision.py`.

**Interfaces:** `complete` builds per-message `content` blocks: TextPart→`{"type":"text","text":...}`, ImagePart→`{"type":"image","source":{"type":"base64","media_type":mime,"data":b64}}`, DocumentPart→`{"type":"document","source":{"type":"base64","media_type":"application/pdf","data":b64}}`. A message that is all-text may stay a plain string.

- [ ] **Step 1: failing test**

```python
# backend/tests/test_llm_anthropic_vision.py
from __future__ import annotations
import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from app.services.ai.llm.anthropic import AnthropicProvider
from app.services.ai.llm.types import LLMMessage, LLMRequest, DocumentPart, TextPart


@pytest.mark.asyncio
async def test_anthropic_sends_pdf_document_block():
    prov = AnthropicProvider(api_key="k", model_default="claude-x")
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")],
                           stop_reason="end_turn",
                           usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="claude-x")
    fake = MagicMock(); fake.messages.create = AsyncMock(return_value=resp)
    with patch("app.services.ai.llm.anthropic.AsyncAnthropic", return_value=fake):
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("Extract"), DocumentPart(b"%PDF-1.4", "application/pdf")])],
            model="claude-x", max_output_tokens=64))
    blocks = fake.messages.create.call_args.kwargs["messages"][0]["content"]
    doc = next(b for b in blocks if b["type"] == "document")
    assert doc["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(doc["source"]["data"]) == b"%PDF-1.4"
```

- [ ] **Step 2: run → FAIL. Step 3: implement** — build messages with a helper that maps `as_parts(m.content)` to blocks (base64-encode image/doc bytes). All-text content with a single TextPart may pass as a string for parity with today. Keep the existing JSON-prefill path working (json_mode appends the `{` assistant turn after the user message).
- [ ] **Step 4: run → PASS (+ existing `test_llm_anthropic.py`). Step 5: commit** `feat(llm-vision): Anthropic image/document blocks`

---

### Task 4: OpenAI-compatible vision mapping

**Files:** Modify `backend/app/services/ai/llm/openai_compat.py`. Test: `backend/tests/test_llm_openai_vision.py`.

**Interfaces:** `complete` builds per-message `content` array: TextPart→`{"type":"text","text":...}`, ImagePart→`{"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}}`, DocumentPart→`{"type":"file","file":{"filename":"document.pdf","file_data":f"data:application/pdf;base64,{b64}"}}`. All-text message stays a plain string (today's behavior).

- [ ] **Step 1: failing test**

```python
# backend/tests/test_llm_openai_vision.py
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from app.services.ai.llm.openai_compat import OpenAICompatProvider
from app.services.ai.llm.types import LLMMessage, LLMRequest, ImagePart, TextPart


@pytest.mark.asyncio
async def test_openai_sends_image_url_data_uri():
    prov = OpenAICompatProvider(name="openai", api_key="k",
                                base_url="https://api.openai.com/v1", model_default="gpt-4o-mini")
    choice = SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")
    resp = SimpleNamespace(choices=[choice],
                           usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                           model="gpt-4o-mini")
    fake = MagicMock(); fake.chat.completions.create = AsyncMock(return_value=resp)
    with patch("app.services.ai.llm.openai_compat.AsyncOpenAI", return_value=fake):
        await prov.complete(LLMRequest(
            messages=[LLMMessage("user", [TextPart("Extract"), ImagePart(b"IMG", "image/png")])],
            model="gpt-4o-mini", max_output_tokens=64))
    content = fake.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    img = next(p for p in content if p["type"] == "image_url")
    assert img["image_url"]["url"].startswith("data:image/png;base64,")
```

- [ ] **Step 2: run → FAIL. Step 3: implement** — map parts as above; keep the all-text path as a plain string; preserve the existing json_mode/temperature/BadRequest-retry logic. Update `capabilities.supports_vision`: leave `False` as the class default (model-dependent) — vision is opt-in via the user choosing this provider for the `vision` op; the provider still SENDS image parts when given them (capability flag is advisory for the UI, not a hard block).
- [ ] **Step 4: run → PASS (+ existing `test_llm_openai_compat.py`). Step 5: commit** `feat(llm-vision): OpenAI-compatible image_url + file parts`

---

### Task 5: Route OCR through the vision provider

**Files:** Modify `backend/app/services/extraction/text_extractor.py`; Modify the OCR call site in `backend/app/api/upload.py` (thread `config`). Test: `backend/tests/test_text_extractor_vision_routing.py`.

**Interfaces:** `extract_text(file_path, api_key, config=None)`, `extract_text_from_pdf(file_path, api_key, config=None)`, `extract_text_from_tiff(file_path, api_key, config=None)`. The Gemini-vision helpers are replaced by a single `_ocr_via_provider(parts, config, api_key) -> str` that calls `get_provider("vision", config or LLMConfig.from_settings()).complete(...)`, falling back to a Gemini provider (built from the api_key) on capability/auth failure when a Gemini key exists.

- [ ] **Step 1: failing test** (a configured vision provider receives the document/image parts)

```python
# backend/tests/test_text_extractor_vision_routing.py
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
from app.services.extraction import text_extractor
from app.services.ai.llm.config import LLMConfig, ProviderCreds
from app.services.ai.llm.types import LLMResponse, LLMUsage, DocumentPart


@pytest.mark.asyncio
async def test_pdf_ocr_routes_to_vision_provider(tmp_path):
    pdf = tmp_path / "scan.pdf"; pdf.write_bytes(b"%PDF-1.4 fake")
    cfg = LLMConfig(routing={"default": "anthropic", "vision": "anthropic"},
                    providers={"anthropic": ProviderCreds(api_key="k", model="claude-x")})
    fake = AsyncMock()
    fake.complete.return_value = LLMResponse(text="OCR TEXT", finish_reason="stop",
                                             model="claude-x", usage=LLMUsage(1, 1, 2), raw=None)
    # force the gemini-local path to "low confidence" so it uses the vision provider
    with patch.object(text_extractor, "extract_text_from_pdf_local", return_value=("", 0.0)), \
         patch.object(text_extractor, "get_provider", return_value=fake):
        out = await text_extractor.extract_text_from_pdf(pdf, api_key="gem", config=cfg)
    assert out == "OCR TEXT"
    req = fake.complete.call_args.args[0]
    parts = req.messages[0].content
    assert any(isinstance(p, DocumentPart) for p in parts)
```

- [ ] **Step 2: run → FAIL. Step 3: implement** — add `_ocr_via_provider`:

```python
async def _ocr_via_provider(parts, config, api_key, instruction):
    from app.services.ai.llm import LLMMessage, LLMRequest, get_provider
    from app.services.ai.llm.config import LLMConfig
    from app.services.ai.llm.registry import _build
    cfg = config or LLMConfig.from_settings()
    req = LLMRequest(messages=[LLMMessage("user", [*parts, TextPart(instruction)])],
                     model="", max_output_tokens=8192, temperature=0.0)
    try:
        return (await get_provider("vision", cfg).complete(req)).text or ""
    except Exception:
        if api_key:  # fall back to Gemini vision
            gem = _build("gemini", LLMConfig(routing={"default": "gemini"},
                         providers={"gemini": ProviderCreds(api_key=api_key, model=settings.gemini_model)}))
            return (await gem.complete(req)).text or ""
        raise
```
Rewrite `_extract_text_from_pdf_gemini`/`extract_text_from_tiff` to read bytes and call `_ocr_via_provider([DocumentPart(pdf, "application/pdf")], ...)` / `_ocr_via_provider([ImagePart(tiff_bytes, "image/tiff")], ...)`. Thread `config` through `extract_text`/`extract_text_from_pdf`/`extract_text_from_tiff`. Remove the hard "Vision OCR requires GEMINI_API_KEY" guard — replace with the fallback (raise a clear error only when BOTH the vision provider fails AND no Gemini key). In `api/upload.py`, pass `config=config` (already loaded in the engines) into the `extract_text(...)` call(s).

- [ ] **Step 4: run → PASS (+ existing `test_text_extractor_guard.py` — update it: the guard message changed; assert the new fallback-absent error). Step 5: commit** `feat(llm-vision): route OCR through the configured vision provider with Gemini fallback`

---

### Task 6: Live vision smoke + regression

**Files:** Create `backend/tests/test_llm_vision_live_smoke.py` (slow, gated). Verify full suite.

- [ ] **Step 1:** a tiny PNG (1×1, base64 built inline) OCR'd via Gemini, Anthropic, and OpenAI (each gated on key presence; skip on rate-limit). Assert a non-empty response. PDF document test for Gemini/Anthropic/OpenAI (native PDF) using a minimal one-page PDF byte string.
- [ ] **Step 2:** `cd backend && .venv/bin/python -m pytest -m "not slow" -q` — all pass (back-compat: text-only operations unchanged).
- [ ] **Step 3: commit** `test(llm-vision): live multimodal smoke (gemini/anthropic/openai)`

---

## Self-Review

**Spec coverage:** content parts (T1), provider mappings for all three SDK families (T2/T3/T4), OCR routed through the `vision` provider with capability fallback (T5), live smoke incl. OpenAI now that credits exist (T6). Vision routing field already exists in Part 1's config/pane. **Placeholders:** none. **Type consistency:** `TextPart/ImagePart/DocumentPart/as_parts`, `get_provider("vision", config)`, `_ocr_via_provider` consistent across tasks. Parallelizable: T2/T3/T4 are independent provider files (run concurrently after T1); T5 depends on T2-T4; T6 last.
