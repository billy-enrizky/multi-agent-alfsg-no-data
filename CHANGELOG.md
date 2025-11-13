# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
    - Format: `variable_day_2`, `variable_day_3`, `variable_day_Admission`, etc.
    - Handles day extraction from values like "ALF Day 2", "ALF Admission"

- **Output Files**
  - `subject_ids.xlsx`: Contains single column with all unique subject IDs (2,631 subjects)
  - `merged_subjects.xlsx`: Contains inner-joined data with all target variables (2,629 subjects, 33 columns)

- **Variable Extraction**
  - Successfully extracted 8 target variables from readable files:
    - `Spont_Survival21`, `Sex`, `Hispanic`, `Pre_NAC_IV`
    - `Infection`, `Trt_Ventilator`, `Trt_Pressors`, `Trt_CVVH` (unstacked by day)
  - Automatic mapping of `male` column to `Sex` variable

- **Logging and Reporting**
  - Comprehensive logging throughout the processing pipeline
  - Variable summary report showing found vs missing variables
  - Warnings for encrypted files that cannot be read

### Known Issues

- **Encrypted Files**
  - `subjects_comagr_12MAR2025.xlsx` (CDFV2 Encrypted) - cannot be read
  - `subjects_labsV2_12MAR2025.xlsx` (CDFV2 Encrypted) - cannot be read
  - These files likely contain the missing 20 lab variables:
    - `ALT`, `Arterial_Ammonia`, `Bilirubin`, `Creat`, `F27Q04`, `HCO3`, `Hemoglobin`, `INR1`, `Lactate`, `Lymph`, `NA`, `PH`, `PMN`, `Phosphate`, `Platelet_Cnt`, `Prothrom_Sec`, `Ratio_PO2_FiO2`, `Venous_Ammonia`, `WBC`, `ammonia`

### Technical Details

- **File Processing**
  - Supports multiple Excel engines: `openpyxl` (for .xlsx) and `xlrd` (for .xls)
  - Handles files with and without `zVisitNm` column
  - Performs inner joins to ensure only subjects present in all files are included

- **Data Transformation**
  - Variables with `zVisitNm`: Pivoted from long to wide format with day suffixes
  - Variables without `zVisitNm`: Kept as single columns (one value per subject)
  - Day extraction handles: "ALF Admission", "ALF Day 2", "ALF Day 3", etc.

