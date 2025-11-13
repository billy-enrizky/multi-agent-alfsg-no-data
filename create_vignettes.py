import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Clinical binning thresholds based on medical literature and README examples
BINNING_THRESHOLDS = {
    'Lactate': {
        'bins': [0, 2.0, 4.0, 7.0, float('inf')],
        'labels': ['Normal', 'Elevated (Hyperlactatemia)', 'Severely Elevated (Lactic Acidosis)', 'Critical (High Mortality Risk)'],
        'unit': 'mmol/L'
    },
    'Creat': {
        'bins': [0, 1.2, 1.6, 2.5, float('inf')],
        'labels': ['Normal', 'High (Meets Stage 1 AKI criteria)', 'Severely High (Stage 2 AKI)', 'Critical (Stage 3 AKI)'],
        'unit': 'mg/dL'
    },
    'INR1': {
        'bins': [0, 1.2, 1.8, 3.0, float('inf')],
        'labels': ['Normal', 'Elevated (Hepatic Dysfunction)', 'Severely Elevated (Synthetic Failure)', 'Critical'],
        'unit': ''
    },
    'Hemoglobin': {
        'bins': [0, 10.0, 12.0, 15.0, float('inf')],
        'labels': ['Critical (Severe Anemia)', 'Low (Moderate Anemia)', 'Normal', 'High'],
        'unit': 'g/dL'
    },
    'WBC': {
        'bins': [0, 4.0, 10.0, 15.0, float('inf')],
        'labels': ['Low (Leukopenia)', 'Normal', 'Elevated (Leukocytosis)', 'High (Severe Leukocytosis)'],
        'unit': 'k/uL'
    },
    'Platelet_Cnt': {
        'bins': [0, 50, 100, 150, float('inf')],
        'labels': ['Critical (Severe Thrombocytopenia)', 'Low (Thrombocytopenia)', 'Borderline', 'Normal'],
        'unit': 'k/uL'
    },
    'Bilirubin': {
        'bins': [0, 1.2, 2.0, 5.0, float('inf')],
        'labels': ['Normal', 'Elevated', 'High (Jaundice)', 'Critical (Severe Hyperbilirubinemia)'],
        'unit': 'mg/dL'
    },
    'ALT': {
        'bins': [0, 40, 100, 300, float('inf')],
        'labels': ['Normal', 'Elevated', 'High', 'Critical (Severe Hepatocellular Injury)'],
        'unit': 'U/L'
    },
    'NA': {
        'bins': [0, 130, 135, 145, float('inf')],
        'labels': ['Critical (Severe Hyponatremia)', 'Low (Hyponatremia)', 'Normal', 'High (Hypernatremia)'],
        'unit': 'mEq/L'
    },
    'HCO3': {
        'bins': [0, 18, 22, 26, float('inf')],
        'labels': ['Critical (Severe Acidosis)', 'Low (Acidosis)', 'Normal', 'High (Alkalosis)'],
        'unit': 'mEq/L'
    },
    'Phosphate': {
        'bins': [0, 2.5, 3.5, 4.5, float('inf')],
        'labels': ['Low (Hypophosphatemia)', 'Normal', 'Elevated', 'High (Hyperphosphatemia)'],
        'unit': 'mg/dL'
    },
    'PH': {
        'bins': [0, 7.2, 7.35, 7.45, float('inf')],
        'labels': ['Critical (Severe Acidosis)', 'Low (Acidosis)', 'Normal', 'High (Alkalosis)'],
        'unit': ''
    },
    'Arterial_Ammonia': {
        'bins': [0, 50, 100, 200, float('inf')],
        'labels': ['Normal', 'Elevated', 'High', 'Critical (Severe Hyperammonemia)'],
        'unit': 'μmol/L'
    },
    'Venous_Ammonia': {
        'bins': [0, 50, 100, 200, float('inf')],
        'labels': ['Normal', 'Elevated', 'High', 'Critical (Severe Hyperammonemia)'],
        'unit': 'μmol/L'
    },
    'ammonia': {
        'bins': [0, 50, 100, 200, float('inf')],
        'labels': ['Normal', 'Elevated', 'High', 'Critical (Severe Hyperammonemia)'],
        'unit': 'μmol/L'
    },
    'Ratio_PO2_FiO2': {
        'bins': [0, 200, 300, 400, float('inf')],
        'labels': ['Critical (Severe ARDS)', 'Low (ARDS)', 'Moderate (ALI)', 'Normal'],
        'unit': ''
    },
    'Prothrom_Sec': {
        'bins': [0, 12, 15, 18, float('inf')],
        'labels': ['Normal', 'Elevated', 'High', 'Critical (Severe Coagulopathy)'],
        'unit': 'seconds'
    },
    'PMN': {
        'bins': [0, 40, 60, 80, float('inf')],
        'labels': ['Low', 'Normal', 'Elevated', 'High'],
        'unit': '%'
    },
    'Lymph': {
        'bins': [0, 15, 30, 45, float('inf')],
        'labels': ['Low (Lymphopenia)', 'Normal', 'Elevated', 'High'],
        'unit': '%'
    }
}

