import pandas as pd
import logging
import io
import os
from pathlib import Path
import msoffcrypto
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Variables to extract
TARGET_VARIABLES = [
    'Spont_Survival21',
    'Sex',
    'Hispanic',
    'Pre_NAC_IV',
    'Hemoglobin',
    'WBC',
    'PMN',
    'Lymph',
    'Platelet_Cnt',
    'Prothrom_Sec',
    'ALT',
    'Bilirubin',
    'Creat',
    'NA',
    'HCO3',
    'Phosphate',
    'Lactate',
    'PH',
    'Arterial_Ammonia',
    'Venous_Ammonia',
    'INR1',
    'ammonia',
    'Ratio_PO2_FiO2',
    'F27Q04',
    'Infection',
    'Trt_Ventilator',
    'Trt_Pressors',
    'Trt_CVVH'
]

# Excel files to process
EXCEL_FILES = [
    'subjects_comagr_12MAR2025.xlsx',
    'subjects_dailychk_08NOV2024.xlsx',
    'subjects_labsV2_12MAR2025.xlsx',
    'subjects_unique_08NOV2024.xlsx'
]

# Password for encrypted Excel files (loaded from environment variable)
EXCEL_PASSWORD = os.getenv("EXCEL_PASSWORD")

def read_excel_file(filepath, password=None):
    """Try to read an Excel file with different engines. If it fails, try decrypting with password."""
    engines = ['openpyxl', 'xlrd']
    
    # First, try reading normally
    for engine in engines:
        try:
            df = pd.read_excel(filepath, engine=engine)
            logger.info(f"Successfully read {filepath} with {engine}")
            return df
        except Exception as e:
            logger.debug(f"Failed to read {filepath} with {engine}: {e}")
            continue
    
    # If normal reading failed, try decrypting if password is provided
    if password:
        try:
            logger.info(f"Attempting to decrypt {filepath} with password")
            decrypted_workbook = io.BytesIO()
            
            with open(filepath, 'rb') as file:
                office_file = msoffcrypto.OfficeFile(file)
                office_file.load_key(password=password)
                office_file.decrypt(decrypted_workbook)
            
            # Reset the stream position
            decrypted_workbook.seek(0)
            
            # Try reading the decrypted file
            for engine in engines:
                try:
                    df = pd.read_excel(decrypted_workbook, engine=engine)
                    logger.info(f"Successfully read decrypted {filepath} with {engine}")
                    return df
                except Exception as e:
                    logger.debug(f"Failed to read decrypted {filepath} with {engine}: {e}")
                    continue
            
        except Exception as e:
            logger.warning(f"Failed to decrypt {filepath}: {e}")
    
    logger.warning(f"Could not read {filepath} with any method")
    return None

def extract_day_number(zvisit_nm):
    """Extract day number from zVisitNm values like 'ALF Day 2' -> '2', 'ALF Admission' -> '1'."""
    if pd.isna(zvisit_nm):
        return None
    
    zvisit_str = str(zvisit_nm).strip()
    
    if 'Admission' in zvisit_str:
        return '1'  # Admission is treated as day 1
    elif 'Day' in zvisit_str:
        # Extract number after "Day"
        parts = zvisit_str.split('Day')
        if len(parts) > 1:
            day_num = parts[1].strip()
            return day_num
    return zvisit_str

def process_dataframe(df, filepath):
    """Process a dataframe: extract target variables and handle zVisitNm if present."""
    logger.info(f"Processing {filepath}")
    logger.info(f"Shape: {df.shape}, Columns: {list(df.columns)}")
    
    # Check if subject_id exists
    if 'subject_id' not in df.columns:
        logger.warning(f"No 'subject_id' column found in {filepath}")
        return None
    
    # Check if zVisitNm exists
    has_zvisit = 'zVisitNm' in df.columns
    
    # Find which target variables exist in this dataframe
    available_vars = [var for var in TARGET_VARIABLES if var in df.columns]
    logger.info(f"Available target variables in {filepath}: {available_vars}")
    
    # Also check for 'male' as it might be the Sex variable
    if 'male' in df.columns and 'Sex' not in df.columns:
        df = df.copy()
        df['Sex'] = df['male']
        if 'Sex' in TARGET_VARIABLES:
            available_vars.append('Sex')
    
    if not available_vars:
        logger.warning(f"No target variables found in {filepath}")
        return None
    
    # Select columns: subject_id, zVisitNm (if exists), and available target variables
    cols_to_select = ['subject_id'] + available_vars
    if has_zvisit:
        cols_to_select.append('zVisitNm')
    
    result_df = df[cols_to_select].copy()
    
    # If zVisitNm exists, we need to unstack the variables
    if has_zvisit:
        logger.info(f"zVisitNm found in {filepath}, will unstack all variables")
        # Extract day number
        result_df['day'] = result_df['zVisitNm'].apply(extract_day_number)
        
        # Unstack all variables that are in this dataframe
        unstacked_dfs = []
        
        for var in available_vars:
            if var in result_df.columns:
                # Pivot this variable by day
                pivot_df = result_df[['subject_id', 'day', var]].copy()
                pivot_df = pivot_df.pivot_table(
                    index='subject_id',
                    columns='day',
                    values=var,
                    aggfunc='first'  # Take first value if duplicates
                )
                
                # Rename columns to variable_dayX format
                pivot_df.columns = [f"{var}_day_{col}" for col in pivot_df.columns]
                
                unstacked_dfs.append(pivot_df)
        
        # Merge all unstacked dataframes
        if unstacked_dfs:
            final_df = unstacked_dfs[0]
            for df_pivot in unstacked_dfs[1:]:
                final_df = final_df.merge(df_pivot, left_index=True, right_index=True, how='outer')
            final_df = final_df.reset_index()
            return final_df
        else:
            # No variables to unstack, return just subject_id
            return result_df[['subject_id']].drop_duplicates()
    else:
        # No zVisitNm, just return the dataframe with subject_id and variables
        # Remove duplicates per subject_id (take first)
        return result_df.groupby('subject_id').first().reset_index()

