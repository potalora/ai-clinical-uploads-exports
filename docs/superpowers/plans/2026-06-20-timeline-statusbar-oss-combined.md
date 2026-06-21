# MedTimeline — Combined Implementation Plan (Timeline Rich Rows · Status-Bar Fix · OSS Adoption)

> **For the agent team:** This plan is organized into **independent workstreams** for parallel execution by named agents in **isolated git worktrees**. Each workstream is self-contained and lands behind tests (and, where it changes behavior, a reversible flag). Steps use checkbox (`- [ ]`) syntax for tracking. Per project convention (memory: *Agent Teams*; *Subagent-Dev Disabled*), execute via an **agent team**, not `subagent-driven-development`. **Read `Agent-Team Orchestration` (below) before spawning anyone** — it defines Phase 0 contract-freeze, the file-ownership matrix, and merge order that keep parallel worktrees from colliding.

**Goal:** Ship two user-found fixes/features (concurrent-upload status-bar fix; rich inline Timeline rows) and adopt five mature OSS components across ingestion/extraction — all test-first, reversible, and license-clean.

**Architecture:** Seven workstreams. Two are new, self-contained, fully specified here (WS-U, WS-T). Five are the OSS-adoption workstreams (WS-A…E) whose architecture lives in `docs/oss-adoption-design.md`; this plan provides their task-level decomposition, dependency order, and conflict map, and defers each one's fully-bite-sized sub-plan to its **kickoff task** (open decisions + external-library APIs must be resolved against real code first — fabricated steps would be plan failures).

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Pydantic v2 / pytest (backend); Next.js 15 / TypeScript / Zustand / Playwright unit+e2e (frontend); spaCy/medspaCy/scispaCy or GLiNER, Presidio, RapidFuzz, `fhir.resources`, Synthea (OSS).

## Source designs
- `docs/superpowers/specs/2026-06-20-extraction-statusbar-concurrent-batch-fix.md` → **WS-U**
- `docs/superpowers/specs/2026-06-20-timeline-rich-rows-design.md` → **WS-T**
- `docs/oss-adoption-design.md` → **WS-A, WS-B, WS-C, WS-D, WS-E**

## Global Constraints
*(Every task implicitly includes these — copied verbatim from the specs / CLAUDE.md.)*
- **Absolute Rules** apply throughout: never generate diagnoses/advice; de-identify all PHI before any Gemini call; AI SDKs `google-genai`/`langextract` only (Rule 3 — no new AI provider; OSS libs are **local**, not providers); `GEMINI_API_KEY` via `.env` only; never log/expose PII or stack traces; soft-delete only; user-scoped queries; audit logging on data endpoints; **only MIT/Apache/BSD runtime deps (Rule 17)**; tests alongside every change.
- **TDD, project-style** (memory: *TDD Expected Output*): define expected output → write the failing unit test first → test exhaustively → compare real-vs-expected.
- **Verification order:** API/script-level proof first (status codes, payloads, DB state), then a manual frontend check. Never skip to UI.
- **Reversible by flag + shadow-compare** for anything changing extraction/de-id behavior (the `phi_ner_enabled` pattern): compute old+new, log diffs, keep old authoritative until validated on real data, *then* flip the default.
- **Neutral framing:** no good/bad value coloring anywhere (Reimagined theme).
- **Known gotchas (honor exactly):** test DB is `create_all`-managed — for any new column run the dev migration **and** `psql medtimeline_test -c "ALTER TABLE …"` (or drop+recreate) **and** ship the Alembic migration; dev uvicorn runs **without `--reload`** (restart after backend edits); run pytest via `.venv`; fast suite is `-m "not slow"`; literal `/records` subpaths precede `/{record_id}`; NER fail-open must stay **non-latching**; never `git push` CLAUDE.md to remote; never commit user PHI fixtures (gitignore).
- **Config flag names (frozen — Phase 0):** `EXTRACTION_ENGINE=gemini|local|hybrid` (default `gemini`), `PHI_ENGINE=legacy|presidio` (default `legacy`), `PHI_LOCATION_NER_ENABLED` (default off), `TERMINOLOGY_FUZZY_ENABLED` (default off), `FHIR_VALIDATION=off|log|strict` (default `log`).

---

## Agent-Team Orchestration

