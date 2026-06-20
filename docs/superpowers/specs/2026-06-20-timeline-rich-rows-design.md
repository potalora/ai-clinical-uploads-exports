# Design — Rich Timeline Rows (server-computed scalar previews)

**Date:** 2026-06-20
**Status:** Design approved (interactive brainstorm); implementation plan authored separately, combined with `docs/oss-adoption-design.md`.
**Scope:** Surface richer per-record data with compact visuals **inline in the default Timeline rows** (before the detail sheet), covering **all** record types. Server-computed scalar previews only — no per-row trend fetches in v1.

> Architecture spec, not a step-by-step plan. Defines *what* the preview is, *where* it plugs in, and *how* it stays faithful to the theme and the Absolute Rules. The granular task breakdown lives in the combined implementation plan.

---

## 1. Goal & non-goals

**Goal.** A user scanning the Timeline should see the salient value of each record — a lab's value + flag + position in range, a med's dose, a condition's status — without opening the detail sheet. Today the Timeline payload carries only `display_text` / `code_display` / `provider`, so structured detail is invisible until click.

**Non-goals.**
- **No per-row network fetches** (sparklines/trends deferred — chosen scope #1). Everything renders from data already loaded server-side.
- **No good/bad value coloring** (CLAUDE.md "Reimagined" theme: *neutral records-organizer framing*). Flags are **factual data from the source**, rendered in theme-neutral chips — never a red=danger / green=good clinical judgment by the app.
- **No new product capability** — this is presentation of existing record data. No diagnoses/advice (Rule 1).
- **No scope creep** to Records/Admin lists or Overview. They can reuse the component later; out of scope for v1.

---

## 2. Data contract

A new **optional** `preview` object on each timeline event, computed server-side. Flat, type-agnostic shape — no tagged union on the wire:

```
TimelinePreview:
  value:    str | None        # primary measured value: "17", "120/80", "20 mg"
  unit:     str | None        # "ng/mL" (labs/vitals); null when the unit is baked into value (meds)
  flag:     str | None        # factual chip label from the source: "LOW"/"HIGH"/"HH"/"ACTIVE"/"RESOLVED"/"NEGATED"/"Telehealth"/...
  emphasis: str | None        # NEUTRAL emphasis only: "normal" | "notable" | "muted"
                              #   notable = out-of-reference-range / abnormal interpretation (subtle theme accent, NOT red/danger)
                              #   muted   = negated / inactive / resolved / stopped
                              #   normal  = default (or null)
  gauge:    {value: float, low: float, high: float} | None   # only when a numeric value AND numeric low+high exist
  facets:   list[str]         # secondary detail chips: ["oral","1×/day"], ["onset 2024"], ["hives, rash"]
```

When nothing populates, `preview` is `null` and the row renders exactly as today (graceful degradation — documents, bare-name records, etc.).

**Why flat, not a per-type union:** the renderer (a single metric strip) treats every field uniformly — value+unit, one chip, an optional gauge, N facet chips. A flat object keeps the wire contract, the Pydantic schema, and the TS type trivial, and lets the per-type *builder* own all the branching.

---

## 3. Per-type mapping (covers all types)

The builder reads **structured FHIR fields** from the stored JSONB, with a `display_text` regex fallback only when the structured value is absent.

| Record type | value / unit | flag | emphasis | gauge | facets |
|---|---|---|---|---|---|
| **observation / lab** | `valueQuantity.value` + `.unit` | `interpretation.coding.code` → LOW/HIGH/HH/LL/N | `notable` if abnormal/out-of-range, else `normal` | `referenceRange[0].low.value` / `.high.value` if both numeric | — |
| **observation / vital** | `valueQuantity`; BP → `component[]` (8480-6 / 8462-4) as "120/80" | — | normal | rare (only if range present) | — |
| **observation / social** | `valueCodeableConcept.text` or `valueString` | — | normal | — | — |
| **condition** | — | `clinicalStatus.coding.code` → ACTIVE/INACTIVE/RESOLVED; negated → NEGATED | `muted` if inactive/resolved/negated | — | onset (`onsetDateTime`/`onsetString`) |
| **medication** (MedicationRequest) | `dosageInstruction[0].doseAndRate[0].doseQuantity` → "20 mg" | `status` → ACTIVE/STOPPED/COMPLETED | `muted` if stopped/completed | — | route, frequency (`timing`) |
| **allergy** (AllergyIntolerance) | — | `criticality` → HIGH/LOW; `clinicalStatus` | `notable` if criticality high | — | reaction(s) `reaction[].manifestation[].text` |
| **procedure** | — | `status` | `muted` if not-done | — | outcome, body site |
| **immunization** | dose (`doseQuantity`) | `status` | normal | — | series # (`protocolApplied[].doseNumber`) |
| **encounter** | — | `class.code/.display` → Ambulatory/ER/Telehealth/Inpatient | normal | — | reason (`reasonCode[].text`) |
| **imaging / DiagnosticReport** | — | — | normal | — | modality, conclusion snippet |
| **document** (DocumentReference) | — | — | normal | — | (usually null → falls back to today's row) |

**Emphasis is neutral.** "notable" signals *out of the source's own reference range / abnormal interpretation flag* — it renders with a subtle theme accent (e.g. ochre/sienna), never a clinical danger red. This faithfully surfaces the source data without the app editorializing.

---

## 4. Backend design

- **New focused module** `backend/app/services/timeline_preview.py` → `build_timeline_preview(fhir_resource: dict | None, record_type: str) -> TimelinePreview | None`.
  - Plain dict traversal over the stored JSONB — the **same pattern** as `timeline_service.extract_provider_display`. **No `fhir.resources`** model instantiation (that library is ingestion-time only).
  - One private helper per record_type family (`_lab`, `_vital`, `_condition`, `_medication`, …) dispatched by `record_type` + observation sub-category, so each branch is independently testable and the module stays readable.
  - Numeric coercion is defensive: a non-parseable value or a missing/zero-width range yields **no gauge** (the value text + flag still render).
- **Schema** (`backend/app/schemas/timeline.py`): add `TimelineGauge` + `TimelinePreview` Pydantic models; add `preview: TimelinePreview | None = None` to `TimelineEvent`.
- **Wiring** (`backend/app/api/timeline.py`): in the event-construction loop, call `build_timeline_preview(r.fhir_resource, r.record_type)`. The endpoint already does `select(HealthRecord)` and reads `r.fhir_resource` for provider extraction, so this adds **zero extra queries** and no N+1.

---

## 5. Frontend design

- **Type** (`frontend/src/types/api.ts`): add `preview?: TimelinePreview` (+ `TimelineGauge`) to `TimelineEvent`.
- **New component** `frontend/src/components/retro/TimelineMetricStrip.tsx` — renders, in one compact line:
  `value`+`unit` → tone-neutral `flag` chip → reused `Gauge` atom (with `low`–`high` range labels) → `facets` as small chips.
  - Reuses `Gauge` from `components/retro/DataViz.tsx` (`{value, low, high}`); **verify the Gauge's own coloring stays theme-neutral** (no good/bad), adjust if needed.
  - A small `emphasis → className/color` map using existing theme tokens (`--theme-*`, `--record-*`). "notable" = subtle accent; "muted" = dimmed; "normal" = default.
- **Placement** (`frontend/src/app/(dashboard)/timeline/page.tsx`): insert `<TimelineMetricStrip preview={r.preview} />` between the title line (`tl-title`, ~L166) and the provider line (`tl-provider`, ~L167). Renders nothing when `preview` is null/empty.
- **Layout** = the approved **inline metric strip** (one line under the title, before provider). Stays compact; degrades to today's row when empty.

---

## 6. Edge cases & faithfulness

- **No structured data** → `preview` null → unchanged row (no empty strip artifacts).
- **Value also in the title** (e.g. extractor baked "VitD: 17" into `display_text`) → mild redundancy accepted; the strip prefers structured FHIR (`valueQuantity`) and adds the *flag + gauge + unit* the title lacks.
- **Negated / inactive** (e.g. "constipation (negated)", "nausea (negated)" rows) → `emphasis: muted`, flag `NEGATED` — visually quiet, matching their clinical status.
- **BP & multi-component vitals** → composed value ("120/80"); other components dropped from the strip (full set stays in the detail sheet).
- **Theme rule** → flags/emphasis are neutral; the gauge shows position-in-range as information, not judgment.

---

## 7. Testing strategy (TDD — expected output first)

Per project TDD: define expected output → write the unit test first → exhaustive → compare real-vs-expected.

- **Backend unit** (`tests/test_timeline_preview.py`): one case per type family against hand-built FHIR dicts — lab with range → value+unit+flag+gauge; abnormal lab → `emphasis=notable`; BP vital → "120/80"; condition active vs negated → flag + `muted`; med → dose + route/frequency facets + status; allergy high criticality → flag + reaction facet; encounter → class flag; **record with nothing → returns `None`**; non-numeric value / missing range → **no gauge**.
- **API** (extend `tests/test_timeline*.py`): `/timeline` response carries populated `preview` for seeded lab/med/condition records and `null` where expected.
- **Frontend** (under the global console-error gate): a Timeline render assertion that a lab row shows value + flag chip; an empty-preview row shows no strip. Reuse the large-dataset seed pattern if needed.
- **Verification order** (project rule): API/script proof first (payload shows `preview`), then manual frontend check.

---

## 8. Sequencing & agent-team notes

This workstream (**WS-T**) is **fully independent** of the OSS workstreams (WS-A…E) — it touches only `schemas/timeline.py`, `api/timeline.py`, the new `services/timeline_preview.py`, and three frontend files. It shares **no** files with the OSS work except, potentially, `conftest.py` seed helpers.

- **Internal order:** data contract (schema) → backend builder (test-first) → API wiring → frontend type → component → placement. Backend and frontend can split across two agents once the contract is fixed.
- **Conflict surface:** none with OSS work; the contract (schema field name/shape) is the only thing other agents must not redefine. Lock it in Phase 0 of the combined plan.

---

## 9. Open decisions

1. **Gauge neutrality:** confirm `DataViz.Gauge`'s existing coloring is theme-neutral; if it encodes good/bad, neutralize it (small, isolated change).
2. **Abnormal accent token:** which exact theme token represents `notable` (ochre vs sienna) — a frontend-design call at implementation time.
3. **Facet caps:** max facet chips before truncation (proposed: 3, "+N" overflow) — set during implementation.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Flag coloring reads as clinical good/bad | Neutral `emphasis` tokens only; design review against the theme rule |
| Gauge atom not built for arbitrary ranges | Reuse + verify with tests; defensive numeric coercion, no gauge on bad input |
| Payload growth on 200-event timeline | Preview is a handful of short scalars; far lighter than shipping `fhir_resource` (the rejected Option B) |
| Redundant value vs title | Accepted; strip adds flag/gauge/unit the title lacks |
| Contract drift if built by parallel agents | Freeze `TimelinePreview` shape in the combined plan's Phase 0 before fan-out |
