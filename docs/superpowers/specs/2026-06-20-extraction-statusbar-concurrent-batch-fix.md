# Design — Extraction Status Bar: concurrent-upload batch fix

**Date:** 2026-06-20
**Status:** Root cause confirmed (read-only investigation); fix designed, folded into the combined implementation plan.
**Scope:** Frontend state bug. The floating "Extracting documents" status pane under-counts when a second upload starts while a first is still extracting.

---

## 1. Symptom

Upload file A; while A is still `processing`, upload file B. The **Admin → Extractions** tab correctly shows **"2 processing"** (A + B), but the bottom-right floating **GlobalExtractionStatusBar** shows **"0 of 1"** — A has vanished from it. A is *not* lost: it keeps extracting on the backend and still produces records. Only the floating widget's tracked batch is wrong.

## 2. Root cause

The floating widget renders from a single Zustand "current batch" store, `useExtractionStore` (`frontend/src/stores/useExtractionStore.ts`). Its `startBatch` action **unconditionally replaces** the prior batch (`batchIds`, `files`, `progress`, `cancelling` all reset). Every upload calls it (`frontend/src/app/(dashboard)/upload/page.tsx:430`, plus retry/history paths at `:490`, `:503`).

So the second upload's `startBatch([B])` **wipes** `[A]`. The widget then polls progress scoped to `batchIds=[B]` only → "0 of 1". The Admin tab is unaffected because it queries the backend for *all* processing files, not this store.

The replace was **intentional** — the store comment (§2a ii) wanted a *new* upload to not show **stale rows from a previously-finished batch**. The flaw: it conflates "prior batch finished" (safe to replace) with "prior batch still in-flight" (must append).

## 3. Fix

Make `startBatch` **merge** into the existing batch **iff the prior batch still has any non-terminal file**; otherwise **replace** (preserving the anti-stale behavior).

- **Rule:** `merge = Object.values(state.files).some(f => !isTerminalStatus(f.status))`.
  - **Merge:** union `batchIds` (dedup, preserve order, append new), spread-merge `files`, clear `dismissed`, keep `progress` (next poll tick refreshes it for the union), preserve `cancelling` for files still in flight.
  - **Replace:** current behavior (fresh batch) — covers "completed/dismissed batch, then a new upload".
- A dismissed batch is always terminal (the Dismiss button only renders when `batch.allTerminal`, `GlobalExtractionStatusBar.tsx:276`), so dismissed → replace falls out of the same rule; no special case.

**Why this is safe:** the polling loop keys off `batchIds` identity; a merged (new) array re-arms the interval and `api.getExtractionProgress(batchIds)` re-scopes to the union, so counts and per-file rows reflect both A and B.

## 4. Files

- `frontend/src/stores/useExtractionStore.ts` — rewrite `startBatch` (merge-or-replace).
- `frontend/src/stores/useExtractionStore.unit.spec.ts` — **currently codifies pure-replace**; update to assert: in-flight prior → union; terminal prior → replace.
- No backend change. No change to the three call sites (they keep calling `startBatch`).

## 5. Testing (TDD — expected output first)

- **Unit** (`useExtractionStore.unit.spec.ts`): (a) start `[A]` (processing) → start `[B]` ⇒ `batchIds == [A,B]`, both in `files`, `dismissed=false`; (b) start `[A]` then mark A terminal → start `[B]` ⇒ `batchIds == [B]` (replace); (c) re-adding an already-tracked id doesn't duplicate it.
- **E2E** (optional, under the console-error gate): two sequential `/upload/unstructured` posts with the first still processing, then assert the status pane count equals the Admin Extractions processing count. The existing real-Gemini extraction specs can flake on latency — prefer the deterministic unit coverage as the gate; treat e2e as confirmatory.
- **Manual** (project verification order): reproduce the original two-file flow; the pane should read "… of 2".

## 6. Risk

Low, isolated to one store action. The only behavioral change is additive (in-flight batches now accumulate); the finished-then-new-upload path is unchanged. Regression guard is the updated unit spec.