### Workstream catalog
| WS | Name | Layer | Independent? | Hard deps | Behind flag? |
|----|------|-------|-------------|-----------|--------------|
| **0** | Shared groundwork | both | — (serialized, runs first) | — | — |
| **U** | Status-bar concurrent-batch fix | FE | ✅ fully | Phase 0 | no |
| **T** | Timeline rich rows | BE+FE | ✅ fully | Phase 0 (contract freeze) | no |
| **C** | RapidFuzz (terminology + dedup) | BE | ✅ | Phase 0 | terminology only |
| **D** | FHIR structural validation | BE | ✅ | Phase 0 | yes (`FHIR_VALIDATION`) |
| **B** | PHI de-id hardening (Presidio) | BE | ✅ | Phase 0; Synthea(WS-E) for benchmark | yes (`PHI_ENGINE`) |
| **E** | Quick wins (CLAUDE.md + Synthea) | docs+test | ✅ | Phase 0 | no |
| **A** | Clinical NLP (medspaCy + local NER) | BE | ⚠️ touches files C & D also touch | Phase 0; **C, D, E merged**; medspaCy before NER fast-path | yes (`EXTRACTION_ENGINE`) |

### Dependency DAG
```
Phase 0 ──┬─► WS-U ───────────────────────────────► merge
          ├─► WS-T ───────────────────────────────► merge
          ├─► WS-C ──────────────┐
          ├─► WS-D ──────────────┤
          ├─► WS-E (Synthea) ────┼──► WS-A ────────► merge (last)
          └─► WS-B ──────────────┘
```

### File-ownership matrix (conflict avoidance for parallel worktrees)
| File / area | Owner | Shared-write risk |
|---|---|---|
| `backend/app/config.py` | **Phase 0** (all flags in one commit) | none after Phase 0 |
| `backend/pyproject.toml` | **Phase 0** (decided deps) + WS-A/WS-B add their model deps in-branch | coordinate: A/B append only, no reorder |
| `backend/app/schemas/timeline.py`, `api/timeline.py`, `services/timeline_preview.py` | WS-T | none |
| `frontend timeline/page.tsx`, `types/api.ts`, `TimelineMetricStrip.tsx` | WS-T | none |
| `frontend stores/useExtractionStore.ts(+spec)` | WS-U | none |
| `services/extraction/terminology.py` | WS-C (adds fuzzy) | **WS-A reads it (read-only)** → land C first |
| `services/dedup/detector.py` | WS-C | none |
| `services/extraction/entity_to_fhir.py`, `services/ingestion/fhir_parser.py` | **WS-D** (validation hook) | **WS-A also edits** → land D first, A rebases |
| `services/extraction/section_parser.py`, `entity_validator.py`, `entity_extractor.py`, `local_ner.py`(new) | WS-A | none |
| `services/ai/phi_scrubber.py`, `patient_phi.py`, `phi_ner.py` | WS-B | none |
| `conftest.py`, `tests/fixtures/synthea/` | WS-E | WS-A/B consume read-only |
| `CLAUDE.md` | WS-E (wording only; **never push to remote**) | none |

### Worktree & branch strategy
- Base branch off `main`: `feat/2026-06-20-combined` (Phase 0 lands here).
- Each workstream in its own worktree/branch off the Phase-0 base: `ws-u-statusbar`, `ws-t-timeline`, `ws-c-rapidfuzz`, `ws-d-fhir-validate`, `ws-b-presidio`, `ws-e-quickwins`, `ws-a-clinical-nlp`. Use the `superpowers:using-git-worktrees` skill (native worktrees) at each agent's start.
- **Merge order:** Phase 0 → (U, T, C, D, E, B in any order as they finish) → **A last** (rebase on C/D/E). Each merge is a PR; flags keep half-finished OSS paths dormant on `main`.

### Shadow-compare & flag-flip protocol (WS-A, WS-B; WS-C terminology; WS-D)
1. New path ships **default-off**. 2. Run new vs old on the **Synthea corpus + retained real fixtures**; log diffs + latency. 3. Gate the default flip on parity (entity-set/PHI-recall tolerance met) — a separate follow-up commit, never bundled with the implementation. 4. Rollback = flip the flag.

---

## Phase 0 — Shared Groundwork (serialized; ONE owner; runs before any fan-out)

