# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.32] - 2025-11-23 16:38:48

### Changed

- **Improved Day Filtering Logic with Per-Patient Bounds**
  - Updated day filtering to handle edge cases per patient
  - If specified day < 1, automatically uses day 1 for each patient
  - If specified day > maximum day for a patient, uses that patient's maximum day
  - Day filtering now applies bounds per patient (not globally)
  - Formula: target_day = max(1, min(specified_day, patient_max_day))
  - Ensures all patients get a valid day within their available range

## [0.5.31] - 2025-11-23 16:36:46

### Changed

- **Enhanced Multi-Agent System Command-Line Interface**
  - Added `--num_patient` argument to specify number of patients to process (default: all patients)
  - Added `--day` argument to specify specific day to process (default: maximum day for each patient)
  - When `--day` is not specified, system automatically filters to maximum day for each patient
  - Results are always saved to `agent_predictions.xlsx` Excel file
  - Improved logging to show filtering steps and final result count
  - Added validation to handle empty results after filtering

## [0.5.30] - 2025-11-23 16:24:20

### Changed

- **Differentiated Extreme Trend Ranges**
  - Updated `calculate_trend_detailed()` function in `create_vignettes.py` to use distinct labels for extreme ranges
  - Changed `< -100%` range from "Rapidly Decreasing" to "Extremely Decreasing" to differentiate from `-100% to -50%` range
  - Changed `> +100%` range from "Rapidly Increasing" to "Extremely Increasing" to differentiate from `+50% to +100%` range
  - Updated `create_time_trend_label_sheet()` in `create_label_legend.py` to match the new differentiated labels
  - Each percent change range now has a unique label, providing better granularity for extreme changes
  - Maintains consistent descriptive labeling (direction only, not evaluative)

## [0.5.29] - 2025-11-23 16:18:41

### Changed

- **Filter Empty Rows from Vignettes**
  - Added filtering logic in `create_vignettes()` function to remove rows where all continuous variables are empty
  - Checks all `_binned`, `_value`, and `_trend` columns for all continuous variables (Lactate, Creat, INR1, Hemoglobin, WBC, Platelet_Cnt, Bilirubin, ALT, NA, HCO3, Phosphate, PH, Arterial_Ammonia, Venous_Ammonia, ammonia, Ratio_PO2_FiO2, Prothrom_Sec, PMN, Lymph)
  - Removes rows where all specified columns are null/NaN, keeping only rows with at least one non-empty continuous variable
  - Filtering occurs after vignette row creation but before comprehensive vignette text generation
  - Logs the number of removed rows for transparency
  - Ensures only meaningful clinical data is included in the final vignette dataset

## [0.5.28] - 2025-11-23 16:17:50

### Changed

- **Fixed Time Trend Label Consistency**
  - Updated `calculate_trend_detailed()` function in `create_vignettes.py` to use consistent descriptive labels
  - Removed evaluative terms ("Improving", "Worsening") that were mixed with descriptive terms ("Decreasing", "Increasing")
  - All negative percent changes now use "Decreasing" labels: "Rapidly Decreasing", "Decreasing", "Mildly Decreasing"
  - All positive percent changes now use "Increasing" labels: "Rapidly Increasing", "Increasing", "Mildly Increasing"
  - Updated `create_time_trend_label_sheet()` in `create_label_legend.py` to match the new consistent labels
  - Labels are now purely descriptive (direction only) rather than evaluative, which is appropriate since clinical interpretation depends on the specific variable
  - Fixed inconsistency where negative changes used "Improving" while positive changes used "Worsening"

## [0.5.27] - 2025-11-23 00:53:00

### Added

- **Agent Variable Mapping Documentation**
  - Created `create_agent_variable_mapping.py` script to generate Excel file with agent to variable mapping
  - Output file: `agent_variable_mapping.xlsx` with 3 rows (one per agent) and 2 columns (Agent, Assigned Variables)
  - Combines continuous and categorical variables for each agent into comma-separated list
  - Uses same `AGENT_VARIABLES` mapping from `create_vignettes.py` for consistency
  - Variables sorted alphabetically for clean presentation
  - Provides clear reference documentation for agent variable assignments

## [0.5.26] - 2025-11-17 13:00:00

### Changed

- **Simplified Trend Descriptions to Remove Binning Labels**
  - Updated `calculate_trend_detailed()` function in `create_vignettes.py`
  - Removed binning label information from trend descriptions
  - Trend descriptions now only include: trend direction, values, absolute change, and percentage change
  - Format: "trend (from valueA unit to valueB unit with change ±X.XX unit with percentage change ±X.XX%)"
  - Example: "Rapidly Increasing (from 3.11 mg/dL to 5.05 mg/dL with change +1.94 mg/dL with percentage change +62.38%)"
  - Removed bin transition information (e.g., "from lower risk... to high risk...") to simplify trend descriptions
  - Applies to all trend history entries in comprehensive and agent-specific vignettes
  - Binning labels remain available in laboratory values section, only removed from trend descriptions

## [0.5.25] - 2025-11-17 12:30:00

### Changed

- **Enhanced Clinical Vignettes to Include Both Value and Label**
  - Updated `create_comprehensive_vignette()` and `create_agent_vignette()` functions in `create_vignettes.py`
  - Laboratory values now display both the numeric value with unit and the binned label
  - Format: "Variable name is value unit (binned label)" (e.g., "Lactate is 2.5 mmol/L (Intermediate Risk (Requires Trend Monitoring))")
  - If unit is not available, format: "Variable name is value (binned label)"
  - **All continuous values are rounded to 2 decimal places at storage time** (when stored in vignette dictionary) and at display time for consistent formatting throughout
  - Binning calculations use original precision for accuracy, then values are rounded for storage and display
  - Falls back to label-only format if value is missing
  - Applies to both comprehensive vignettes and agent-specific vignettes
  - Provides complete clinical context with both quantitative and qualitative information

