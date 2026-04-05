from __future__ import annotations

import langextract as lx

CLINICAL_EXTRACTION_PROMPT = """\
Extract clinical entities from the following medical text. Entity types:

STORABLE ENTITIES (create health records):
- medication: Drug names. Group related dosage/route/frequency via medication_group attribute. Include: name, dose, unit, route, frequency, indication.
- condition: Patient diagnoses. Include status attribute: active, resolved, historical, negated.
- lab_result: Laboratory test results. Include: test, value, unit, ref_low, ref_high, interpretation.
- vital: Vital signs (BP, HR, Temp, SpO2, Weight, Height, BMI). Include: type, value, unit.
- procedure: Medical procedures performed ON THIS PATIENT. Include: date, status.
- allergy: Drug/food/substance allergies. Include: reaction, severity.
- encounter: A clinical visit or encounter. Extract ONLY the PRIMARY visit (the visit this document is about). Include: visit_type (office, telehealth, emergency, inpatient), date, cpt_code, reason.
- imaging_result: Diagnostic test/imaging results (EGD, MRI, CT, ultrasound, X-ray, breath test, gastric emptying, SBFT, colonoscopy, etc). Include: procedure_name, date, findings, interpretation, category (imaging, endoscopy, nuclear_medicine, pulmonary, laboratory_panel).
- family_history: Health conditions of family members. Include: relationship (mother, father, grandmother, grandfather, sibling, etc.), condition, status, notes.
- social_history: Social/lifestyle factors. Include: category (diet, alcohol, tobacco, exercise, birth_history, occupation), value, date.
- assessment_plan: The Assessment & Plan section as a whole. Extract as a SINGLE entity with the full A&P text. Include: plan_items (array of numbered plan item summaries).

ATTRIBUTE ENTITIES (support storable entities, do NOT create records):
- dosage: Dose amounts (group via medication_group)
- route: Administration route (IV, PO, IM, topical, etc.)
- frequency: Dosing schedule (BID, TID, QID, daily, weekly, etc.)
- duration: Treatment duration
- date: Associated dates

RULES:
1. Use EXACT text from the document. Do NOT paraphrase or infer.
2. Group medication + dosage + route + frequency using matching medication_group attribute values.
3. NEGATION: "No X", "denies X", "ruled out X" → skip OR set status="negated". Do NOT extract as active conditions.
4. EDUCATIONAL TEXT: Skip conditions in "can cause", "may develop", "risk of" phrasing.
5. FAMILY HISTORY: Conditions attributed to family members ("Father has X", "Mom: X") → extract as family_history entity, NOT as condition.
6. Extract the date attribute for ALL entity types when a date is available in the text (format as found).
7. ENCOUNTER: Extract only ONE encounter per document — the primary visit. Do NOT create encounters for historical visit references.
8. IMAGING RESULTS: Extract the FINDINGS and INTERPRETATION, not just the procedure name. Include the date of the study.
9. ASSESSMENT & PLAN: Extract as a single entity containing the full A&P narrative. Summarize each numbered plan item in the plan_items array.
10. Confidence scoring: High (>0.8) for exact matches with clear context, Medium (0.5-0.8) for context-dependent extractions, Low (<0.5) for ambiguous mentions.
"""

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
                attributes={"medication_group": "Cefazolin", "drug_class": "antibiotic", "confidence": "0.95"},
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
                attributes={"status": "active", "controlled": "true", "confidence": "0.90"},
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
                attributes={"test": "HbA1c", "value": "6.8", "unit": "%", "ref_low": "4.0", "ref_high": "5.6", "interpretation": "high", "confidence": "0.95"},
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
    lx.data.ExampleData(
        text="No chest pain. Denies shortness of breath. History of diabetes, controlled. Family history of heart disease (father).",
        extractions=[
            # chest pain: SKIPPED (negated)
            # shortness of breath: SKIPPED (negated)
            lx.data.Extraction(
                extraction_class="condition",
                extraction_text="diabetes",
                attributes={"status": "active", "controlled": "true", "date": ""},
            ),
            # heart disease: SKIPPED (family history, not patient's)
        ],
    ),
    lx.data.ExampleData(
        text=(
            "GI Follow-Up Visit - Telehealth\n"
            "Date: 03/15/2025\n"
            "Reason: Follow-up gastroparesis and GERD management\n\n"
            "Medications:\n"
            "Omeprazole 40mg PO daily\n"
            "Metoclopramide 10mg PO QID before meals\n\n"
            "Active Problems:\n"
            "1. Gastroparesis (K31.84)\n"
            "2. Gastroesophageal reflux disease (K21.0)\n\n"
            "Labs (03/10/2025):\n"
            "CBC: WBC 6.2 (4.0-11.0), Hgb 13.5 (12.0-16.0), Plt 245 (150-400)\n"
            "CMP: Glucose 98 (70-100), Creatinine 0.9 (0.6-1.2)\n\n"
            "Imaging/Diagnostic Studies:\n"
            "EGD (02/20/2025): Mild erythema in gastric antrum, no ulceration. "
            "Biopsy negative for H. pylori. Impression: mild chronic gastritis.\n"
            "CT Abdomen (01/15/2025): No bowel obstruction. Mild hepatic steatosis.\n"
            "Gastric emptying study (12/10/2024): 45% retention at 4 hours (normal <10%). "
            "Findings consistent with moderate gastroparesis.\n"
            "PFT (11/05/2024): FEV1 92% predicted, FVC 95% predicted. "
            "Interpretation: normal spirometry.\n\n"
            "Family History:\n"
            "Mother: Type 2 diabetes, diagnosed age 55\n"
            "Father: Colon cancer, deceased age 68\n"
            "Maternal grandmother: Celiac disease\n\n"
            "Social History:\n"
            "Diet: Low-fat, small frequent meals\n"
            "Alcohol: Occasional, 1-2 drinks per week\n"
            "Birth history: G2P2, no complications\n\n"
            "Assessment & Plan:\n"
            "1. Gastroparesis - symptoms improving on metoclopramide. Continue current regimen. "
            "Repeat gastric emptying in 6 months.\n"
            "2. GERD - well controlled on omeprazole 40mg daily. Continue.\n"
            "3. Mild chronic gastritis - H. pylori negative. Monitor.\n"
            "4. Hepatic steatosis - incidental finding on CT. Recommend dietary counseling.\n"
            "5. Preventive care - due for colonoscopy given family history of colon cancer."
        ),
        extractions=[
            # Encounter - primary visit
            lx.data.Extraction(
                extraction_class="encounter",
                extraction_text="GI Follow-Up Visit - Telehealth",
                attributes={
                    "visit_type": "telehealth",
                    "date": "03/15/2025",
                    "reason": "Follow-up gastroparesis and GERD management",
                    "confidence": "0.95",
                },
            ),
            # Medications with grouping
            lx.data.Extraction(
                extraction_class="medication",
                extraction_text="Omeprazole",
                attributes={"medication_group": "Omeprazole", "confidence": "0.95"},
            ),
            lx.data.Extraction(
                extraction_class="dosage",
                extraction_text="40mg",
                attributes={"medication_group": "Omeprazole", "value": "40", "unit": "mg"},
            ),
            lx.data.Extraction(
                extraction_class="route",
                extraction_text="PO",
                attributes={"medication_group": "Omeprazole", "full_name": "oral"},
            ),
            lx.data.Extraction(
                extraction_class="frequency",
                extraction_text="daily",
                attributes={"medication_group": "Omeprazole", "meaning": "once daily"},
            ),
            lx.data.Extraction(
                extraction_class="medication",
                extraction_text="Metoclopramide",
                attributes={"medication_group": "Metoclopramide", "confidence": "0.95"},
            ),
            lx.data.Extraction(
                extraction_class="dosage",
                extraction_text="10mg",
                attributes={"medication_group": "Metoclopramide", "value": "10", "unit": "mg"},
            ),
            lx.data.Extraction(
                extraction_class="route",
                extraction_text="PO",
                attributes={"medication_group": "Metoclopramide", "full_name": "oral"},
            ),
            lx.data.Extraction(
                extraction_class="frequency",
                extraction_text="QID before meals",
                attributes={"medication_group": "Metoclopramide", "meaning": "four times daily before meals"},
            ),
            # Conditions
            lx.data.Extraction(
                extraction_class="condition",
                extraction_text="Gastroparesis (K31.84)",
                attributes={"status": "active", "icd10": "K31.84", "confidence": "0.95"},
            ),
            lx.data.Extraction(
                extraction_class="condition",
                extraction_text="Gastroesophageal reflux disease (K21.0)",
                attributes={"status": "active", "icd10": "K21.0", "confidence": "0.95"},
            ),
            # Lab results
            lx.data.Extraction(
                extraction_class="lab_result",
                extraction_text="WBC 6.2",
                attributes={
                    "test": "WBC", "value": "6.2", "unit": "10^3/uL",
                    "ref_low": "4.0", "ref_high": "11.0",
                    "interpretation": "normal", "date": "03/10/2025", "confidence": "0.95",
                },
            ),
            lx.data.Extraction(
                extraction_class="lab_result",
                extraction_text="Hgb 13.5",
                attributes={
                    "test": "Hgb", "value": "13.5", "unit": "g/dL",
                    "ref_low": "12.0", "ref_high": "16.0",
                    "interpretation": "normal", "date": "03/10/2025", "confidence": "0.95",
                },
            ),
            lx.data.Extraction(
                extraction_class="lab_result",
                extraction_text="Plt 245",
                attributes={
                    "test": "Plt", "value": "245", "unit": "10^3/uL",
                    "ref_low": "150", "ref_high": "400",
                    "interpretation": "normal", "date": "03/10/2025", "confidence": "0.95",
                },
            ),
            lx.data.Extraction(
                extraction_class="lab_result",
                extraction_text="Glucose 98",
                attributes={
                    "test": "Glucose", "value": "98", "unit": "mg/dL",
                    "ref_low": "70", "ref_high": "100",
                    "interpretation": "normal", "date": "03/10/2025", "confidence": "0.95",
                },
            ),
            lx.data.Extraction(
                extraction_class="lab_result",
                extraction_text="Creatinine 0.9",
                attributes={
                    "test": "Creatinine", "value": "0.9", "unit": "mg/dL",
                    "ref_low": "0.6", "ref_high": "1.2",
                    "interpretation": "normal", "date": "03/10/2025", "confidence": "0.95",
                },
            ),
            # Family history
            lx.data.Extraction(
                extraction_class="family_history",
                extraction_text="Mother: Type 2 diabetes, diagnosed age 55",
                attributes={
                    "relationship": "mother", "condition": "Type 2 diabetes",
                    "notes": "diagnosed age 55", "confidence": "0.90",
                },
            ),
            lx.data.Extraction(
                extraction_class="family_history",
                extraction_text="Father: Colon cancer, deceased age 68",
                attributes={
                    "relationship": "father", "condition": "Colon cancer",
                    "status": "deceased", "notes": "deceased age 68", "confidence": "0.90",
                },
            ),
            lx.data.Extraction(
                extraction_class="family_history",
                extraction_text="Maternal grandmother: Celiac disease",
                attributes={
                    "relationship": "maternal grandmother", "condition": "Celiac disease",
                    "confidence": "0.85",
                },
            ),
            # Imaging results
            lx.data.Extraction(
                extraction_class="imaging_result",
                extraction_text="EGD (02/20/2025): Mild erythema in gastric antrum, no ulceration. Biopsy negative for H. pylori. Impression: mild chronic gastritis.",
                attributes={
                    "procedure_name": "EGD",
                    "date": "02/20/2025",
                    "findings": "Mild erythema in gastric antrum, no ulceration. Biopsy negative for H. pylori.",
                    "interpretation": "mild chronic gastritis",
                    "category": "endoscopy",
                    "confidence": "0.95",
                },
            ),
            lx.data.Extraction(
                extraction_class="imaging_result",
                extraction_text="CT Abdomen (01/15/2025): No bowel obstruction. Mild hepatic steatosis.",
                attributes={
                    "procedure_name": "CT Abdomen",
                    "date": "01/15/2025",
                    "findings": "No bowel obstruction. Mild hepatic steatosis.",
                    "interpretation": "Mild hepatic steatosis, no obstruction",
                    "category": "imaging",
                    "confidence": "0.95",
                },
            ),
            lx.data.Extraction(
                extraction_class="imaging_result",
                extraction_text="Gastric emptying study (12/10/2024): 45% retention at 4 hours (normal <10%). Findings consistent with moderate gastroparesis.",
                attributes={
                    "procedure_name": "Gastric emptying study",
                    "date": "12/10/2024",
                    "findings": "45% retention at 4 hours (normal <10%)",
                    "interpretation": "moderate gastroparesis",
                    "category": "nuclear_medicine",
                    "confidence": "0.95",
                },
            ),
            lx.data.Extraction(
                extraction_class="imaging_result",
                extraction_text="PFT (11/05/2024): FEV1 92% predicted, FVC 95% predicted. Interpretation: normal spirometry.",
                attributes={
                    "procedure_name": "PFT",
                    "date": "11/05/2024",
                    "findings": "FEV1 92% predicted, FVC 95% predicted",
                    "interpretation": "normal spirometry",
                    "category": "pulmonary",
                    "confidence": "0.90",
                },
            ),
            # Social history
            lx.data.Extraction(
                extraction_class="social_history",
                extraction_text="Low-fat, small frequent meals",
                attributes={
                    "category": "diet", "value": "Low-fat, small frequent meals",
                    "confidence": "0.85",
                },
            ),
            lx.data.Extraction(
                extraction_class="social_history",
                extraction_text="Occasional, 1-2 drinks per week",
                attributes={
                    "category": "alcohol", "value": "Occasional, 1-2 drinks per week",
                    "confidence": "0.85",
                },
            ),
            lx.data.Extraction(
                extraction_class="social_history",
                extraction_text="G2P2, no complications",
                attributes={
                    "category": "birth_history", "value": "G2P2, no complications",
                    "confidence": "0.85",
                },
            ),
            # Assessment & Plan - single entity
            lx.data.Extraction(
                extraction_class="assessment_plan",
                extraction_text=(
                    "1. Gastroparesis - symptoms improving on metoclopramide. Continue current regimen. "
                    "Repeat gastric emptying in 6 months.\n"
                    "2. GERD - well controlled on omeprazole 40mg daily. Continue.\n"
                    "3. Mild chronic gastritis - H. pylori negative. Monitor.\n"
                    "4. Hepatic steatosis - incidental finding on CT. Recommend dietary counseling.\n"
                    "5. Preventive care - due for colonoscopy given family history of colon cancer."
                ),
                attributes={
                    "plan_items": "[\"Gastroparesis - continue metoclopramide, repeat gastric emptying in 6 months\", \"GERD - continue omeprazole 40mg daily\", \"Mild chronic gastritis - H. pylori negative, monitor\", \"Hepatic steatosis - dietary counseling recommended\", \"Preventive care - colonoscopy due for family history of colon cancer\"]",
                    "confidence": "0.90",
                },
            ),
        ],
    ),
]