### Task 0.1: Base branch + flags + decided deps + contract freeze

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/pyproject.toml`
- Create: `backend/app/schemas/timeline.py` (add models — see WS-T Task T1 for exact shapes; commit them here to freeze the cross-agent contract)

- [ ] **Step 1: Branch.** `git checkout -b feat/2026-06-20-combined`
- [ ] **Step 2: Add all config flags** to `config.py` Settings (defaults per Global Constraints), each with a one-line comment. No behavior wired yet — just the typed settings, so parallel agents never touch `config.py` again.
- [ ] **Step 3: Add the decided runtime deps** to `pyproject.toml`: `rapidfuzz` (WS-C). Leave WS-A/WS-B/WS-D model/library deps to their branches (they append). `fhir.resources`/`fhirpathpy` are already declared (WS-D).
- [ ] **Step 4: Freeze the `TimelinePreview` contract** — add `TimelineGauge` + `TimelinePreview` Pydantic models and the `preview` field to `TimelineEvent` in `schemas/timeline.py` exactly as WS-T Task T1 defines. (Backend builder + frontend type both consume this; freezing here prevents drift between the WS-T backend and frontend agents.)
- [ ] **Step 5: Verify** the app imports: `cd backend && .venv/bin/python -c "from app.config import settings; from app.schemas.timeline import TimelinePreview, TimelineGauge, TimelineEvent; print('ok')"` → `ok`.
- [ ] **Step 6: Commit.** `git add -A && git commit -m "chore: phase-0 groundwork — config flags, rapidfuzz dep, TimelinePreview contract"`

---

## WS-U — Status-Bar Concurrent-Batch Fix  *(worktree `ws-u-statusbar`)*

**Design:** `…/2026-06-20-extraction-statusbar-concurrent-batch-fix.md`

### Task U1: `startBatch` merges into an in-flight batch instead of replacing it

**Files:**
- Modify: `frontend/src/stores/useExtractionStore.ts` (the `startBatch` action, ~L90-101)
- Test: `frontend/src/stores/useExtractionStore.unit.spec.ts` (add cases)

**Interfaces:**
- Consumes: `isTerminalStatus` (already imported from `@/lib/extraction-progress`), `toTracked`, `TrackedFileInput` (existing).
- Produces: unchanged public signature `startBatch(files: TrackedFileInput[]): void` — behavior change only.

- [ ] **Step 1: Write the failing tests.** Append to `useExtractionStore.unit.spec.ts`:

```ts
import { useExtractionStore } from "./useExtractionStore";

test.describe("startBatch merge-or-replace", () => {
  test.beforeEach(() => useExtractionStore.getState().reset());

  test("merges a new upload into an in-flight batch", () => {
    const s = useExtractionStore.getState();
    s.startBatch([{ upload_id: "A", filename: "a.pdf", status: "processing" }]);
    s.startBatch([{ upload_id: "B", filename: "b.pdf", status: "pending_extraction" }]);
    const st = useExtractionStore.getState();
    expect(st.batchIds).toEqual(["A", "B"]);
    expect(Object.keys(st.files).sort()).toEqual(["A", "B"]);
    expect(st.dismissed).toBe(false);
  });

  test("replaces when the prior batch is fully terminal", () => {
    const s = useExtractionStore.getState();
    s.startBatch([{ upload_id: "A", filename: "a.pdf", status: "processing" }]);
    useExtractionStore.getState().mergeFileStatuses([{ id: "A", ingestion_status: "completed" }]);
    useExtractionStore.getState().startBatch([{ upload_id: "B", filename: "b.pdf", status: "pending_extraction" }]);
    const st = useExtractionStore.getState();
    expect(st.batchIds).toEqual(["B"]);
    expect(Object.keys(st.files)).toEqual(["B"]);
  });

  test("does not duplicate an already-tracked id", () => {
    const s = useExtractionStore.getState();
    s.startBatch([{ upload_id: "A", filename: "a.pdf", status: "processing" }]);
    s.startBatch([{ upload_id: "A", filename: "a.pdf", status: "processing" }]);
    expect(useExtractionStore.getState().batchIds).toEqual(["A"]);
  });
});
```

- [ ] **Step 2: Run to verify FAIL.** `cd frontend && npx playwright test --config playwright.unit.config.ts useExtractionStore` → Expected: the "merges" test FAILS (`batchIds` is `["B"]`, not `["A","B"]`).
- [ ] **Step 3: Implement merge-or-replace.** Replace the `startBatch` action body:

```ts
startBatch: (input) =>
  set((state) => {
    const priorInFlight = Object.values(state.files).some(
      (f) => !isTerminalStatus(f.status)
    );
    if (priorInFlight) {
      // A prior batch is still extracting — accumulate, don't drop it.
      const files = { ...state.files };
      const batchIds = [...state.batchIds];
      for (const f of input) {
        if (!files[f.upload_id]) batchIds.push(f.upload_id);
        files[f.upload_id] = toTracked(f);
      }
      return { batchIds, files, dismissed: false };
    }
    // Prior batch finished (or none) — fresh batch (anti-stale, original intent).
    const files: Record<string, TrackedFile> = {};
    for (const f of input) files[f.upload_id] = toTracked(f);
    return {
      batchIds: input.map((f) => f.upload_id),
      files,
      progress: null,
      dismissed: false,
      cancelling: [],
    };
  }),
