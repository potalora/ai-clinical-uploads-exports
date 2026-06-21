# Multi-LLM-Provider Support — Design Spec

**Date:** 2026-06-21
**Status:** Approved (brainstorming complete)
**Supersedes constraints:** Relaxes Absolute Rules #3 and #16 in `CLAUDE.local.md` — additional LLM providers are now explicitly approved by the user. Rule #2 (always de-identify before any LLM call) is **strengthened**, not relaxed: it now applies to every provider, cloud or local. Rule #17 (OSS/permissive licenses only) still holds — all new deps are MIT/Apache-2.0.

## 1. Goal

MedTimeline currently calls Google Gemini directly at five sites (summarization, PDF/TIFF OCR, document section parsing, dedup LLM-judge, clinical entity extraction via LangExtract). The goal is a provider-agnostic LLM layer so the same operations can run against:

| Provider | Transport | How reached |
|----------|-----------|-------------|
| **Gemini** (existing) | google-genai | `genai.Client(api_key=...)` |
| **OpenAI** | openai SDK | `AsyncOpenAI(api_key, base_url=https://api.openai.com/v1)` |
| **Anthropic** | anthropic SDK | `AsyncAnthropic(api_key=...)` |
| **OpenRouter** | openai SDK | base_url `https://openrouter.ai/api/v1` |
| **LM Studio** | openai SDK | base_url `http://localhost:1234/v1` |
| **Ollama** | openai SDK | base_url `http://localhost:11434/v1` |
| **Vertex (GCP)** | google-genai (Gemini-on-Vertex) | `genai.Client(vertexai=True, project, location)`; Claude-on-Vertex via `anthropic[vertex]` best-effort |

**Key insight:** OpenAI, OpenRouter, LM Studio, and Ollama all speak the OpenAI Chat Completions API. One `openai_compat` provider class with a swappable `base_url` covers all four. That makes the real provider count three SDKs (google-genai, openai, anthropic) for seven providers.

## 2. Decisions (locked)

1. **Native SDKs**, not LiteLLM. Add `openai` + `anthropic` (both light, pure-Python, httpx-based; google-genai already present). Keeps full control over Gemini's `ThinkingConfig` and `response_schema`, which LiteLLM would abstract away. Avoids LiteLLM's heavy transitive tree (tiktoken, etc.).
2. **Always de-identify.** The existing three-layer scrubber runs before EVERY provider call, cloud or local. No opt-out branch. One invariant, easy to test.
3. **Scope = all text operations.** Summarization, section parsing, dedup LLM-judge, and a generic JSON entity-extraction fallback route through the new client. Vision-OCR stays Gemini-only (capability-gated). LangExtract stays the Gemini entity path; non-Gemini providers use the generic JSON entity path.

## 3. Architecture

New package `backend/app/services/ai/llm/`:

```
llm/
├── __init__.py          # public: get_provider(), LLMProvider, LLMResponse, LLMError, complete()/complete_async()
├── types.py             # LLMMessage, LLMResponse, LLMUsage, Capabilities, LLMError taxonomy
├── base.py              # LLMProvider ABC
├── registry.py          # build provider from settings; per-operation override; caching
├── gemini.py            # wraps google-genai (api-key mode AND vertexai mode)
├── openai_compat.py     # openai SDK; base_url drives openai/openrouter/lmstudio/ollama
└── anthropic.py         # anthropic SDK
```

### 3.1 Interface (`base.py`)

```python
class LLMProvider(ABC):
    name: str
    capabilities: Capabilities  # supports_vision, supports_json_mode, supports_reasoning

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
    # sync wrapper provided in base via asyncio.run guard for the few sync callers
```

`LLMRequest` fields (provider-normalized):
- `messages: list[LLMMessage]` (role: system|user|assistant)
- `system: str | None` (hoisted out for providers that take it separately — Anthropic, Gemini system_instruction)
- `model: str` (resolved by registry per operation)
- `max_output_tokens: int`
- `temperature: float | None`
- `json_mode: bool` and optional `json_schema: dict | None`
- `reasoning: ReasoningConfig | None` (level low/high — mapped to Gemini ThinkingConfig; no-op where unsupported)

`LLMResponse`: `text: str`, `finish_reason: str` (normalized: `stop` | `length` | `content_filter` | `other`), `model: str`, `usage: LLMUsage(prompt_tokens, completion_tokens, total_tokens)`, `raw: Any` (provider object, for debugging).