def bin_continuous_value(value: float, var_name: str) -> Optional[str]:
    """Bin a continuous value based on clinical thresholds."""
    if pd.isna(value):
        return None
    
    if var_name not in BINNING_THRESHOLDS:
        return None
    
    thresholds = BINNING_THRESHOLDS[var_name]
    bins = thresholds['bins']
    labels = thresholds['labels']
    
    # Find which bin the value falls into
    for i in range(len(bins) - 1):
        if bins[i] <= value < bins[i + 1]:
            return labels[i]
    
    # Handle edge case for last bin
    if value >= bins[-2]:
        return labels[-1]
    
    return None

def calculate_trend(current: float, previous: float, days_diff: int = 1) -> Optional[str]:
    """Calculate trend description between two time points."""
    if pd.isna(current) or pd.isna(previous) or days_diff <= 0:
        return None
    
    if previous == 0:
        return None  # Cannot calculate percentage change from zero
    
    percent_change = ((current - previous) / previous) * 100
    absolute_change = current - previous
    
    # Determine trend based on magnitude and direction
    if abs(percent_change) < 5:
        return "Stable"
    elif percent_change > 50:
        return "Rapidly Increasing"
    elif percent_change > 20:
        return "Increasing"
    elif percent_change > 5:
        return "Mildly Increasing"
    elif percent_change < -50:
        return "Rapidly Decreasing"
    elif percent_change < -20:
        return "Decreasing"
    elif percent_change < -5:
        return "Mildly Decreasing"
    else:
        return "Stable"

# Categorical variable mappings
CATEGORICAL_MAPPINGS = {
    'Sex': {
        0: 'Female',
        1: 'Male',
        0.0: 'Female',
        1.0: 'Male'
    },
    'Hispanic': {
        0: 'Non-Hispanic',
        1: 'Hispanic',
        0.0: 'Non-Hispanic',
        1.0: 'Hispanic'
    },
    'Pre_NAC_IV': {
        0: 'No prior IV N-acetylcysteine',
        1: 'Received IV N-acetylcysteine',
        0.0: 'No prior IV N-acetylcysteine',
        1.0: 'Received IV N-acetylcysteine'
    },
    'Infection': {
        0: 'No infection documented',
        1: 'Infection documented',
        0.0: 'No infection documented',
        1.0: 'Infection documented'
    },
    'Trt_Ventilator': {
        0: 'Not on mechanical ventilation',
        1: 'Receiving mechanical ventilation',
        0.0: 'Not on mechanical ventilation',
        1.0: 'Receiving mechanical ventilation'
    },
    'Trt_Pressors': {
        0: 'No vasopressor support',
        1: 'Receiving vasopressor support',
        0.0: 'No vasopressor support',
        1.0: 'Receiving vasopressor support'
    },
    'Trt_CVVH': {
        0: 'Not receiving CVVH',
        1: 'Receiving CVVH',
        0.0: 'Not receiving CVVH',
        1.0: 'Receiving CVVH'
    },
    'F27Q04': {  # Coma Grade (West Haven Criteria for Hepatic Encephalopathy)
        0: 'No Hepatic Encephalopathy (Grade 0)',
        1: 'Mild Hepatic Encephalopathy (Grade 1)',
        2: 'Moderate Hepatic Encephalopathy (Grade 2)',
        3: 'Severe Hepatic Encephalopathy (Grade 3)',
        4: 'Coma (Grade 4)',
        0.0: 'No Hepatic Encephalopathy (Grade 0)',
        1.0: 'Mild Hepatic Encephalopathy (Grade 1)',
        2.0: 'Moderate Hepatic Encephalopathy (Grade 2)',
        3.0: 'Severe Hepatic Encephalopathy (Grade 3)',
        4.0: 'Coma (Grade 4)'
    }
}