```

- [ ] **Step 4: Run to verify PASS.** `npx playwright test --config playwright.unit.config.ts useExtractionStore` → all PASS.
- [ ] **Step 5: Manual repro** (project verification order): restart nothing (FE hot-reloads). In the app, upload one PDF; while it's `processing`, upload a second. The bottom-right pane reads **"… of 2"** and lists both; Admin → Extractions also shows 2. Confirms parity.
- [ ] **Step 6: Commit.** `git add frontend/src/stores/useExtractionStore.ts frontend/src/stores/useExtractionStore.unit.spec.ts && git commit -m "fix: extraction status bar accumulates concurrent uploads instead of dropping the prior batch"`

---

## WS-T — Timeline Rich Rows  *(worktree `ws-t-timeline`)*

**Design:** `…/2026-06-20-timeline-rich-rows-design.md`. The `TimelinePreview`/`TimelineGauge` schema is frozen in Phase 0 Task 0.1 — WS-T consumes it.

### Task T1: Preview schema (verify the frozen contract)

**Files:**
- Verify/Modify: `backend/app/schemas/timeline.py`

**Interfaces:**
- Produces: `TimelineGauge(value: float, low: float, high: float)`; `TimelinePreview(value: str|None, unit: str|None, flag: str|None, emphasis: str|None, gauge: TimelineGauge|None, facets: list[str])`; `TimelineEvent.preview: TimelinePreview|None`.

- [ ] **Step 1:** Confirm Phase 0 added exactly:

```python
class TimelineGauge(BaseModel):
    value: float
    low: float
    high: float
    model_config = {"from_attributes": True}

class TimelinePreview(BaseModel):
    value: str | None = None
    unit: str | None = None
    flag: str | None = None
    emphasis: str | None = None          # "normal" | "notable" | "muted" (neutral only)
    gauge: TimelineGauge | None = None
    facets: list[str] = []
    model_config = {"from_attributes": True}
```
and `preview: TimelinePreview | None = None` on `TimelineEvent`. If Phase 0 differs, reconcile to this and note it.
- [ ] **Step 2: Commit** only if changed: `git commit -am "chore: confirm TimelinePreview schema"`.

### Task T2: `build_timeline_preview` — lab branch (test-first)

**Files:**
- Create: `backend/app/services/timeline_preview.py`
- Test: `backend/tests/test_timeline_preview.py`

**Interfaces:**
- Produces: `build_timeline_preview(fhir_resource: dict | None, record_type: str) -> TimelinePreview | None`.

- [ ] **Step 1: Write the failing test** (`tests/test_timeline_preview.py`):

```python
from __future__ import annotations
from app.services.timeline_preview import build_timeline_preview
from app.schemas.timeline import TimelineGauge

def _lab(value, unit, interp=None, low=None, high=None):
    r = {"resourceType": "Observation",
         "category": [{"coding": [{"code": "laboratory"}]}],
         "valueQuantity": {"value": value, "unit": unit}}
    if interp:
        r["interpretation"] = [{"coding": [{"code": interp}]}]
    if low is not None and high is not None:
        r["referenceRange"] = [{"low": {"value": low}, "high": {"value": high}}]
    return r

def test_lab_with_range_and_low_flag():
    p = build_timeline_preview(_lab(17, "ng/mL", "L", 30, 100), "observation")
    assert p is not None
    assert p.value == "17" and p.unit == "ng/mL"
    assert p.flag == "LOW" and p.emphasis == "notable"
    assert p.gauge == TimelineGauge(value=17, low=30, high=100)

def test_lab_normal_has_no_flag_no_gauge_when_range_absent():
    p = build_timeline_preview(_lab(5.0, "mIU/L", "N"), "observation")
    assert p.value == "5" and p.unit == "mIU/L"
    assert p.flag is None and p.emphasis == "normal" and p.gauge is None

def test_lab_non_numeric_value_yields_no_gauge():
    r = {"resourceType": "Observation", "category": [{"coding": [{"code": "laboratory"}]}],
         "valueString": "Detected"}
    p = build_timeline_preview(r, "observation")
    assert p.value == "Detected" and p.gauge is None
```

- [ ] **Step 2: Run to verify FAIL.** `cd backend && .venv/bin/python -m pytest tests/test_timeline_preview.py -x -q` → FAIL (module missing).
- [ ] **Step 3: Implement the module skeleton + lab branch:**

```python
from __future__ import annotations
from typing import Any
from app.schemas.timeline import TimelinePreview, TimelineGauge

_ABNORMAL = {"H": "HIGH", "L": "LOW", "HH": "CRIT HIGH", "LL": "CRIT LOW",
             "A": "ABNORMAL", "AA": "CRIT", "POS": "POSITIVE"}
_NORMAL = {"N", "NR", "WNL", "NEG"}

def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _fmt(v: Any) -> str | None:
    n = _num(v)
    if n is None:
        return str(v).strip() if v not in (None, "") else None
    return str(int(n)) if n == int(n) else str(n)