- **Enhanced Trend Information to Include Values and Rate of Change**
  - Updated `calculate_trend_detailed()` function in `create_vignettes.py`
  - Trend descriptions now include actual values, absolute change, and percentage change
  - Format: "trend (from valueA unit to valueB unit with change ±X.XX unit with percentage change ±X.XX%, from previous_bin to current_bin)"
  - Example: "Worsening (from 2.0 mmol/L to 3.5 mmol/L with change +1.50 mmol/L with percentage change +75.00%, from Intermediate Risk (Requires Trend Monitoring) to Urgent Transplant Candidate (High Risk) (Post-Fluid Resuscitation))"
  - All values in trend descriptions are rounded to 2 decimal places for consistent formatting
  - If unit is not available, format excludes unit from values and change
  - Includes both quantitative change metrics and qualitative bin transitions
  - Applies to all trend history entries in comprehensive and agent-specific vignettes

## [0.5.24] - 2025-11-17 12:00:00

### Added

- **NextStep Sheet in Label Legend Documentation**
  - Added new "NextStep" sheet to `vignette_label_legend.xlsx` in `create_label_legend.py`
  - Documents next steps and notes for data processing and evaluation
  - Contains 8 entries covering:
    - Value Only, Label Only (with note: "Sensitive for labelling"), Value + Label Only
    - Agent pick it up correctly at which day?
    - Evaluation at each day
    - Need to put references for only labelling
    - Need to add data from previous days not just the trend
    - in Day i, if Day i-1 does not have data, use trend from day i-2, i-3,.., (the last available)
  - Created `create_next_step_sheet()` function to generate the sheet
  - Sheet includes "Next Step" and "Notes" columns

## [0.5.23] - 2025-11-17 11:30:00

### Changed

- **Updated Lymph (Lymphocytes) Binning Thresholds**
  - Revised lymphocyte percentage binning to use neutrophil-lymphocyte ratio prognostic thresholds for acetaminophen overdose based on [Craig et al. (2014)](https://pubmed.ncbi.nlm.nih.gov/25045842/)
  - < 5.6%: "High Risk / Severe Lymphopenia" (exclusive threshold)
  - 5.6% – 17.8%: "Intermediate Risk / Warning" (inclusive range)
  - > 17.8%: "Low Risk / Normal" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 5.6, 17.8, inf]
  - Added special binning logic in `bin_continuous_value()` to handle Lymph with proper inclusive/exclusive boundaries
  - Added reference field to `BINNING_THRESHOLDS` for Lymph
  - Updated range formatting in `create_label_legend.py` to display proper ranges (e.g., "< 5.6", "5.6 – 17.8", "> 17.8") for Lymph with decimal precision

## [0.5.22] - 2025-11-17 11:00:00

### Changed

- **Updated PMN (Polymorphonuclear Neutrophils) Binning Thresholds**
  - Revised PMN percentage binning to use blood differential test normal ranges based on [UCSF Health - Blood Differential Test](https://www.ucsfhealth.org/medical-tests/blood-differential-test)
  - < 40%: "Neutropenia / Immune Paralysis" (exclusive threshold)
  - 40% – 80%: "Normal Physiologic Range" (inclusive range)
  - > 80%: "Hyper-inflammatory / SIRS" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 40, 80, inf]
  - Added special binning logic in `bin_continuous_value()` to handle PMN with proper inclusive/exclusive boundaries
  - Added reference field to `BINNING_THRESHOLDS` for PMN
  - Updated range formatting in `create_label_legend.py` to display proper ranges (e.g., "< 40", "40 – 80", "> 80") for PMN

## [0.5.21] - 2025-11-17 10:30:00

### Changed