`LLMError` taxonomy (normalized so callers/retry logic are provider-agnostic): `LLMAuthError`, `LLMRateLimitError`, `LLMTimeoutError`, `LLMBadRequestError`, `LLMResponseError`, `LLMProviderUnavailableError`. Each provider maps its SDK exceptions into these.

### 3.2 Per-provider normalization notes

- **gemini.py** — maps `system` → `system_instruction`; `json_mode` → `response_mime_type="application/json"` (+ `response_schema` when a schema is given); `reasoning.level` → `types.ThinkingConfig(thinking_level=...)`; reads `usage_metadata`. Honors `finish_reason == MAX_TOKENS` → normalized `length`. Vertex mode toggled by `vertexai=True, project, location` instead of `api_key`.
- **openai_compat.py** — `system` becomes a leading system message; `json_mode` → `response_format={"type":"json_object"}` (schema → `{"type":"json_schema", ...}` when the model/endpoint supports it, else fall back to json_object + prompt instruction); `reasoning` is a no-op for standard chat models (documented). Reads `response.usage`. Guards for models that reject `temperature` or require `max_completion_tokens` (try/fallback). `base_url`/`api_key` come from the provider config; local servers accept any non-empty key (`"ollama"` / `"lm-studio"`).
- **anthropic.py** — `system` → top-level `system`; messages mapped to user/assistant; no native JSON mode, so `json_mode` is enforced via a strict system-prompt instruction plus optional assistant-message prefill (`{`) and we strip/parse; reads `usage.input_tokens`/`output_tokens`; `stop_reason == max_tokens` → `length`.

### 3.3 Registry & config

`registry.get_provider(operation: str | None = None) -> LLMProvider`:
- Resolves provider name: per-operation override (`LLM_<OP>_PROVIDER`) → global `LLM_PROVIDER` → `"gemini"` (back-compat default).
- Builds and caches one provider instance per (provider, base_url, model) key.
- Resolves the model: per-operation model override → per-provider default model → hard default.

