# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