- **Updated Prothrom_Sec (Prothrombin Time) Binning Thresholds**
  - Revised prothrombin time binning to use King's College Criteria threshold for poor prognosis in acetaminophen toxicity based on [O'Grady et al. (1989)](https://pubmed.ncbi.nlm.nih.gov/2490426/)
  - < 13.5 seconds: "Normal / Low Risk (Physiological baseline)" (exclusive threshold)
  - 13.5 – 100 seconds: "Abnormal / Monitor Trajectory (Indicates coagulopathy and liver injury requiring dynamic trend analysis)" (inclusive range)
  - ≥ 100 seconds: "Critical / Transplant Consideration (Meets King's College Criteria threshold for poor prognosis in acetaminophen toxicity)" (inclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 13.5, 100, inf]
  - Added special binning logic in `bin_continuous_value()` to handle Prothrom_Sec with proper inclusive/exclusive boundaries
  - Added reference field to `BINNING_THRESHOLDS` for Prothrom_Sec
  - Updated range formatting in `create_label_legend.py` to display proper ranges (e.g., "< 13.5", "13.5 – 100", "≥ 100") for Prothrom_Sec

## [0.5.20] - 2025-11-17 10:00:00

### Changed

- **Updated Ratio_PO2_FiO2 (PaO₂/FiO₂ Ratio) Binning Thresholds**
  - Revised PaO₂/FiO₂ ratio binning to use ARDS classification criteria based on [JAMA Network](https://jamanetwork.com/journals/jama/article-abstract/1160659)
  - ≤ 100 mmHg: "Severe ARDS (Critical instability; high risk of hypoxia-induced cerebral edema)" (inclusive threshold)
  - 100 < x ≤ 200 mmHg: "Moderate ARDS (Significant respiratory compromise; potential contraindication for immediate transport/surgery)" (exclusive lower bound, inclusive upper bound)
  - 200 < x ≤ 300 mmHg: "Mild ARDS (Early sign of deterioration; warning for AI monitoring)" (exclusive lower bound, inclusive upper bound)
  - > 300 mmHg: "No ARDS (Physiologically stable respiratory status)" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 100, 200, 300, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all four ARDS categories with proper inclusive/exclusive boundaries
  - Added reference field to `BINNING_THRESHOLDS` for Ratio_PO2_FiO2
  - Updated range formatting in `create_label_legend.py` to display proper ranges (e.g., "≤ 100", "100 < x ≤ 200", "200 < x ≤ 300", "> 300") for Ratio_PO2_FiO2

## [0.5.19] - 2025-11-17 09:30:00

### Changed

- **Updated ammonia Binning Thresholds**
  - Revised ammonia binning to use intracranial hypertension and cerebral herniation risk thresholds based on [Bernal et al. (2007)](https://pubmed.ncbi.nlm.nih.gov/17685471/)
  - < 100 μmol/L: "Lower Risk of Neurotoxicity"
  - 100 – 200 μmol/L: "High Risk of Intracranial Hypertension (ICH) & Severe Encephalopathy" (inclusive range)
  - > 200 μmol/L: "Critical Risk of Cerebral Herniation" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 100, 200, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all three risk categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for ammonia
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "100 – 200") and "> 200" for ammonia

## [0.5.18] - 2025-11-17 09:00:00

### Changed

- **Updated Venous_Ammonia Binning Thresholds**
  - Revised venous ammonia binning to use hepatic encephalopathy and intracranial hypertension risk thresholds based on [Bernal et al. (2007)](https://pubmed.ncbi.nlm.nih.gov/17685471/)
  - < 100 μmol/L: "Lower Risk (Associated with lower risk of cerebral complications; favors continued medical management and assessment for spontaneous recovery)"
  - 100 – 150 μmol/L: "High Risk (Predictive of severe Hepatic Encephalopathy [Grade III/IV]; indicates deterioration requiring intensive monitoring)" (inclusive range)
  - > 150 μmol/L: "Critical Risk (High probability of intracranial hypertension and cerebral edema; triggers immediate neuroprotective protocols and urgent transplant listing assessment)" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 100, 150, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all three risk categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for Venous_Ammonia
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "100 – 150") and "> 150" for Venous_Ammonia

## [0.5.17] - 2025-11-17 08:30:00

### Changed

- **Updated Arterial_Ammonia Binning Thresholds**
  - Revised arterial ammonia binning to use intracranial hypertension risk thresholds based on [Wiley Online Library - Hepatology](https://onlinelibrary.wiley.com/doi/10.1002/hep.510290309)
  - < 150 μmol/L: "Lower Risk (Intracranial hypertension is infrequent below this threshold, though hepatic encephalopathy may still be present)"
  - 150 – 200 μmol/L: "High Risk (Significant risk of developing intracranial hypertension; indicates need for aggressive monitoring)" (inclusive range)
  - > 200 μmol/L: "Critical Risk (Strongly associated with cerebral herniation; immediate neuroprotective strategies and transplant assessment required)" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 150, 200, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all three risk categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for Arterial_Ammonia
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "150 – 200") and "> 200" for Arterial_Ammonia

## [0.5.16] - 2025-11-17 08:00:00

### Changed

- **Updated PH (pH) Binning Thresholds**
  - Revised pH binning to use King's College Criteria based on [StatPearls - Acetaminophen Toxicity](https://www.ncbi.nlm.nih.gov/books/NBK441917/)
  - < 7.30: "Urgent Transplant Candidate (High likelihood of mortality without liver transplantation; meets the single KCC criterion for listing regardless of encephalopathy grade)"
  - >= 7.30: "Monitor / Assess Other Criteria (Survival is possible with supportive care unless the patient meets the alternative criteria triad: INR > 6.5, Creatinine > 3.4 mg/dL, and Grade III/IV Encephalopathy)" (inclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 7.30, inf]
  - Added special binning logic in `bin_continuous_value()` to handle the 7.30 threshold for PH
  - Added reference field to `BINNING_THRESHOLDS` for PH
  - Updated range formatting in `create_label_legend.py` to display "< 7.30" and ">= 7.30" for PH

## [0.5.15] - 2025-11-17 07:30:00

### Changed

- **Updated Phosphate Binning Thresholds**
  - Revised phosphate binning to use acute liver failure prognostic thresholds based on [Baquerizo et al. (2003)](https://pubmed.ncbi.nlm.nih.gov/12829902/)
  - < 2.5 mg/dL: "High Likelihood of Spontaneous Recovery" (74% recovery rate at 1 week)
  - 2.5 – 5.0 mg/dL: "Indeterminate / Moderate Risk" (45% recovery rate at 1 week) (inclusive range)
  - > 5.0 mg/dL: "High Risk of Mortality / Urgent Transplant Candidate" (0% recovery rate at 1 week) (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 2.5, 5.0, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all three prognostic categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for Phosphate
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "2.5 – 5.0") and "> 5.0" for Phosphate

## [0.5.14] - 2025-11-17 07:00:00

### Changed

- **Updated HCO3 (Bicarbonate) Binning Thresholds**
  - Revised bicarbonate binning to use metabolic acidosis classification based on [StatPearls - Metabolic Acidosis](https://www.ncbi.nlm.nih.gov/books/NBK482146/)
  - < 10 mEq/L: "Severe Metabolic Acidosis"
  - 10 – 22 mEq/L: "Mild to Moderate Metabolic Acidosis" (Indicates physiological deterioration and lactate accumulation) (inclusive range)
  - > 22 mEq/L: "Normal / Compensated" (Indicates physiological stability) (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 10, 22, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all three categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for HCO3
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "10 – 22") and "> 22" for HCO3

## [0.5.13] - 2025-11-17 06:30:00

### Changed

- **Updated NA (Sodium) Binning Thresholds**
  - Revised sodium binning to use neuroprotective thresholds based on [Skytthe et al. (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7432735/)
  - < 135 mEq/L: "Hyponatremia / High Risk" (Significant risk factor for worsening cerebral edema and herniation; requires immediate correction)
  - 135 – 145 mEq/L: "Sub-therapeutic / Monitor" (Normal physiologic range, but potentially insufficient for neuroprotection; consider administration of hypertonic saline if ICP concerns arise) (inclusive range)
  - 145 – 155 mEq/L: "Therapeutic Target / Neuroprotective" (Recommended goal range for patients with high-grade encephalopathy to reduce intracranial pressure and prevent cerebral edema) (inclusive range)
  - >= 155 mEq/L: "Hypernatremia / Monitor" (inclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 135, 145, 155, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all four categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for NA
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "135 – 145", "145 – 155") and ">= 155" for NA

## [0.5.12] - 2025-11-17 06:00:00

### Changed

- **Updated ALT (Alanine Aminotransferase) Binning Thresholds**
  - Revised ALT binning to use LiverTox severity grading system based on [NCBI Bookshelf - LiverTox](https://www.ncbi.nlm.nih.gov/books/NBK548241/)
  - < 120 U/L: "Grade 1 (Mild)"
  - 120 – 200 U/L: "Grade 2 (Moderate)" (inclusive range)
  - 200 – 800 U/L: "Grade 3 (Severe)" (inclusive range)
  - > 800 U/L: "Grade 4 (Life-Threatening / Acute Liver Failure)" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 120, 200, 800, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all four severity grades with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for ALT
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "120 – 200", "200 – 800") and "> 800" for ALT

## [0.5.11] - 2025-11-17 05:30:00

### Changed

- **Updated Bilirubin Binning Thresholds**
  - Revised bilirubin binning to use SOFA score liver function criteria based on [Moreno et al. (2023)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9837980/)
  - < 1.2 mg/dL: "0 (Normal function)"
  - 1.2 – 1.9 mg/dL: "1 (Mild dysfunction)" (inclusive range)
  - 2.0 – 5.9 mg/dL: "2 (Moderate dysfunction)" (inclusive range)
  - 6.0 – 11.9 mg/dL: "3 (Severe dysfunction)" (inclusive range)
  - >= 12.0 mg/dL: "4 (Critical liver failure)" (inclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 1.2, 2.0, 6.0, 12.0, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all five SOFA score categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for Bilirubin
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "1.2 – 1.9", "2.0 – 5.9", "6.0 – 11.9") and ">= 12.0" for Bilirubin

## [0.5.10] - 2025-11-17 05:00:00

### Changed

- **Updated Platelet_Cnt (Platelet Count) Binning Thresholds**
  - Revised platelet count binning to use SOFA score coagulation criteria based on [ASPR TRACIE SOFA Score Fact Sheet](https://files.asprtracie.hhs.gov/documents/aspr-tracie-sofa-score-fact-sheet.pdf)
  - < 20 k/uL: "4 (Extreme Thrombocytopenia / Risk of Spontaneous Bleeding)"
  - 20 – 49 k/uL: "3 (Severe Thrombocytopenia)" (inclusive range)
  - 50 – 99 k/uL: "2 (Moderate Thrombocytopenia)" (inclusive range)
  - 100 – 149 k/uL: "1 (Mild Thrombocytopenia)" (inclusive range)
  - >= 150 k/uL: "0 (No Coagulopathy)" (inclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 20, 50, 100, 150, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all five SOFA score categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for Platelet_Cnt
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "20 – 49", "50 – 99", "100 – 149") and ">= 150" for Platelet_Cnt

## [0.5.9] - 2025-11-17 04:30:00

### Changed

- **Updated WBC (White Blood Cell Count) Binning Thresholds**
  - Revised WBC binning to use APACHE II severity classification based on [Knaus et al. (1985)](https://pubmed.ncbi.nlm.nih.gov/3928249/)
  - < 1 k/uL: "Critical Low"
  - 1 – 2.9 k/uL: "Moderate Low" (inclusive range)
  - 3 – 14.9 k/uL: "Normal" (inclusive range)
  - 15 – 19.9 k/uL: "Mild High" (inclusive range)
  - 20 – 39.9 k/uL: "Moderate High" (inclusive range)
  - ≥ 40 k/uL: "Critical High" (inclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 1.0, 3.0, 15.0, 20.0, 40.0, inf]
  - Added special binning logic in `bin_continuous_value()` to handle all six WBC categories with proper inclusive ranges
  - Added reference field to `BINNING_THRESHOLDS` for WBC
  - Updated range formatting in `create_label_legend.py` to display proper inclusive ranges (e.g., "1 – 2.9", "3 – 14.9") and "≥ 40" for WBC

## [0.5.8] - 2025-11-17 04:00:00

### Changed

- **Updated Hemoglobin Binning Thresholds**
  - Revised hemoglobin binning to use restrictive transfusion thresholds based on [JAMA article](https://jamanetwork.com/journals/jama/article-abstract/2569055)
  - < 7 g/dL: "Urgent Intervention (Restrictive Threshold)"
  - 7 – 8 g/dL: "Conditional/Pre-Operative Alert" (inclusive range)
  - > 8 g/dL: "Hemodynamically Adequate" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 7.0, 8.0, inf]
  - Added special binning logic in `bin_continuous_value()` to handle inclusive middle range and exclusive upper bound for Hemoglobin
  - Added reference field to `BINNING_THRESHOLDS` for Hemoglobin
  - Updated range formatting in `create_label_legend.py` to display "< 7", "7 – 8", and "> 8" for Hemoglobin

## [0.5.7] - 2025-11-17 03:30:00

### Changed

- **Updated INR1 (International Normalized Ratio) Binning Thresholds**
  - Revised INR1 binning to use King's College Criteria based on [O'Grady et al. (1989)](https://pubmed.ncbi.nlm.nih.gov/2490426/)
  - < 1.5: "No Acute Liver Failure (Acute Liver Injury or Normal)"
  - 1.5 – 6.5: "Acute Liver Failure / Monitor (Standard medical management)" (inclusive range)
  - > 6.5: "High Risk / Transplant Candidate (Criteria met if used in isolation with other markers*)" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 1.5, 6.5, inf]
  - Added special binning logic in `bin_continuous_value()` to handle inclusive middle range and exclusive upper bound for INR1
  - Added reference field to `BINNING_THRESHOLDS` for INR1
  - Updated range formatting in `create_label_legend.py` to display "< 1.5", "1.5 – 6.5", and "> 6.5" for INR1

## [0.5.6] - 2025-11-17 03:00:00

### Changed

- **Updated Creatinine (Creat) Binning Thresholds**
  - Revised creatinine binning to use King's College Criteria based on [O'Grady et al. (1989)](https://pubmed.ncbi.nlm.nih.gov/2490426/)
  - ≤ 3.4 mg/dL: "Lower Risk (Does not meet the specific renal transplant criterion)"
  - > 3.4 mg/dL: "High Risk (Meets King's College Criteria component for urgent transplant consideration)"
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 3.4, inf]
  - Added special binning logic in `bin_continuous_value()` to handle the 3.4 mg/dL threshold for Creatinine
  - Added reference field to `BINNING_THRESHOLDS` for Creatinine
  - Updated range formatting in `create_label_legend.py` to display "≤ 3.4" and "> 3.4" for Creatinine

## [0.5.5] - 2025-11-17 02:30:00

### Changed

- **Updated Lactate Binning Thresholds**
  - Revised lactate binning to use transplant candidacy risk-based categories based on [Bernal et al. (2002)](https://pubmed.ncbi.nlm.nih.gov/11867109/)
  - < 2.0 mmol/L: "Likely Spontaneous Recovery (Low Risk)"
  - 2.0 – 3.0 mmol/L: "Intermediate Risk (Requires Trend Monitoring)" (inclusive range)
  - > 3.0 mmol/L (Post-Fluid Resuscitation): "Urgent Transplant Candidate (High Risk)" (exclusive threshold)
  - Updated `BINNING_THRESHOLDS` in `create_vignettes.py` with new bins: [0, 2.0, 3.0, inf]
  - Added special binning logic in `bin_continuous_value()` to handle inclusive middle range and exclusive upper bound for Lactate
  - Added reference field to `BINNING_THRESHOLDS` for Lactate

- **Enhanced Label Legend Documentation**
  - Added `Reference` column to continuous label sheet in `create_label_legend.py`
  - Added PubMed reference for Lactate: https://pubmed.ncbi.nlm.nih.gov/11867109/
  - Updated range formatting to display inclusive ranges (e.g., "2.0 – 3.0" instead of "2.0 to < 3.0")
  - Changed last bin display from "≥ 3.0" to "> 3.0" for Lactate to match specification

## [0.5.4] - 2025-11-17 02:00:00

### Changed

- **Updated F27Q04 Categorical Labels**
  - Updated F27Q04 (Hepatic Encephalopathy Grade) labels with detailed clinical descriptions
  - Grade 0: "Normal/Minimal: No detectable changes in personality or behavior; minimal changes in coordination (Grade 0 of Hepatic Encephalopathy)"
  - Grade 1: "Trivial: Shortened attention span, euphoria or anxiety, impaired calculation (Grade 1 of Hepatic Encephalopathy)"
  - Grade 2: "Lethargy: Disoriented to time, apathy, personality change, inappropriate behavior. (Grade 2 of Hepatic Encephalopathy)"
  - Grade 3: "Somnolence : Responsive to stimuli but confused, gross disorientation. (Grade 3 of Hepatic Encephalopathy)"
  - Grade 4: "Coma: Unresponsive to voice; may or may not respond to painful stimuli. (Grade 4 of Hepatic Encephalopathy)"
  - Updated `CATEGORICAL_MAPPINGS` in `create_vignettes.py`
  - Label legend documentation will automatically reflect these changes when regenerated

## [0.5.3] - 2025-11-17 01:24:26

### Added

- **Download Prediction Results Feature**
  - Added download button to Streamlit app for exporting prediction results
  - Downloads Excel file with same structure as `agent_predictions.xlsx`
  - Includes all prediction data:
    - Subject ID and day
    - Final prediction, confidence, and reasoning
    - Individual agent decisions, confidence scores, and reasoning (Hepatologist, Critical Care, Transplant Surgeon)
    - Actual survival outcome
  - Dynamic filename: `prediction_Patient_{patient_id}_Day_{day}.xlsx`
  - File generated in-memory using `BytesIO` and `pd.ExcelWriter`
  - Full-width download button with clear labeling

## [0.5.2] - 2025-11-17 01:01:28

### Changed

- **Simplified Label Legend Documentation**
  - **categorical label sheet**: Removed `Transformation Method` column
    - Now contains: Variable Name, Numeric Value, Text Label, Description
  - **continuous label sheet**: Removed `Clinical Context` and `Binning Method` columns
    - Now contains: Variable Name, Unit, Value Range, Binned Label
  - **time trend label sheet**: 
    - Removed `Clinical Interpretation` column
    - Removed all "indicating" statements from `Description` column
    - Descriptions now contain only factual information (e.g., "Very large decrease (>100% reduction)" instead of "Very large decrease (>100% reduction), indicating rapid clinical improvement")
    - Now contains: Percent Change Range, Trend Label, Description
  - Streamlined documentation focuses on essential mapping information

## [0.5.1] - 2025-11-17 00:20:00

### Added

- **Label Legend Documentation**
  - Created `vignette_label_legend.xlsx` with three comprehensive documentation sheets:
    - **categorical label**: Explains how all categorical variables are transformed to text labels
      - Documents all 8 categorical variables (Sex, Hispanic, Pre_NAC_IV, Infection, Trt_Ventilator, Trt_Pressors, Trt_CVVH, F27Q04)
      - Shows numeric value → text label mappings
      - Includes variable descriptions
    - **continuous label**: Explains how all continuous variables are binned to text labels
      - Documents all 19 continuous variables with their clinical thresholds
      - Shows value ranges, binned labels, and units
    - **time trend label**: Explains how rate of change is categorized to trend labels
      - Documents 9 trend categories based on percent change ranges
      - Includes descriptions and calculation method
      - Explains context enhancement and cumulative history
  - Created `create_label_legend.py` script to generate the documentation file
  - Provides complete reference for understanding all label transformations in the vignettes

### Changed

- **Streamlit App UI Improvements**
  - Removed empty text_area boxes, replaced with formatted markdown display
  - Moved actual 21-day survival label to bottom of results (after all predictions)
  - Fixed accessibility warnings by adding proper labels to text_area widgets

## [0.5.0] - 2025-11-17 00:15:27

### Added

- **Streamlit Web Application**
  - Created beautiful, user-friendly Streamlit app (`streamlit_app.py`)
  - Features:
    - Automatic loading of `clinical_vignettes.xlsx`
    - Patient ID dropdown (all available patients)
    - Day dropdown (filtered by selected patient)
    - Single "Predict Survival" button
    - Displays clinical vignettes for each agent (Hepatologist, Critical Care, Transplant Surgeon)
    - Shows individual agent decisions with reasoning and confidence scores
    - Displays final committee prediction with reasoning and confidence
    - Weighted voting breakdown visualization
    - Color-coded confidence scores (high/medium/low)
    - Dataset statistics display
  - Beautiful UI with custom CSS styling, gradient cards, and responsive layout
  - Caching for data loading and graph compilation for performance

### Changed

- **API Parameter Updates for gpt-5 Model**
  - Replaced `max_tokens` with `max_completion_tokens` (required by gpt-5)
  - Removed `temperature` parameter (gpt-5 only supports default value of 1)
  - All 7 API calls updated across all agents

## [0.4.3] - 2025-11-16 23:55:00

### Changed

- **Updated Deployment Configuration**
  - Changed default model from `gpt-4o` to `gpt-5`
  - Removed default endpoint URL - now requires `ENDPOINT_URL` environment variable
  - Updated `get_azure_openai_client()` to match new deployment pattern
  - Model name and deployment name both set to `"gpt-5"`
  - Added validation to ensure `ENDPOINT_URL` is provided

## [0.4.2] - 2025-11-16 23:50:00

### Added

- **Confidence Scores for Individual Agents**
  - Added `confidence` field to `AgentDecision` Pydantic model (0.0 to 1.0)
  - Each agent (Hepatologist, Critical Care Physician, Transplant Surgeon) now provides confidence score
  - Confidence extracted from LLM structured output or parsed from text fallback
  - Output file includes: `hepatologist_confidence`, `critical_care_confidence`, `transplant_surgeon_confidence`

### Changed

- **Simplified FinalPrediction Model**
  - Removed redundant fields from `FinalPrediction`: `hepatologist_decision`, `critical_care_decision`, `transplant_surgeon_decision`
  - Individual agent decisions are already available in state and output file as separate columns
  - `FinalPrediction` now only contains: `prediction`, `confidence`, `reasoning`
  - Updated `process_patient_day()` to return dictionary with all outputs (final + individual agents)
  - Output file structure: Final prediction columns + individual agent columns (decision, confidence, reasoning for each)

## [0.4.1] - 2025-11-16 23:38:16

### Changed

- **Updated Azure OpenAI Authentication**
  - Switched from Entra ID authentication to API key authentication
  - Uses `OpenAI` client with `base_url` and `api_key` parameters
  - Removed dependency on `azure-identity` package
  - Environment variables: `AZURE_OPENAI_API_KEY`, `ENDPOINT_URL`
  - Model: `gpt-5` (hardcoded, updated in v0.4.3)

## [0.4.0] - 2025-11-16 23:30:00

### Added

- **Multi-Agent AI System using LangGraph**
  - Implemented complete multi-agent architecture based on README.md Mermaid diagram
  - Created `multi_agent_system.py` with LangGraph workflow
  - Three specialist agents:
    - AI Hepatologist: Analyzes liver function, hepatic encephalopathy, liver-related complications
    - AI Critical Care Physician: Analyzes ICU parameters, organ support, critical care interventions
    - AI Transplant Surgeon: Analyzes surgical/MELD parameters, transplant candidacy
  - Final Synthesis Agent: AI Transplant Leader Committee with weighted voting
    - Weighting: Critical Care=40%, Surgeon=30%, Hepatologist=30%
  - Pydantic structured outputs:
    - `AgentDecision`: Individual agent decision (Yes/No) with confidence score and reasoning
    - `FinalPrediction`: Final committee prediction with confidence score and synthesis
  - Azure OpenAI integration
  - JSON mode for structured outputs (Pydantic models)
  - Input: Reads from `clinical_vignettes.xlsx` with agent-specific vignette columns
  - Output: Saves predictions to `agent_predictions.xlsx`
  - Architecture matches README.md diagram exactly

## [0.3.5] - 2025-11-16 23:21:54

### Changed

- **Removed Target Variable from Vignettes**
  - Removed `Spont_Survival21` (target variable) from all vignette columns
  - Target variable should never be passed to agents during prediction
  - Applied to: `patient_day_vignette`, `hepatologist_vignette`, `transplant_surgeon_vignette`, `critical_care_physician_vignette`
  - Target variable remains in the dataframe as a separate column for model training/evaluation

## [0.3.4] - 2025-11-16 23:13:32

### Added

- **Agent-Specific Vignette Columns**
  - Created three separate vignette columns based on README.md Agent to Variable Mapping:
    - `hepatologist_vignette`: Contains only variables assigned to AI Hepatologist
    - `transplant_surgeon_vignette`: Contains only variables assigned to AI Transplant Surgeon
    - `critical_care_physician_vignette`: Contains only variables assigned to AI Critical Care Physician
  - Each agent sees only their assigned variables (continuous and categorical)
  - Variable assignments match README.md exactly:
    - AI Hepatologist: ALT, Arterial_Ammonia, Bilirubin, Creat, F27Q04, Hispanic, INR1, Lymph, Platelet_Cnt, Pre_NAC_IV, Prothrom_Sec, Sex, Venous_Ammonia, WBC, ammonia
    - AI Transplant Surgeon: Bilirubin, Creat, F27Q04, Hemoglobin, Hispanic, INR1, Infection, NA, Platelet_Cnt, Prothrom_Sec, Ratio_PO2_FiO2, Trt_CVVH, Trt_Pressors, Trt_Ventilator
    - AI Critical Care Physician: Arterial_Ammonia, Creat, F27Q04, HCO3, Hemoglobin, INR1, Infection, Lactate, Lymph, NA, PMN, Phosphate, Platelet_Cnt, Ratio_PO2_FiO2, Trt_CVVH, Trt_Pressors, Trt_Ventilator, Venous_Ammonia, WBC, ammonia
  - Format: Same human-readable format as comprehensive vignette, but filtered by agent assignment

## [0.3.3] - 2025-11-16 23:05:07

### Added

- **Comprehensive Clinical Vignette Column**
  - Added `patient_day_vignette` column that concatenates all text information into a single human-readable clinical narrative
  - Uses natural language with verbs like "is", "has", "shows" for readability
  - Sections separated by newline characters (`\n`)
  - Includes: patient demographics, laboratory values (binned), trend analysis, clinical status, and outcome
  - No numeric values - only descriptive text labels
  - One comprehensive vignette per patient-day combination
  - Format: Multi-line text narrative suitable for LLM input

## [0.3.2] - 2025-11-16 22:50:03

### Added

- **Cumulative Trend History**
  - Added `_trend_history` columns for all continuous variables showing cumulative progression from day 1
  - For day i, shows all trends from day 1 to day i in sequential format
  - Format: "day 1 to day 2: trend, then day 2 to day 3: trend, then day 3 to day 4: trend"
  - Day 1 has no trend history (baseline)
  - Provides complete clinical narrative of variable progression over time
  - Example: Day 4 shows trends from day 1→2, day 2→3, and day 3→4 all in one column

## [0.3.1] - 2025-11-13 10:09:57

### Changed

- **Categorical Text Labels**
  - Added descriptive text columns for categorical variables in `create_vignettes.py`
  - `Sex`, `Hispanic`, `Pre_NAC_IV` now include human-readable labels
  - Treatment indicators and coma grade (`Infection`, `Trt_Ventilator`, `Trt_Pressors`, `Trt_CVVH`, `F27Q04`) now output clinical descriptions
  - Updated `clinical_vignettes.xlsx` to include `_text` columns alongside raw values

## [0.3.0] - 2025-11-13 01:51:37

### Added

- **Clinical Vignette Creation**
  - Created `create_vignettes.py` script to generate clinical vignettes for each patient-day combination
  - Implemented clinical binning for 18 continuous variables using medical thresholds:
    - Lactate, Creatinine, INR1, Hemoglobin, WBC, Platelet_Cnt, Bilirubin, ALT, NA, HCO3, Phosphate, PH, Arterial_Ammonia, Venous_Ammonia, ammonia, Ratio_PO2_FiO2, Prothrom_Sec, PMN, Lymph
  - Binning categories: Normal, Elevated, High, Critical (with clinical context)
  - Time series trend analysis between consecutive days:
    - Calculates rate of change and trend direction (Rapidly Worsening, Improving, Stable, etc.)
    - Includes context about bin transitions (e.g., "from Normal to Elevated")
    - Day 1 (Admission) has no trend data (as expected)
  - Output: `clinical_vignettes.xlsx` with 17,983 vignettes (2,569 subjects × ~7 days)
  - Each vignette contains: subject_id, day, Spont_Survival21 (target), static variables, binned values, raw values, trends, and treatment variables

### Technical Details

- **Binning Implementation**
  - Uses clinical thresholds based on medical literature and README examples
  - Each variable has 3-4 bins with descriptive labels
  - Handles missing values gracefully
  - Preserves original values alongside binned categories

- **Trend Calculation**
  - Calculates percentage change between consecutive days
  - Classifies trends: Rapidly Worsening/Improving, Worsening/Improving, Mildly Increasing/Decreasing, Stable
  - Includes contextual information about bin transitions
  - Only calculated for days 2-7 (Day 1 has no previous day for comparison)

## [0.2.2] - 2025-11-13 01:42:21

### Changed

- **Day Column Naming**
  - "Admission" values in `zVisitNm` column are now mapped to "day 1" instead of "day_Admission"
  - Column naming updated: `variable_day_Admission` → `variable_day_1`
  - All day columns now use consistent numeric format: `variable_day_1`, `variable_day_2`, `variable_day_3`, etc.
  - Updated `extract_day_number()` function to return '1' for "ALF Admission" values

## [0.2.1] - 2025-11-13 01:25:00

### Security

- **Password Management**
  - Removed hardcoded password from source code
  - Added `python-dotenv` dependency for environment variable management
  - Password now loaded from `.env` file using `os.getenv("EXCEL_PASSWORD")`
  - `.env` file is already in `.gitignore` to prevent accidental commits

## [0.2.0] - 2025-11-13 01:23:44

### Added

- **Encrypted File Support**
  - Added `msoffcrypto-tool` dependency for decrypting password-protected Excel files
  - Implemented automatic decryption in `read_excel_file()` function
  - All 4 Excel files now readable (previously 2 were encrypted)

### Changed

- **Complete Variable Extraction**
  - Now successfully extracts all 28 target variables (previously only 8)
  - All lab variables from encrypted files are now available:
    - `Hemoglobin`, `WBC`, `PMN`, `Lymph`, `Platelet_Cnt`, `Prothrom_Sec`, `ALT`, `Bilirubin`, `Creat`, `NA`, `HCO3`, `Phosphate`, `Lactate`, `PH`, `Arterial_Ammonia`, `Venous_Ammonia`, `INR1`, `ammonia`, `Ratio_PO2_FiO2`, `F27Q04`
  - Final output: 2,569 subjects with 173 columns (all variables unstacked by day)

### Fixed

- **Encrypted Files Issue Resolved**
  - `subjects_comagr_12MAR2025.xlsx` - now successfully decrypted and read
  - `subjects_labsV2_12MAR2025.xlsx` - now successfully decrypted and read
  - No missing variables remaining

### Technical Details

- **Decryption Implementation**
  - Uses `msoffcrypto.OfficeFile` to decrypt password-protected Excel files
  - Decrypted content is streamed to `io.BytesIO` for pandas to read
  - Falls back to decryption if normal file reading fails
  - Password loaded from environment variable using `python-dotenv` and `os.getenv("EXCEL_PASSWORD")`

## [0.1.0] - 2025-11-13 01:17:36

### Added

- **Project Setup**
  - Initialized project with `uv` package manager
  - Created `pyproject.toml` with Python 3.12+ requirement
  - Added dependencies: `pandas`, `openpyxl`, `xlrd`

- **Excel Processing Script**
  - Created `process_excel.py` script for processing multiple Excel files
  - Implemented inner join functionality across all Excel files using `subject_id` as key
  - Added support for extracting specific target variables from Excel files
  - Implemented `zVisitNm` column handling with automatic unstacking:
    - Variables with `zVisitNm` are unstacked from rows to columns
    - Format: `variable_day_1`, `variable_day_2`, `variable_day_3`, etc. (updated in v0.2.2)
    - Handles day extraction from values like "ALF Admission" (→ day 1), "ALF Day 2", etc.

- **Output Files**
  - `subject_ids.xlsx`: Contains single column with all unique subject IDs (2,631 subjects)
  - `merged_subjects.xlsx`: Contains inner-joined data with all target variables (2,629 subjects, 33 columns) - **Updated in v0.2.0: 2,569 subjects, 173 columns**

- **Variable Extraction**
  - Successfully extracted 8 target variables from readable files:
    - `Spont_Survival21`, `Sex`, `Hispanic`, `Pre_NAC_IV`
    - `Infection`, `Trt_Ventilator`, `Trt_Pressors`, `Trt_CVVH` (unstacked by day)
  - Automatic mapping of `male` column to `Sex` variable
  - **Updated in v0.2.0: All 28 target variables now extracted**

- **Logging and Reporting**
  - Comprehensive logging throughout the processing pipeline
  - Variable summary report showing found vs missing variables
  - Warnings for encrypted files that cannot be read - **Resolved in v0.2.0**

### Technical Details

- **File Processing**
  - Supports multiple Excel engines: `openpyxl` (for .xlsx) and `xlrd` (for .xls)
  - Handles files with and without `zVisitNm` column
  - Performs inner joins to ensure only subjects present in all files are included

- **Data Transformation**
  - Variables with `zVisitNm`: Pivoted from long to wide format with day suffixes
  - Variables without `zVisitNm`: Kept as single columns (one value per subject)
  - Day extraction handles: "ALF Admission" (→ day 1), "ALF Day 2", "ALF Day 3", etc. (updated in v0.2.2)

