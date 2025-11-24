# Prediction Differences Analysis: GPT5_noseed vs GPT5

## Summary

Comparison of two prediction runs (`agent_predictions_GPT5_noseed.xlsx` vs `agent_predictions_GPT5.xlsx`) revealed **2 patients with different predictions**, both resulting in incorrect predictions in Run A and correct predictions in Run B.

## Patients with Different Predictions

### Patient 1185, Day 7
- **Run A**: Predicted "No" (incorrect) - Actual survival: Yes
- **Run B**: Predicted "Yes" (correct) - Actual survival: Yes
- **Difference**: Hepatologist decision changed from "No" to "Yes"
- **Individual Agent Decisions**:
  - Run A: Hepatologist=No, Critical Care=Yes, Transplant Surgeon=No → Final=No
  - Run B: Hepatologist=Yes, Critical Care=Yes, Transplant Surgeon=No → Final=Yes

### Patient 1231, Day 2
- **Run A**: Predicted "No" (incorrect) - Actual survival: Yes
- **Run B**: Predicted "Yes" (correct) - Actual survival: Yes
- **Difference**: Both Hepatologist and Transplant Surgeon decisions changed
- **Individual Agent Decisions**:
  - Run A: Hepatologist=No, Critical Care=Yes, Transplant Surgeon=No → Final=No
  - Run B: Hepatologist=Yes, Critical Care=Yes, Transplant Surgeon=Yes → Final=Yes

## Root Cause Analysis

### 1. Code Differences Between bb3dcfc and Current HEAD

**Key Changes:**
- **create_vignettes.py**: Backward filling of missing values is commented out (line 787)
- **multi_agent_system.py**: 
  - Added unified `call_llm()` function supporting both OpenAI and Anthropic APIs
  - Added `seed=42` parameter for OpenAI JSON mode calls (line 269)
  - Enhanced error handling and JSON parsing
  - Improved prompt formatting with explicit field name instructions

**Note**: User confirmed both runs are NOT seeded. The seed parameter (`seed=42`) exists in the current code (line 269) but was not used in either run, explaining the non-deterministic behavior.

### 2. Input Vignettes Are Identical (Verified)

**Verification Method**: Extracted and compared `clinical_vignettes.xlsx` from commit `3540e9c` (Run B) with the current version (Run A).

**Results**:
- Both files have identical shape: (12,936 rows, 99 columns)
- **All 12,936 rows are identical** across all vignette columns:
  - `hepatologist_vignette`: ALL IDENTICAL
  - `critical_care_physician_vignette`: ALL IDENTICAL
  - `transplant_surgeon_vignette`: ALL IDENTICAL
  - `patient_day_vignette`: ALL IDENTICAL

**Specific Patients Verified**:
- **Patient 1185, Day 7**: All three agent vignettes are identical (Hepatologist: 4,668 chars, Critical Care: 4,223 chars, Transplant Surgeon: 4,042 chars)
- **Patient 1231, Day 2**: All three agent vignettes are identical (Hepatologist: 1,597 chars, Critical Care: 1,559 chars, Transplant Surgeon: 1,711 chars)

**Conclusion**: The clinical vignettes used in both runs are **completely identical**, eliminating input differences as a cause of the prediction differences.

### 3. Non-Deterministic LLM Behavior

The differences are due to **non-deterministic LLM behavior** when seed is not used. The same clinical vignettes produced different interpretations and decisions:

**Patient 1185, Day 7 - Hepatologist Reasoning:**
- **Run A**: Focused on "persistently critical hyperbilirubinemia (28.3 mg/dL)" and "severe excretory dysfunction" → Decision: No
- **Run B**: Focused on "synthetic function is relatively preserved: INR is low at 1.51" and "favorable prognostic sign" → Decision: Yes

**Patient 1231, Day 2 - Hepatologist Reasoning:**
- **Run A**: Emphasized "severe acute kidney injury (creatinine 7.5 mg/dL)" and "high short-term mortality" → Decision: No
- **Run B**: Emphasized "early improvement: ALT decreased by ~19%, INR improved from 2.0 to 1.5" and "recovering synthetic function" → Decision: Yes

**Patient 1231, Day 2 - Transplant Surgeon Reasoning:**
- **Run A**: Focused on "severe renal dysfunction (Cr 7.5 mg/dL)" and "high short-term mortality" → Decision: No
- **Run B**: Focused on "hepatic synthetic function appears to be recovering" and "other organ systems are stable" → Decision: Yes

## Key Findings

1. **Same Inputs, Different Outputs (Verified)**: 
   - Extracted and compared `clinical_vignettes.xlsx` from commit `3540e9c` (Run B) with current version (Run A)
   - **All 12,936 rows are identical** across all vignette columns
   - Identical clinical vignettes produced different agent decisions due to non-deterministic LLM behavior
   - This confirms the differences are **purely due to LLM non-determinism**, not input differences

2. **Interpretation Differences**: The LLM agents interpreted the same clinical data differently:
   - Run A tended to focus on negative prognostic factors (high bilirubin, renal dysfunction)
   - Run B tended to focus on positive trends (improving INR, recovering synthetic function)

3. **Impact on Final Prediction**: The weighted voting system (Critical Care=40%, Surgeon=30%, Hepatologist=30%) amplified individual agent differences, leading to different final predictions.

4. **Both Runs Not Seeded**: Without seed parameter, GPT-5 produces non-deterministic outputs, explaining the variability.

## Recommendations

1. **Use Seed for Reproducibility**: Enable `seed=42` parameter for deterministic outputs when reproducibility is required.

2. **Multiple Runs for Critical Cases**: For important predictions, consider running multiple times and using consensus or confidence-weighted aggregation.

3. **Enhanced Prompting**: Consider adding explicit instructions to consider both positive and negative factors, or use chain-of-thought prompting to make reasoning more consistent.

4. **Testing Specific Patients**: Use the new `--patient_id` argument to test specific patients:
   ```bash
   uv run python multi_agent_system.py --patient_id 1185 1231 --day 7
   ```

## Implementation Changes

Added `--patient_id` argument to `multi_agent_system.py` to enable testing specific patients:
- Usage: `--patient_id 1185 1231` (can specify multiple IDs)
- Works in combination with `--day` argument
- Example: `uv run python multi_agent_system.py --patient_id 1185 --day 7`