def transform_categorical(value, var_name: str) -> Optional[str]:
    """Transform categorical variable to text label."""
    if pd.isna(value):
        return None
    
    if var_name not in CATEGORICAL_MAPPINGS:
        return None
    
    mapping = CATEGORICAL_MAPPINGS[var_name]
    
    # Try exact match first
    if value in mapping:
        return mapping[value]
    
    # Try converting to int/float
    try:
        if isinstance(value, float):
            int_val = int(value)
            if int_val in mapping:
                return mapping[int_val]
        elif isinstance(value, int):
            float_val = float(value)
            if float_val in mapping:
                return mapping[float_val]
    except (ValueError, TypeError):
        pass
    
    return None

def calculate_trend_detailed(current: float, previous: float, days_diff: int, var_name: str) -> Optional[str]:
    """Calculate detailed trend description with context."""
    if pd.isna(current) or pd.isna(previous) or days_diff <= 0:
        return None
    
    if previous == 0:
        return None
    
    percent_change = ((current - previous) / previous) * 100
    absolute_change = current - previous
    unit = BINNING_THRESHOLDS.get(var_name, {}).get('unit', '')
    
    # More nuanced trend classification
    if abs(percent_change) < 5:
        trend = "Stable"
    elif percent_change > 100:
        trend = "Rapidly Worsening"
    elif percent_change > 50:
        trend = "Rapidly Increasing"
    elif percent_change > 20:
        trend = "Worsening"
    elif percent_change > 5:
        trend = "Mildly Increasing"
    elif percent_change < -100:
        trend = "Rapidly Improving"
    elif percent_change < -50:
        trend = "Rapidly Decreasing"
    elif percent_change < -20:
        trend = "Improving"
    elif percent_change < -5:
        trend = "Mildly Decreasing"
    else:
        trend = "Stable"
    
    # Add context about the values
    current_bin = bin_continuous_value(current, var_name)
    previous_bin = bin_continuous_value(previous, var_name)
    
    if current_bin and previous_bin:
        if current_bin != previous_bin:
            return f"{trend} (from {previous_bin} to {current_bin})"
        else:
            return f"{trend} (remains {current_bin})"
    
    return trend

