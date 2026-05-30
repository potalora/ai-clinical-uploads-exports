# How MedTimeline Measures AI Extraction Accuracy — A Plain-Language Guide

**Audience:** non-technical readers. Every term is defined when first used.

---

## 1. What the Extractor Does

MedTimeline helps you organize your health records. One way it does that is by reading unstructured
documents — PDFs, visit notes, even a quick phone note you typed yourself — and pulling out the
medically meaningful items inside them: medications you take, conditions you have, lab results,
allergies, and so on. We call this process **extraction**.

Once extracted, each item becomes a structured **health record** stored in the app (for example, an
entry in your medications list). "Structured" just means the information is stored in a consistent,
searchable format rather than as raw text.

### Why messy documents are harder than clean clinical notes

A tidy hospital discharge summary follows a standard template. An AI trained on such documents does
well on them. But real life produces messier documents:

- **Visit transcripts** — a recording of a doctor's appointment turned into text. Multiple people
  are speaking. The doctor might mention a common condition ("a lot of patients with hypertension
  …") that belongs to no one in particular. The patient uses casual language ("I stopped taking
  that pill a while back").
- **Phone/app notes** — a terse reminder you typed yourself: "HTN, DM2, check labs." No sentences,
  heavy abbreviations, no standard structure.

Both types introduce risks: the AI might pull out something it shouldn't (a false alarm) or miss
something it should catch (a gap). Without measuring, we can't tell how well we're doing.

---

## 2. What We Measure and Why

We define five metrics. Each one catches a different kind of mistake.

### Recall
> "Of all the things that *should* have been found, how many did we actually find?"

If a note mentions five medications and the AI finds four of them, recall is 4 out of 5, or 80%.
A low recall score means the AI is missing information — a risk for a health-records tool because
a medication or condition that never gets recorded might be overlooked later.

### Precision
> "Of everything the AI *did* find, how many were actually correct?"

If the AI pulls out six items but two of them are wrong, precision is 4 out of 6, or about 67%.
Low precision means the AI is inventing or mis-reading things — also dangerous in a health record.

### Negation Accuracy
> "When the document says the patient does NOT have something, did the AI correctly avoid recording
> it?"

**Worked example:** A phone note reads: *"never had diabetes."* The word "diabetes" appears in the
document, but the patient is explicitly saying they do not have it. A correct AI should skip this
entirely — no diabetes entry should appear in the patient's record. Negation accuracy measures how
often the AI gets this right. A low score here would mean the app is filling someone's record with
conditions they explicitly said they don't have, which is a serious error.

### Attribution Accuracy
> "When a condition belongs to someone *else* — a family member, a doctor speaking generally, or
> another patient — did the AI keep it off the patient's personal record?"

**Worked example:** A visit transcript contains the line: *"Patient reports that his father was
diagnosed with colon cancer at age 60."* This should be stored as **family history** (a note that
a blood relative had colon cancer), not as the patient's own cancer diagnosis. If the AI records
it as the patient's cancer, that is a serious factual error. Attribution accuracy measures how
often the AI correctly routes these statements — either to family history or ignores them entirely
when they belong to someone else (such as a clinician making a general remark).

### False Extractions
> "Things the AI wrongly recorded — the most dangerous kind of mistake."

False extractions are a subset of low precision. We call them out separately because in a health
record, a wrongly added item (especially a condition or medication) is more harmful than a missed
one. Our test suite maintains a list of "trap" items — things that should never appear in the
patient's record — and we check explicitly that none of them slipped through.

---

## 3. The Synthetic Fixtures and Ground-Truth Files

To measure the above, we need documents with known correct answers.

We wrote two **synthetic fixtures** — realistic but entirely made-up documents with no real
patient data:

1. **`transcript_visit.txt`** — a fake visit transcript between a clinician and a patient. It
   contains deliberate traps: a family member's condition, a conversational negation, a medication
   mentioned without a dose, and a relative date ("since about last week").
2. **`phone_note.txt`** — a terse note in the style of an iPhone reminder, with abbreviations
   (HTN for hypertension, DM2 for Type 2 diabetes) and no sentence structure.

Each fixture is paired with a **ground-truth file** (ending in `.expected.json`). Think of this
as an answer key. It lists:

- **`expected`** — every item the AI should find and record.
- **`must_not_extract`** — every trap item the AI must never record as the patient's own
  information (the father's colon cancer, the doctor's general remark, the negated condition).
- **`expected_family_history`** — items that should be recorded, but specifically as family
  history rather than the patient's own condition.

The **scorer** — a small program we built — compares the AI's output against this answer key and
computes all five metrics automatically.

---

## 4. How to Read a Baseline Report

After running the scorer against the two synthetic fixtures with real AI output, we record the
results in:

> `docs/superpowers/specs/2026-05-30-extraction-quality-baseline.md`

That document lists the measured numbers for each metric (overall and broken down by record type
such as medications, conditions, labs). Here is how to interpret them:

- **Higher is better** for precision, recall, F1 (a combined score), negation accuracy, and
  attribution accuracy. A score of 1.0 means perfect; 0.0 means complete failure.
- **Zero is the goal** for false extractions. Any number above zero means the AI wrongly added
  something to a patient's record.
- **The gaps listed in that document** — wherever scores are below acceptable thresholds — are
  exactly what the next phase of work will fix. The baseline is not a grade; it is a starting
  point and a prioritized to-do list.

---

## 5. Why This Matters

This measurement system lets us **prove** that a change to the AI actually improves accuracy,
rather than guessing. Before this harness existed, we could tune the AI and have no reliable way
to know whether records got more accurate or less.

For a health-records tool, the stakes are real: silently missing a medication, or silently adding
a condition someone does not have, are exactly the kinds of errors we are guarding against.
This eval harness makes those errors visible and measurable so we can fix them with confidence.

---

*MedTimeline organizes and displays your health records. It does not provide medical advice,
diagnoses, or treatment recommendations.*