def _obs_category(r: dict) -> str:
    for cat in r.get("category", []) or []:
        for c in (cat.get("coding") or []):
            code = (c.get("code") or "").lower()
            if code in ("laboratory", "vital-signs", "social-history"):
                return code
    return "laboratory"

def _lab(r: dict) -> TimelinePreview:
    vq = r.get("valueQuantity") or {}
    value = _fmt(vq.get("value")) if vq else _fmt(r.get("valueString"))
    unit = (vq.get("unit") or "").strip() or None
    flag, emphasis = None, "normal"
    for ic in (r.get("interpretation") or []):
        for c in (ic.get("coding") or []):
            code = (c.get("code") or "").upper()
            if code in _ABNORMAL:
                flag, emphasis = _ABNORMAL[code], "notable"
            elif code in _NORMAL:
                emphasis = "normal"
    gauge = None
    rng = (r.get("referenceRange") or [{}])[0]
    lo, hi, val = _num((rng.get("low") or {}).get("value")), _num((rng.get("high") or {}).get("value")), _num(vq.get("value"))
    if lo is not None and hi is not None and val is not None and hi != lo:
        gauge = TimelineGauge(value=val, low=lo, high=hi)
    return TimelinePreview(value=value, unit=unit, flag=flag, emphasis=emphasis, gauge=gauge, facets=[])

def build_timeline_preview(fhir_resource: dict | None, record_type: str) -> TimelinePreview | None:
    if not isinstance(fhir_resource, dict):
        return None
    if record_type == "observation":
        cat = _obs_category(fhir_resource)
        if cat == "laboratory":
            p = _lab(fhir_resource)
            return p if (p.value or p.flag) else None
    return None