def main():
    logger.info("Starting Excel file processing")
    
    # Read all Excel files
    dataframes = {}
    for filepath in EXCEL_FILES:
        full_path = Path(filepath)
        if not full_path.exists():
            logger.warning(f"File not found: {filepath}")
            continue
        
        # Try reading with password for encrypted files
        df = read_excel_file(filepath, password=EXCEL_PASSWORD)
        if df is not None:
            dataframes[filepath] = df
    
    if not dataframes:
        logger.error("No Excel files could be read!")
        return
    
    logger.info(f"Successfully read {len(dataframes)} Excel files")
    
    # Process each dataframe
    processed_dfs = {}
    for filepath, df in dataframes.items():
        processed_df = process_dataframe(df, filepath)
        if processed_df is not None:
            processed_dfs[filepath] = processed_df
    
    if not processed_dfs:
        logger.error("No dataframes could be processed!")
        return
    
    # Get all unique subject_ids
    all_subject_ids = set()
    for df in processed_dfs.values():
        if 'subject_id' in df.columns:
            all_subject_ids.update(df['subject_id'].unique())
    
    logger.info(f"Found {len(all_subject_ids)} unique subject IDs")
    
    # Create base dataframe with subject_id
    result_df = pd.DataFrame({'subject_id': sorted(all_subject_ids)})
    
    # Inner join all processed dataframes
    logger.info("Performing inner joins...")
    for filepath, df in processed_dfs.items():
        logger.info(f"Joining {filepath}")
        # Merge on subject_id
        result_df = result_df.merge(df, on='subject_id', how='inner')
        logger.info(f"After joining {filepath}: shape = {result_df.shape}")
    
    # Select only target variables (and their day variants) plus subject_id
    # Get all columns that match target variables or their day variants
    target_cols = ['subject_id']
    for var in TARGET_VARIABLES:
        # Add exact match
        if var in result_df.columns:
            target_cols.append(var)
        # Add day variants
        day_variants = [col for col in result_df.columns if col.startswith(f"{var}_day_")]
        target_cols.extend(day_variants)
    
    # Remove duplicates while preserving order
    target_cols = list(dict.fromkeys(target_cols))
    
    # Select only these columns
    final_df = result_df[target_cols].copy()
    
    logger.info(f"Final dataframe shape: {final_df.shape}")
    logger.info(f"Final columns: {list(final_df.columns)}")
    
    # Create summary of found vs missing variables
    found_vars = set()
    for col in final_df.columns:
        if col == 'subject_id':
            continue
        # Extract base variable name (remove _day_X suffix)
        if '_day_' in col:
            base_var = col.split('_day_')[0]
            found_vars.add(base_var)
        else:
            found_vars.add(col)
    
    missing_vars = set(TARGET_VARIABLES) - found_vars
    
    logger.info(f"\n{'='*60}")
    logger.info("VARIABLE SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Found variables ({len(found_vars)}): {sorted(found_vars)}")
    logger.info(f"Missing variables ({len(missing_vars)}): {sorted(missing_vars)}")
    
    if missing_vars:
        logger.warning(f"\nNote: Missing variables are likely in encrypted files:")
        logger.warning(f"  - subjects_comagr_12MAR2025.xlsx (CDFV2 Encrypted)")
        logger.warning(f"  - subjects_labsV2_12MAR2025.xlsx (CDFV2 Encrypted)")
    
    # Save to Excel
    output_file = 'merged_subjects.xlsx'
    final_df.to_excel(output_file, index=False, engine='openpyxl')
    logger.info(f"\nSaved results to {output_file}")
    
    # Also create a file with just subject_id
    subject_id_df = pd.DataFrame({'subject_id': sorted(all_subject_ids)})
    subject_id_file = 'subject_ids.xlsx'
    subject_id_df.to_excel(subject_id_file, index=False, engine='openpyxl')
    logger.info(f"Saved subject IDs to {subject_id_file}")

if __name__ == '__main__':
    main()