**Config additions (`config.py`)** — all optional, back-compat (unset → Gemini with today's behavior):

```
llm_provider: str = "gemini"               # global default
llm_summary_provider / llm_extraction_provider / llm_section_provider / llm_dedup_provider: str = ""  # optional per-op override

# OpenAI-compatible family (base_url distinguishes them)
openai_api_key: str = ""
openai_model: str = "gpt-4o-mini"
openai_base_url: str = "https://api.openai.com/v1"
openrouter_api_key: str = ""
openrouter_model: str = "openai/gpt-4o-mini"
openrouter_base_url: str = "https://openrouter.ai/api/v1"
ollama_base_url: str = "http://localhost:11434/v1"
ollama_model: str = "llama3.1"
lmstudio_base_url: str = "http://localhost:1234/v1"
lmstudio_model: str = ""                   # resolved from /v1/models if blank

# Anthropic
anthropic_api_key: str = ""
anthropic_model: str = "claude-haiku-4-5-20251001"

# Vertex (Gemini-on-Vertex)
vertex_project: str = ""
vertex_location: str = "us-central1"
vertex_model: str = "gemini-3.5-flash"
```

Existing `GEMINI_*` settings are untouched and remain the Gemini provider's source.

### 3.4 Call-site refactors

Each site keeps its de-id step verbatim and swaps the raw genai call for the facade:

1. **summarizer.py** — build `LLMRequest` (system=NL/JSON/BOTH prompt, json_mode for json/both, reasoning=summary thinking level, max_output_tokens=summary budget). `model_used` in the response dict comes from `LLMResponse.model`. Check `finish_reason` (already a documented gotcha).
2. **section_parser.py** — `json_mode=True` + the existing Pydantic `_SectionParseSchema` passed as `json_schema`; temp 0.1.
3. **llm_judge.py** — `json_mode=True`, temp 0.1; parse unchanged.
4. **entity_extractor.py** — **branch by provider.** If the resolved extraction provider is Gemini → keep LangExtract exactly as today. Else → new `generic_entity_extract()` that sends `CLINICAL_EXTRACTION_PROMPT` + the few-shot `CLINICAL_EXAMPLES` (reformatted as JSON exemplars) through the facade with `json_mode`, then parses the JSON into the same internal entity structure LangExtract yields (so `entity_to_fhir` is unchanged downstream). Retry wrapper reused.
5. **text_extractor.py** (vision OCR) — **out of scope for multi-provider.** Stays Gemini. Add a guard: if the configured provider can't do vision, OCR uses Gemini if a Gemini key exists, else returns a clear "vision unavailable for provider X" error. No behavior change when provider=gemini.

### 3.5 Frontend (small)

- `POST /summary/generate` accepts optional `provider` and `model` in the request body (validated against the known provider set; ignored/defaulted when absent).
- Summarize page gains a compact provider+model selector (defaults to the configured global provider). Populated from a new `GET /summary/providers` that returns the providers which are actually configured (have a key or a reachable local base_url) — never leaks keys, just names + default models + capability flags.

## 4. Testing strategy (autonomous, full)

Per the project's Feature Verification Pattern (API first, then frontend):

**Unit (mocked SDKs, no network):**
- `test_llm_providers.py` — each provider maps a canned SDK response → `LLMResponse` correctly (text, usage, finish_reason normalization); error mapping (auth/rate/timeout/badrequest) → the normalized taxonomy; system-prompt hoisting; json_mode wiring; reasoning→ThinkingConfig for Gemini and no-op elsewhere.
- `test_llm_registry.py` — provider/model resolution precedence (per-op override → global → default); instance caching; unknown provider → clear error; back-compat (no `LLM_PROVIDER` → Gemini + existing models).
- Contract test — every registered provider satisfies the `LLMProvider` interface and round-trips a fake request.
- `test_generic_entity_extract.py` — JSON entity payload → internal entity structure → unchanged `entity_to_fhir` output, parity-checked against a LangExtract-shaped fixture.
- De-id regression — assert the scrubber runs before the facade call for every refactored site (mock the provider, assert it received already-scrubbed text). This guards Absolute Rule #2 across all providers.

**Live smoke (gated on key/server presence; skip when absent — mirrors the existing `@pytest.mark.slow`/fidelity gating):**
- Gemini (existing key), OpenAI (provided key), Anthropic (provided key), Ollama (local), LM Studio (local). One real `complete()` per provider asserting non-empty text + sane usage. Vertex: unit/mock only (no creds).

**E2E (Playwright):**
- `multi-provider-summary.spec.ts` — seed records, open Summarize, switch provider via the selector, generate, assert a summary renders with the AI disclaimer and the de-id report present. Run against at least one cloud (OpenAI or Anthropic) and one local (Ollama or LM Studio) provider. Skips gracefully when a provider isn't configured.

**Local-server bring-up (I do this autonomously):** start `ollama serve`, `ollama pull/run` a small model (e.g. `llama3.2` / `qwen2.5`), and LM Studio's server via its `lms` CLI (`lms server start`, load a model). Persist through first-try failures (model not pulled, server not started, port busy).

## 5. Security / HIPAA

- All provided keys live only in `backend/.env` (gitignored — verified). Never committed, never logged, never returned by `GET /summary/providers`.
- De-id runs before every provider call (decision #2). The de-id report is still stored per prompt.
- Cloud providers (OpenAI/Anthropic/OpenRouter) receive only de-identified (Safe-Harbor) text. A short note will be added to the Summarize UI when a cloud provider is selected, reminding the user that de-identified data leaves the machine. Local providers (Ollama/LM Studio) keep data on-device.
- No diagnoses/advice constraint is unchanged — it lives in the prompts, which are provider-independent.

## 6. Out of scope (YAGNI)

- Streaming responses (all current calls are unary).
- Multi-provider vision OCR (Gemini-only; revisit if needed).
- Per-provider cost/usage accounting beyond the token counts already captured.
- Bedrock / Azure OpenAI (reachable later via the same openai_compat/anthropic seams, but not wired now).
- Replacing LangExtract for Gemini (kept as-is).

## 7. Rollout / back-compat

- Default `LLM_PROVIDER=gemini` → byte-for-byte current behavior; the refactor is a pure internal indirection until a provider is configured.
- `pyproject.toml`: add `openai` and `anthropic` to base deps (light). `uv.lock` regenerated; verify `uv sync --frozen` and the container build still resolve under the `<3.12` / typing-extensions override constraints already in place.
- `.env.example` documents every new var with comments.
- `CLAUDE.local.md` updated at ship time: Rules #3/#16 relaxed to "Gemini + the wired providers"; new "AI Providers" section; gotchas captured.
```
