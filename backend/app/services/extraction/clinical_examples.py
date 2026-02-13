from __future__ import annotations

import langextract as lx

CLINICAL_EXTRACTION_PROMPT = """Extract clinical entities from medical text in order of appearance.
Entity types: medication, dosage, route, frequency, condition, lab_result, vital, procedure, allergy, provider, duration.

Use exact text from the input. Do not paraphrase.
Use attributes to group related entities (e.g. medication_group for drug details).
For lab results, include value, unit, and reference range as attributes when available.
For conditions, include status (active, resolved, historical) as an attribute."""

CLINICAL_EXAMPLES = [
    lx.data.ExampleData(
        text="Patient was given 250 mg IV Cefazolin TID for one week. History of hypertension, controlled. BP 120/80 mmHg. Dr. Smith, Cardiology.",
        extractions=[
            lx.data.Extraction(
                extraction_class="dosage",
                extraction_text="250 mg",
                attributes={"medication_group": "Cefazolin", "value": "250", "unit": "mg"},
            ),
            lx.data.Extraction(
                extraction_class="route",
                extraction_text="IV",
                attributes={"medication_group": "Cefazolin", "full_name": "intravenous"},
            ),
            lx.data.Extraction(
                extraction_class="medication",
                extraction_text="Cefazolin",
                attributes={"medication_group": "Cefazolin", "drug_class": "antibiotic"},
            ),
            lx.data.Extraction(
                extraction_class="frequency",
                extraction_text="TID",
                attributes={"medication_group": "Cefazolin", "meaning": "three times daily"},
            ),
            lx.data.Extraction(
                extraction_class="duration",
                extraction_text="for one week",
                attributes={"medication_group": "Cefazolin", "days": "7"},
            ),
            lx.data.Extraction(
                extraction_class="condition",
                extraction_text="hypertension",
                attributes={"status": "active", "controlled": "true"},
            ),
            lx.data.Extraction(
                extraction_class="vital",
                extraction_text="BP 120/80 mmHg",
                attributes={"type": "blood_pressure", "systolic": "120", "diastolic": "80", "unit": "mmHg"},
            ),
            lx.data.Extraction(
                extraction_class="provider",
                extraction_text="Dr. Smith",
                attributes={"specialty": "Cardiology", "role": "attending"},
            ),
        ],
    ),
    lx.data.ExampleData(
        text="HbA1c 6.8% (ref 4.0-5.6). Metformin 500mg PO BID for type 2 diabetes. Allergic to Penicillin (rash). Colonoscopy performed 01/2024.",
        extractions=[
            lx.data.Extraction(
                extraction_class="lab_result",
                extraction_text="HbA1c 6.8%",
                attributes={"test": "HbA1c", "value": "6.8", "unit": "%", "ref_low": "4.0", "ref_high": "5.6", "interpretation": "high"},
            ),
            lx.data.Extraction(
                extraction_class="medication",
                extraction_text="Metformin",
                attributes={"medication_group": "Metformin"},
            ),
            lx.data.Extraction(
                extraction_class="dosage",
                extraction_text="500mg",
                attributes={"medication_group": "Metformin", "value": "500", "unit": "mg"},
            ),
            lx.data.Extraction(
                extraction_class="route",
                extraction_text="PO",
                attributes={"medication_group": "Metformin", "full_name": "oral"},
            ),
            lx.data.Extraction(
                extraction_class="frequency",
                extraction_text="BID",
                attributes={"medication_group": "Metformin", "meaning": "twice daily"},
            ),
            lx.data.Extraction(
                extraction_class="condition",
                extraction_text="type 2 diabetes",
                attributes={"status": "active"},
            ),
            lx.data.Extraction(
                extraction_class="allergy",
                extraction_text="Penicillin",
                attributes={"reaction": "rash", "severity": "mild"},
            ),
            lx.data.Extraction(
                extraction_class="procedure",
                extraction_text="Colonoscopy",
                attributes={"date": "01/2024"},
            ),
        ],
    ),
]
