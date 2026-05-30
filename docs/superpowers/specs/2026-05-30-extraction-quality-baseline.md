# Extraction Quality Baseline — 2026-05-30

**Branch:** `feat/extraction-quality-eval`
**Test file:** `backend/tests/test_extraction_eval.py`
**Extractor:** `extract_entities_async` via LangExtract + `gemini-2.5-flash`
**Scorer:** `app/services/extraction/eval/scorer.py`

---

## Fixture 1: `transcript_visit.txt`

### Input text
```
Dr. Lee: Good morning. What brings you in today?
Patient: I've had this burning stomach pain since about last week.
Dr. Lee: Are you taking anything for it?
Patient: Just something over the counter for my stomach. I stopped taking my lisinopril though.
Dr. Lee: Okay. Any history of diabetes?
Patient: No, never had diabetes. But my father had colon cancer.
Dr. Lee: Your blood pressure today is 142 over 90. I'm noting hypertension.
Dr. Lee: Generally, untreated reflux can cause esophagitis, but let's not get ahead of ourselves.
```

### Ground truth
| Field | Values |
|---|---|
| Expected | `vital:142/90`, `condition:hypertension` |
| Must-not-extract (negation) | `condition:diabetes` |
| Must-not-extract (attribution) | `condition:colon cancer` |
| Must-not-extract (educational) | `condition:esophagitis` |
| Expected family history | `family_history:colon cancer` |

### Eval result (verbatim)
```
[eval transcript_visit.txt] P=0.17 R=0.50 F1=0.25 negation=1.00 attribution=1.00
  | false=[]
  | missed=['vital:142/90']
  | extracted=['encounter:What brings you in today?', 'medication:lisinopril',
               'family_history:father had colon cancer', 'vital:142 over 90',
               'condition:hypertension', 'provider:Dr. Lee']
```

| Metric | Score |
|---|---|
| Precision | 0.17 |
| Recall | 0.50 |
| F1 | 0.25 |
| Negation accuracy | 1.00 |
| Attribution accuracy | 1.00 |

### Analysis

**What went right:**
- `condition:hypertension` correctly extracted (1 of 2 expected entities matched).
- `condition:diabetes` correctly NOT extracted despite being mentioned — negation guard worked perfectly (negation_accuracy = 1.00).
- `condition:colon cancer` correctly NOT extracted as a patient condition. The father's cancer was correctly labelled as `family_history:father had colon cancer` (attribution_accuracy = 1.00).
- `condition:esophagitis` correctly NOT extracted (educational/hypothetical context guard worked).

**What went wrong:**
- **Low precision (0.17):** 5 of 6 extracted entities were not in the expected list. This is a scorer artifact rather than a pure extractor failure: the expected set only covers 2 entities (`vital:142/90`, `condition:hypertension`), while the extractor also found `encounter`, `medication:lisinopril`, `family_history`, and `provider:Dr. Lee` which are clinically reasonable but not labelled in the ground truth. This inflates FP and deflates precision. The fixture's expected list is intentionally minimal (testing negation/attribution), so these are unlabelled true positives, not genuine hallucinations.
- **`vital:142/90` missed (recall = 0.50):** The extractor correctly found the vital but rendered the text as `"142 over 90"` (spoken English form from the transcript), while the expected label uses the numeric shorthand `"142/90"`. The scorer's substring match (`"142/90" in "142 over 90"`) did not fire because `"142/90"` is not a substring of `"142 over 90"`. This is a scorer normalization gap: the two forms are semantically identical but syntactically distinct. The extractor behaviour is correct; the fixture or normalizer should be updated to handle spoken BP notation.

---

## Fixture 2: `phone_note.txt`

### Input text
```
pt c/o HTN, on lisinopril 10mg. DM2 dx 2019, metformin 500 bid. allergic PCN.
no chest pain. mom breast ca.
```

### Ground truth
| Field | Values |
|---|---|
| Expected | `condition:hypertension`, `medication:lisinopril`, `condition:type 2 diabetes`, `medication:metformin`, `allergy:penicillin` |
| Must-not-extract (negation) | `condition:chest pain` |
| Must-not-extract (attribution) | `condition:breast cancer` |
| Expected family history | `family_history:breast cancer` |

### Eval result (verbatim)
```
[eval phone_note.txt] P=0.44 R=0.80 F1=0.57 negation=1.00 attribution=0.50
  | false=[]
  | missed=['allergy:penicillin']
  | extracted=['condition:HTN', 'medication:lisinopril', 'dosage:10mg',
               'condition:DM2', 'medication:metformin', 'dosage:500',
               'frequency:bid', 'allergy:PCN', 'family_history:mom breast ca']
```

| Metric | Score |
|---|---|
| Precision | 0.44 |
| Recall | 0.80 |
| F1 | 0.57 |
| Negation accuracy | 1.00 |
| Attribution accuracy | 0.50 |

### Analysis