```

- [ ] **Step 4: Run to verify PASS.** `.venv/bin/python -m pytest tests/test_timeline_preview.py -x -q` → PASS.
- [ ] **Step 5: Commit.** `git add backend/app/services/timeline_preview.py backend/tests/test_timeline_preview.py && git commit -m "feat(timeline): preview builder — lab branch"`

### Task T3: builder — vital, social, condition, medication, allergy, procedure, immunization, encounter; null fallback

**Files:**
- Modify: `backend/app/services/timeline_preview.py`
- Test: `backend/tests/test_timeline_preview.py`

- [ ] **Step 1: Write failing tests** — one per branch. Concrete assertions to implement against:
  - **vital BP:** `component[]` with codes `8480-6` (sys) + `8462-4` (dia) → `value=="120/80"`, `unit` from component or "mmHg".
  - **vital simple:** `valueQuantity {value:98.6, unit:"degF"}` → `value=="98.6"`.
  - **social:** `valueCodeableConcept.text == "Former smoker"` → `value=="Former smoker"`, no gauge.
  - **condition active:** `clinicalStatus.coding[0].code=="active"` → `flag=="ACTIVE"`, `emphasis=="normal"`, facet `"onset 2024"` from `onsetDateTime:"2024-03-01"`.
  - **condition negated/resolved:** code `"resolved"` → `flag=="RESOLVED"`, `emphasis=="muted"`.
  - **medication:** `dosageInstruction[0].doseAndRate[0].doseQuantity{value:20,unit:"mg"}` → `value=="20 mg"`; `route.text=="oral"` + `timing.code.text=="1×/day"` → `facets==["oral","1×/day"]`; `status=="active"` → `flag=="ACTIVE"`.
  - **allergy:** `criticality=="high"` → `flag=="HIGH"`, `emphasis=="notable"`; `reaction[0].manifestation[0].text=="hives"` → facet `"hives"`.
  - **procedure:** `status=="completed"` → `flag=="COMPLETED"`; `bodySite[0].text` → facet.
  - **immunization:** `status=="completed"` → `flag=="COMPLETED"`; `protocolApplied[0].doseNumberPositiveInt==2` → facet `"dose 2"`.
  - **encounter:** `class.code=="AMB"` → `flag=="Ambulatory"`; `reasonCode[0].text` → facet.
  - **null fallback:** `{"resourceType":"DocumentReference"}` with no useful fields → `build_timeline_preview(...) is None`.
- [ ] **Step 2: Run to verify FAIL.** Same pytest command — new tests fail.
- [ ] **Step 3: Implement** each branch in `timeline_preview.py` (helpers `_vital`, `_social`, `_condition`, `_medication`, `_allergy`, `_procedure`, `_immunization`, `_encounter`; dispatch by `record_type` and observation sub-category). Status→flag maps; abnormal/criticality→`emphasis="notable"`; inactive/resolved/stopped/not-done→`emphasis="muted"`. Return `None` when no field populates. Keep each helper small and pure (dict-in → `TimelinePreview`-out), **no `fhir.resources`**.
- [ ] **Step 4: Run to verify PASS** (full file) → PASS. Run fast suite `python -m pytest -m "not slow" -q` to confirm no regressions.
- [ ] **Step 5: Commit.** `git commit -am "feat(timeline): preview builder — all remaining types + null fallback"`

### Task T4: Wire builder into the timeline API

**Files:**
- Modify: `backend/app/api/timeline.py` (event construction loop, ~L53-64)
- Test: `backend/tests/test_timeline.py` (or the existing timeline test module)

- [ ] **Step 1: Write failing API test** — seed a lab record with `valueQuantity`+`interpretation`+`referenceRange`, GET `/timeline`, assert the event's `preview.value`/`preview.flag`/`preview.gauge` populate; seed a document record, assert its `preview is None`. (Use `auth_headers()`, `create_test_patient()`, `seed_test_records()` from `conftest.py`.)
- [ ] **Step 2: Run to verify FAIL** (`preview` absent/None).
- [ ] **Step 3: Implement** — import `build_timeline_preview` and add `preview=build_timeline_preview(r.fhir_resource, r.record_type)` to the `TimelineEvent(...)` constructor. No new query (resource already loaded).
- [ ] **Step 4: Run to verify PASS.**
- [ ] **Step 5: Commit.** `git commit -am "feat(timeline): include scalar preview in /timeline payload"`

### Task T5: Frontend type + `TimelineMetricStrip` + row placement

**Files:**
- Modify: `frontend/src/types/api.ts` (add `TimelinePreview`/`TimelineGauge`; add `preview?` to `TimelineEvent`)
- Create: `frontend/src/components/retro/TimelineMetricStrip.tsx`
- Modify: `frontend/src/app/(dashboard)/timeline/page.tsx` (insert strip between title L166 and provider L167)

**Interfaces:**
- Consumes: `Gauge` from `@/components/retro/DataViz` (`{value, low, high}` — already theme-neutral).
- Produces: `<TimelineMetricStrip preview={...} />` (renders `null` when preview is empty).

- [ ] **Step 1: Add the TS types** mirroring the Pydantic contract; add `preview?: TimelinePreview` to `TimelineEvent`.
- [ ] **Step 2: Build `TimelineMetricStrip`** — renders, when `preview` has any of value/flag/gauge/facets: `value`+dimmed `unit`, a flag chip whose class derives from `emphasis` (`normal`→default, `notable`→subtle theme accent token, `muted`→dimmed), the reused `<Gauge>` when `preview.gauge`, then facet chips (cap 3, "+N" overflow). Returns `null` otherwise. Tailwind + theme tokens only; **no good/bad colors**.
- [ ] **Step 3: Place it** in `timeline/page.tsx` between `tl-title` and the provider block: `{r.preview && <TimelineMetricStrip preview={r.preview} />}`.
- [ ] **Step 4: Live smoke** (memory: *Live Smoke Before Commit*) — mint a JWT for the dev user, inject localStorage, load `/timeline`, confirm lab rows show value+flag+gauge and a document row shows no strip; check the browser console is clean (console-error gate).
- [ ] **Step 5: Commit.** `git add frontend/src/types/api.ts frontend/src/components/retro/TimelineMetricStrip.tsx "frontend/src/app/(dashboard)/timeline/page.tsx" && git commit -m "feat(timeline): inline metric strip with neutral flags + reference gauge"`

### Task T6: Timeline render regression (console-gated)

**Files:**
- Modify/Create: a Playwright spec under `frontend/e2e/` (or extend an existing timeline spec) importing `test`/`expect` from the console-gate fixture.

- [ ] **Step 1:** Seed (or mock `/timeline`) a lab event with a populated `preview` and a document event with `preview: null`; assert the lab row shows the value + flag chip and the doc row shows no strip; the global console-error gate guards React key/`console.error`.
- [ ] **Step 2: Run** `cd frontend && npx playwright test <spec> --workers=1` → PASS.
- [ ] **Step 3: Commit.** `git commit -am "test(timeline): metric-strip render under console-error gate"`

---

## WS-C — RapidFuzz (terminology + dedup)  *(worktree `ws-c-rapidfuzz`)*

**Design:** `docs/oss-adoption-design.md` §WS-C. **Land before WS-A** (both reference `terminology.py`).

### Task C1: dedup matcher swap (like-for-like, test-guarded)
- **Files:** `backend/app/services/dedup/detector.py` (`_fuzzy_match`); tests `tests/test_dedup_*` incl. `TestDateDistancePenalty`, band-filter, resolve-bulk.
- [ ] Write/extend tests asserting current scoring/banding outputs are **unchanged** at boundaries → run (some may already pass) → replace `_fuzzy_match` body with `rapidfuzz.fuzz.token_set_ratio(...)/100`, preserving additive weights + integer-percent banding → run → confirm banding regressions green → commit.

### Task C2: terminology high-threshold fuzzy fallback (flagged off)
- **Files:** `backend/app/services/extraction/terminology.py`; tests `tests/test_terminology.py`.
- [ ] Write guardrail tests: a near-miss known term codes correctly **above** threshold; a below-threshold term returns `None` (never a wrong code) → implement a RapidFuzz fallback after exact/normalized lookup, gated by `TERMINOLOGY_FUZZY_ENABLED` (default off), threshold a named constant → run → tune threshold against fixtures so "unknown stays uncoded" holds → commit.

> Kickoff note: the exact threshold is an **open decision** (design §7.5) — set empirically; document the chosen value + the negative-test corpus in the commit.

---

## WS-D — FHIR Structural Validation  *(worktree `ws-d-fhir-validate`)*

**Design:** `docs/oss-adoption-design.md` §WS-D (Option A, log-only). **Land before WS-A** (both edit `entity_to_fhir.py`/`fhir_parser.py`).

### Task D1: log-only structural validator
- **Files:** new `backend/app/services/ingestion/fhir_validation.py`; hooks in `entity_to_fhir.py` (after AI resource build) + `fhir_parser.py` (after map); tests `tests/test_fhir_validation.py`.
- [ ] Write failing tests: malformed resource (missing required field) is **logged but still returned** in `log` mode; a valid Synthea resource passes silently; a partial AI resource does **not** produce false-failure noise → implement validation against `fhir.resources` R4B models, **fail-open non-latching** (library hiccup never blocks ingestion), gated by `FHIR_VALIDATION=off|log|strict` (default `log`; `strict` never applied to AI resources) → run → commit.

> Kickoff note: the **required-field subset / log level** that avoids noise on partial AI resources is the open decision (design §7.4) — tune against the 18 `SUPPORTED_RESOURCE_TYPES` + extraction outputs.

---

## WS-E — Quick Wins  *(worktree `ws-e-quickwins`)*

**Design:** `docs/oss-adoption-design.md` §WS-E. **Synthea fixtures must land before WS-A/WS-B parity/benchmark work.**

### Task E1: CLAUDE.md license wording
- **Files:** `CLAUDE.md` (terminology gotcha). **Never push CLAUDE.md to remote.**
- [ ] Edit the gotcha to separate **CPT** (AMA paid, permanent exclusion) from **SNOMED CT** (free under UMLS Affiliate License but redistribution/reporting makes *bundling* impractical); note the legitimate future path = opt-in, operator-licensed SNOMED, never bundled. Commit locally.

### Task E2: Synthea synthetic fixtures
- **Files:** new generator script under `backend/scripts/`; fixtures under `tests/fixtures/synthea/`; wire into `conftest.py`/fidelity fixtures.
- [ ] Add a Synthea-driven generator producing FHIR R4 bundles (+ optional C-CDA); smoke test: generated bundles ingest cleanly through `fhir_parser` and yield expected record counts/types → wire a fixture other suites can opt into → commit. Real user fixtures stay gitignored (Rule 10).

---

## WS-B — PHI De-id Hardening (Presidio)  *(worktree `ws-b-presidio`)*

**Design:** `docs/oss-adoption-design.md` §WS-B. Independent; uses Synthea + retained fixtures for the recall benchmark.

### Tasks (kickoff sub-plan authors the bite-sized steps)
- [ ] **B1 — pyproject:** append `presidio-analyzer`(+`presidio-anonymizer`); the clinical location model dep behind its own extra.
- [ ] **B2 — Layer 1 → Presidio recognizers** (test-first parity): port every existing scrubber regression (SSN/phone/MRN/address/account/accession/date-generalization) to the Presidio path behind `PHI_ENGINE=presidio`; legacy stays default.
- [ ] **B3 — Layer 2 re-homed:** decrypt-known-identity as a Presidio deny-list/ad-hoc recognizer fed name/MRN/DOB (preserve the `name_encrypted`-NULL leak defense).
- [ ] **B4 — Layer 3 re-homed:** eponym/clinical-suffix allowlist around `PERSON` (Crohn's/Hodgkin/Gastroenterology survive); keep NER **fail-open non-latching**.
- [ ] **B5 — close the city gap:** `LOCATION` pass via a **clinical** de-id model (Stanford deidentifier or OBI RoBERTa — open decision §7.3) behind `PHI_LOCATION_NER_ENABLED`; add drug-as-place negatives (`Rifaximin` must survive).
- [ ] **B6 — recall benchmark harness:** i2b2-style held-out **recall** measurement; record before/after.
- [ ] **B7 — shadow-compare** then flag-flip in a separate commit once recall parity met.

> Kickoff: resolve the location-model choice (§7.3) with a quick bake-off before B5; this WS warrants its own fully-bite-sized sub-plan authored at start (external Presidio/transformers APIs).

---

## WS-A — Clinical NLP (medspaCy + local NER)  *(worktree `ws-a-clinical-nlp`; merge LAST)*

**Design:** `docs/oss-adoption-design.md` §WS-A. **Prereqs merged:** WS-C, WS-D, WS-E (Synthea). Internal order: **medspaCy precedes the NER fast-path.**

### Tasks (kickoff sub-plan authors the bite-sized steps)
- [ ] **A0 — engine bake-off (open decision §7.1):** scispaCy `en_ner_bc5cdr_md` vs GLiNER-biomed on real notes (accuracy/latency); pick one behind the `local_ner` interface. Append the chosen dep to `pyproject.toml`.
- [ ] **A1 — medspaCy `ClinicalContext` stage:** `section_detection` replaces `section_parser.py`; `context` (ConText) replaces negation/family/experiencer guards (negated→FHIR `inactive` preserved); `postprocess` replaces `entity_validator.py` drop-rules. Migrate `test_entity_validator`/`test_extraction_prompt_guards` expectations as the test oracle.
- [ ] **A2 — `services/extraction/local_ner.py`:** chosen engine; map spans to codes via existing bundled RxNorm/ICD-10 indexes (`terminology.py`, read-only — WS-C already merged); **no UMLS**.
- [ ] **A3 — escalation policy:** low-confidence spans/sections escalate to LangExtract/Gemini; rest stay local. Threshold = open decision §7.5.
- [ ] **A4 — pipeline wiring** in `_process_unstructured` behind `EXTRACTION_ENGINE=gemini|local|hybrid` (default `gemini`).
- [ ] **A5 — parity/shadow tests:** `local`/`hybrid` vs `gemini` on Synthea + real fixtures; entity-set parity within tolerance + latency (target: ~6.5 min/note → seconds for local path).
- [ ] **A6 — flip default to `hybrid`** only after parity, in a separate commit.

> Kickoff: this is the largest WS and edits files WS-C/WS-D touched — **rebase on their merges first**, then author its fully-bite-sized sub-plan.

---

## Self-Review (performed against the three specs)

- **Spec coverage:** WS-U ✅ (statusbar spec §3-5). WS-T ✅ (data contract, all per-type mappings T2/T3, API wiring T4, FE strip T5, tests T6, neutral-emphasis honored). OSS WS-A…E ✅ mapped to tasks with design-doc refs + open-decision callouts (§7 items each surfaced as a kickoff task). Quick wins ✅ (E1/E2).
- **Placeholder scan:** WS-U and WS-T contain complete, runnable code + exact commands. OSS workstreams are **intentionally task-level** (not placeholders): they reference the approved design and defer bite-sized steps to each WS's kickoff because of unresolved open decisions and external-library APIs — fabricating that code would be a plan failure. This deferral is faithful to `oss-adoption-design.md` §9 ("granular plan … authored in a later session").
- **Type consistency:** `TimelinePreview`/`TimelineGauge` shape identical in Phase 0, T1, T4 (backend) and T5 (TS mirror); `build_timeline_preview(fhir_resource, record_type)` signature identical in T2/T3/T4; `startBatch` signature unchanged in WS-U; flag names identical between Global Constraints and WS-A/B/C/D.
- **Conflict review:** `terminology.py` (C writes / A reads) and `entity_to_fhir.py`+`fhir_parser.py` (D writes / A writes) resolved by merge order (C, D before A) in the orchestration section.

---

## Execution Handoff — Agent Team

Per memory (*Agent Teams*; *Subagent-Dev Disabled*), execute with an **agent team**, not `subagent-driven-development`:

1. **Land Phase 0 first** (serialized, one agent) on `feat/2026-06-20-combined` — freezes flags, deps, and the `TimelinePreview` contract.
2. **Fan out** named agents in isolated worktrees off the Phase-0 base: `ws-u`, `ws-t`, `ws-c`, `ws-d`, `ws-e` can all run **concurrently**; `ws-b` too. Each follows its tasks test-first.
3. **`ws-a` starts after `ws-c`, `ws-d`, `ws-e` merge** (rebase on them).
4. **Merge order:** Phase 0 → U/T/C/D/E/B (as they finish) → A last. Each via PR; OSS paths stay dormant behind default-off flags until shadow-validated.
5. **Default flips** (WS-A `hybrid`, WS-B `presidio`/location, WS-C terminology fuzzy, WS-D `log`→stays) are **separate follow-up commits** gated on parity/recall — never bundled with implementation.

**Note:** these docs are written but **not committed** (project rule: commit only when you ask, and `main` would need a branch first). Say the word and I'll create `feat/2026-06-20-combined` and commit the three specs + this plan as the Phase-0 starting point.