def create_vignettes(df: pd.DataFrame) -> pd.DataFrame:
    """Create clinical vignettes for each patient-day combination."""
    logger.info("Creating clinical vignettes...")
    
    # Get all day columns for each variable
    continuous_vars = [var for var in BINNING_THRESHOLDS.keys() if any(f"{var}_day_" in col for col in df.columns)]
    
    # Create a list to store vignette rows
    vignette_rows = []
    
    # Get static variables (not time-varying)
    static_vars = ['subject_id', 'Spont_Survival21', 'Sex', 'Hispanic', 'Pre_NAC_IV']
    static_data = df[static_vars].copy()
    
    # Process each subject
    for idx, row in df.iterrows():
        subject_id = row['subject_id']
        spont_survival = row['Spont_Survival21']
        
        # Get static variables for this subject
        static_row = static_data[static_data['subject_id'] == subject_id].iloc[0]
        
        # Process each day (1-7)
        for day in range(1, 8):
            day_str = str(day)
            
            # Create base vignette row
            vignette = {
                'subject_id': subject_id,
                'day': day,
                'Spont_Survival21': spont_survival,
                'Sex': static_row['Sex'],
                'Sex_text': transform_categorical(static_row['Sex'], 'Sex'),
                'Hispanic': static_row['Hispanic'],
                'Hispanic_text': transform_categorical(static_row['Hispanic'], 'Hispanic'),
                'Pre_NAC_IV': static_row['Pre_NAC_IV'],
                'Pre_NAC_IV_text': transform_categorical(static_row['Pre_NAC_IV'], 'Pre_NAC_IV')
            }
            
            # Add binned values for this day
            for var in continuous_vars:
                day_col = f"{var}_day_{day_str}"
                if day_col in df.columns:
                    value = row[day_col]
                    if not pd.isna(value):
                        binned = bin_continuous_value(value, var)
                        vignette[f"{var}_binned"] = binned
                        vignette[f"{var}_value"] = value
                    else:
                        vignette[f"{var}_binned"] = None
                        vignette[f"{var}_value"] = None
                else:
                    vignette[f"{var}_binned"] = None
                    vignette[f"{var}_value"] = None
            
            # Add trend information (comparing to previous day)
            if day > 1:
                prev_day = str(day - 1)
                for var in continuous_vars:
                    current_col = f"{var}_day_{day_str}"
                    prev_col = f"{var}_day_{prev_day}"
                    
                    if current_col in df.columns and prev_col in df.columns:
                        current_val = row[current_col]
                        prev_val = row[prev_col]
                        
                        if not pd.isna(current_val) and not pd.isna(prev_val):
                            trend = calculate_trend_detailed(current_val, prev_val, 1, var)
                            vignette[f"{var}_trend"] = trend
                        else:
                            vignette[f"{var}_trend"] = None
                    else:
                        vignette[f"{var}_trend"] = None
            else:
                # Day 1 (Admission) has no trend
                for var in continuous_vars:
                    vignette[f"{var}_trend"] = None
            
            # Add binary treatment variables with text labels
            for treatment in ['Infection', 'Trt_Ventilator', 'Trt_Pressors', 'Trt_CVVH', 'F27Q04']:
                day_col = f"{treatment}_day_{day_str}"
                if day_col in df.columns:
                    value = row[day_col]
                    vignette[treatment] = value if not pd.isna(value) else None
                    vignette[f"{treatment}_text"] = transform_categorical(value, treatment)
                else:
                    vignette[treatment] = None
                    vignette[f"{treatment}_text"] = None
            
            vignette_rows.append(vignette)
    
    vignettes_df = pd.DataFrame(vignette_rows)
    logger.info(f"Created {len(vignettes_df)} vignettes for {vignettes_df['subject_id'].nunique()} subjects")
    logger.info(f"Vignette shape: {vignettes_df.shape}")
    
    return vignettes_df

def main():
    logger.info("Starting vignette creation process")
    
    # Read merged subjects
    input_file = 'merged_subjects.xlsx'
    logger.info(f"Reading {input_file}")
    df = pd.read_excel(input_file)
    logger.info(f"Input shape: {df.shape}")
    
    # Create vignettes
    vignettes_df = create_vignettes(df)
    
    # Save output
    output_file = 'clinical_vignettes.xlsx'
    vignettes_df.to_excel(output_file, index=False, engine='openpyxl')
    logger.info(f"Saved vignettes to {output_file}")
    
    # Print summary
    logger.info("\n" + "="*60)
    logger.info("VIGNETTE SUMMARY")
    logger.info("="*60)
    logger.info(f"Total vignettes: {len(vignettes_df)}")
    logger.info(f"Unique subjects: {vignettes_df['subject_id'].nunique()}")
    logger.info(f"Days per subject: {len(vignettes_df) / vignettes_df['subject_id'].nunique():.1f}")
    logger.info(f"\nSample columns: {list(vignettes_df.columns[:15])}...")
    logger.info(f"\nSample vignette (first row):")
    print(vignettes_df.iloc[0][:20].to_dict())

if __name__ == '__main__':
    main()