**What went right:**
- `condition:HTN` correctly extracted (scorer synonym map resolves `htn` → `hypertension` — matched).
- `condition:DM2` correctly extracted (`dm2` → `type 2 diabetes` — matched).
- `medication:lisinopril` and `medication:metformin` both correctly extracted.
- `condition:chest pain` correctly NOT extracted despite being present in text ("no chest pain") — negation guard worked (negation_accuracy = 1.00).
- `condition:breast cancer` correctly NOT extracted as a patient condition.

**What went wrong:**

1. **Attribution accuracy = 0.50:** "mom breast ca" was extracted as `family_history:mom breast ca`. The scorer correctly matches it against `expected_family_history[{text: "breast cancer"}]` via fuzzy substring check — `"breast ca"` is in `"breast cancer"`? No: `"breast cancer"` is NOT in `"breast ca"`, and `"breast ca"` is NOT in `"breast cancer"`. So the family history item was NOT credited as matching. This is a scorer normalization gap: `"breast ca"` is an abbreviation for `"breast cancer"` but the current synonym/substring logic does not handle oncology abbreviations. The extractor behaviour (labelling it as family_history) is correct; the scorer needs a synonym or stemming expansion for `"breast ca"` → `"breast cancer"`.

2. **`allergy:penicillin` missed (recall = 0.80):** The extractor produced `allergy:PCN` (standard pharmacy abbreviation for penicillin), but the expected label is `"penicillin"`. The scorer's `_SYNONYMS` dict does not include `pcn` → `penicillin`, and neither string is a substring of the other. The extractor behaviour is correct; the scorer's synonym map needs `"pcn": "penicillin"`.

3. **Low precision (0.44):** 5 of 9 extracted entities were not in the expected list (`dosage:10mg`, `dosage:500`, `frequency:bid`, `allergy:PCN` — unlabelled true positive once synonym gap is fixed — and `family_history:mom breast ca` — also a true positive once synonym gap is fixed). The inflated FP count comes from unlabelled true positives plus dosage/frequency sub-entities that the expected set does not cover. No genuine hallucinations were observed (`false_extractions = []`).

---

## Cross-fixture summary

| Fixture | P | R | F1 | Negation | Attribution | False extractions | Missed |
|---|---|---|---|---|---|---|---|
| transcript_visit | 0.17 | 0.50 | 0.25 | 1.00 | 1.00 | none | `vital:142/90` (spoken form) |
| phone_note | 0.44 | 0.80 | 0.57 | 1.00 | 0.50 | none | `allergy:penicillin` (PCN abbrev) |

Both tests PASSED the `recall >= 0.5` floor. No hallucinations (false_extractions = [] for both).

---

## Top gaps for Phase 2b-2

These are the concrete, observed failures ranked by priority.

### Gap 1 — Scorer synonym gaps (highest priority, easy fix)

The extractor is producing clinically correct output; the scorer is failing to credit it because of missing normalization rules. Three instances observed:

- `"142 over 90"` vs `"142/90"` — spoken vs numeric blood pressure notation. Fix: add regex normalization for `(\d+) over (\d+)` → `\1/\2` in `scorer.normalize()`.
- `"breast ca"` vs `"breast cancer"` — oncology abbreviation. Fix: add `"breast ca": "breast cancer"` to `_SYNONYMS`.
- `"pcn"` vs `"penicillin"` — pharmacy abbreviation. Fix: add `"pcn": "penicillin"` to `_SYNONYMS`.

All three fixes would raise both fixtures' scores substantially without changing extractor behaviour.

### Gap 2 — Unlabelled true positives inflate FP (medium priority)

The expected sets in both fixtures are intentionally sparse (testing specific phenomena), causing the scorer to count clinically reasonable extractions as false positives. Specific unlabelled true positives observed:

- `transcript_visit`: `medication:lisinopril`, `family_history:father had colon cancer`, `provider:Dr. Lee`, `encounter:What brings you in today?`
- `phone_note`: `dosage:10mg`, `dosage:500`, `frequency:bid`

Recommendation: either expand the expected sets to cover these entities, or restructure the ground-truth format to include an `acceptable` list that is counted as TP but not required for recall.

### Gap 3 — Attribution for abbreviated family history (medium priority)

`"mom breast ca"` was extracted as `family_history:mom breast ca` (correct entity class), but the scorer did not credit the match because `"breast ca"` does not substring-match `"breast cancer"`. After synonym fix (Gap 1), attribution_accuracy for phone_note will improve to 1.00.

### Gap 4 — Negation working perfectly (no action needed)

Both fixtures scored negation_accuracy = 1.00. The extractor correctly suppressed `condition:diabetes` ("never had diabetes"), `condition:chest pain` ("no chest pain"), and did not extract `condition:colon cancer` or `condition:breast cancer` as patient conditions. This guard is robust and does not need improvement.

### Gap 5 — No hallucinations observed (no action needed)

`false_extractions = []` for both fixtures. The model did not extract `condition:esophagitis` (educational context) or misattribute family history as patient conditions. The hallucination guard is working.
