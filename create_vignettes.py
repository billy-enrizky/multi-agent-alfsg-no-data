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

# Agent to Variable Mapping (from README.md)
AGENT_VARIABLES = {
    'AI_Hepatologist': {
        'continuous': ['ALT', 'Arterial_Ammonia', 'Bilirubin', 'Creat', 'INR1', 'Lymph', 'Platelet_Cnt', 'Prothrom_Sec', 'Venous_Ammonia', 'WBC', 'ammonia'],
        'categorical': ['Sex', 'Hispanic', 'Pre_NAC_IV', 'F27Q04']
    },
    'AI_Transplant_Surgeon': {
        'continuous': ['Bilirubin', 'Creat', 'Hemoglobin', 'INR1', 'NA', 'Platelet_Cnt', 'Prothrom_Sec', 'Ratio_PO2_FiO2'],
        'categorical': ['Hispanic', 'F27Q04', 'Infection', 'Trt_CVVH', 'Trt_Pressors', 'Trt_Ventilator']
    },
    'AI_Critical_Care_Physician': {
        'continuous': ['Arterial_Ammonia', 'Creat', 'HCO3', 'Hemoglobin', 'INR1', 'Lactate', 'Lymph', 'NA', 'PMN', 'Phosphate', 'Platelet_Cnt', 'Ratio_PO2_FiO2', 'Venous_Ammonia', 'WBC', 'ammonia'],
        'categorical': ['F27Q04', 'Infection', 'Trt_CVVH', 'Trt_Pressors', 'Trt_Ventilator']
    }
}

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
        0: 'Normal/Minimal: No detectable changes in personality or behavior; minimal changes in coordination (Grade 0 of Hepatic Encephalopathy)',
        1: 'Trivial: Shortened attention span, euphoria or anxiety, impaired calculation (Grade 1 of Hepatic Encephalopathy)',
        2: 'Lethargy: Disoriented to time, apathy, personality change, inappropriate behavior. (Grade 2 of Hepatic Encephalopathy)',
        3: 'Somnolence : Responsive to stimuli but confused, gross disorientation. (Grade 3 of Hepatic Encephalopathy)',
        4: 'Coma: Unresponsive to voice; may or may not respond to painful stimuli. (Grade 4 of Hepatic Encephalopathy)',
        0.0: 'Normal/Minimal: No detectable changes in personality or behavior; minimal changes in coordination (Grade 0 of Hepatic Encephalopathy)',
        1.0: 'Trivial: Shortened attention span, euphoria or anxiety, impaired calculation (Grade 1 of Hepatic Encephalopathy)',
        2.0: 'Lethargy: Disoriented to time, apathy, personality change, inappropriate behavior. (Grade 2 of Hepatic Encephalopathy)',
        3.0: 'Somnolence : Responsive to stimuli but confused, gross disorientation. (Grade 3 of Hepatic Encephalopathy)',
        4.0: 'Coma: Unresponsive to voice; may or may not respond to painful stimuli. (Grade 4 of Hepatic Encephalopathy)'
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
            
            # Add cumulative trend history (all trends from day 1 to current day)
            for var in continuous_vars:
                trend_history_parts = []
                
                if day > 1:
                    # Build cumulative history from day 1 to current day
                    for d in range(1, day):
                        prev_day_str = str(d)
                        curr_day_str = str(d + 1)
                        
                        prev_col = f"{var}_day_{prev_day_str}"
                        curr_col = f"{var}_day_{curr_day_str}"
                        
                        if prev_col in df.columns and curr_col in df.columns:
                            prev_val = row[prev_col]
                            curr_val = row[curr_col]
                            
                            if not pd.isna(prev_val) and not pd.isna(curr_val):
                                trend = calculate_trend_detailed(curr_val, prev_val, 1, var)
                                if trend:
                                    trend_history_parts.append(f"day {d} to day {d+1}: {trend}")
                
                if trend_history_parts:
                    # Join with "then" for sequential narrative
                    vignette[f"{var}_trend_history"] = ", then ".join(trend_history_parts)
                else:
                    vignette[f"{var}_trend_history"] = None
            
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
    
    # Create comprehensive clinical vignette text
    logger.info("Creating comprehensive clinical vignettes...")
    vignettes_df['patient_day_vignette'] = vignettes_df.apply(create_comprehensive_vignette, axis=1)
    
    # Create agent-specific vignettes
    logger.info("Creating agent-specific vignettes...")
    vignettes_df['hepatologist_vignette'] = vignettes_df.apply(lambda row: create_agent_vignette(row, 'AI_Hepatologist'), axis=1)
    vignettes_df['transplant_surgeon_vignette'] = vignettes_df.apply(lambda row: create_agent_vignette(row, 'AI_Transplant_Surgeon'), axis=1)
    vignettes_df['critical_care_physician_vignette'] = vignettes_df.apply(lambda row: create_agent_vignette(row, 'AI_Critical_Care_Physician'), axis=1)
    
    return vignettes_df

def create_comprehensive_vignette(row: pd.Series) -> str:
    """Create a comprehensive clinical vignette text from all available data."""
    parts = []
    
    # Patient identification
    parts.append(f"Patient {int(row['subject_id'])} on Day {int(row['day'])}")
    
    # Demographics section
    demo_parts = []
    if pd.notna(row.get('Sex_text')):
        demo_parts.append(f"is {row['Sex_text'].lower()}")
    if pd.notna(row.get('Hispanic_text')):
        demo_parts.append(f"is {row['Hispanic_text'].lower()}")
    if pd.notna(row.get('Pre_NAC_IV_text')):
        if 'received' in row['Pre_NAC_IV_text'].lower() or 'yes' in row['Pre_NAC_IV_text'].lower():
            demo_parts.append("has received prior IV N-acetylcysteine")
        else:
            demo_parts.append("has not received prior IV N-acetylcysteine")
    
    if demo_parts:
        parts.append("Patient " + ", ".join(demo_parts) + ".")
    
    # Laboratory values section
    continuous_vars = [var for var in BINNING_THRESHOLDS.keys() if f"{var}_binned" in row.index]
    
    lab_parts = []
    for var in continuous_vars:
        var_name = var.replace('_', ' ')
        binned = row.get(f"{var}_binned")
        
        if pd.notna(binned):
            lab_parts.append(f"{var_name} is {binned.lower()}")
    
    if lab_parts:
        parts.append("Laboratory values: " + "; ".join(lab_parts) + ".")
    
    # Trend history section
    trend_parts = []
    for var in continuous_vars:
        var_name = var.replace('_', ' ')
        trend_history = row.get(f"{var}_trend_history")
        
        if pd.notna(trend_history):
            trend_parts.append(f"{var_name} trend shows {trend_history.lower()}")
    
    if trend_parts:
        parts.append("Trend analysis: " + "; ".join(trend_parts) + ".")
    
    # Clinical status and treatments
    clinical_parts = []
    
    if pd.notna(row.get('Infection_text')):
        if 'yes' in row['Infection_text'].lower() or 'documented' in row['Infection_text'].lower():
            clinical_parts.append("has documented infection")
        else:
            clinical_parts.append("has no documented infection")
    
    if pd.notna(row.get('Trt_Ventilator_text')):
        if 'yes' in row['Trt_Ventilator_text'].lower() or 'receiving' in row['Trt_Ventilator_text'].lower():
            clinical_parts.append("is receiving mechanical ventilation")
        else:
            clinical_parts.append("is not on mechanical ventilation")
    
    if pd.notna(row.get('Trt_Pressors_text')):
        if 'yes' in row['Trt_Pressors_text'].lower() or 'receiving' in row['Trt_Pressors_text'].lower():
            clinical_parts.append("is receiving vasopressor support")
        else:
            clinical_parts.append("is not receiving vasopressor support")
    
    if pd.notna(row.get('Trt_CVVH_text')):
        if 'yes' in row['Trt_CVVH_text'].lower() or 'receiving' in row['Trt_CVVH_text'].lower():
            clinical_parts.append("is receiving continuous renal replacement therapy (CVVH)")
        else:
            clinical_parts.append("is not receiving CVVH")
    
    if pd.notna(row.get('F27Q04_text')):
        clinical_parts.append(f"has {row['F27Q04_text'].lower()}")
    
    if clinical_parts:
        parts.append("Clinical status: " + "; ".join(clinical_parts) + ".")
    
    # Note: Spont_Survival21 is the target variable and should NOT be included in vignettes
    
    # Join all parts with newlines
    return "\n".join(parts)

def create_agent_vignette(row: pd.Series, agent_name: str) -> str:
    """Create a clinical vignette text for a specific agent with only their assigned variables."""
    if agent_name not in AGENT_VARIABLES:
        return ""
    
    parts = []
    agent_vars = AGENT_VARIABLES[agent_name]
    
    # Patient identification
    parts.append(f"Patient {int(row['subject_id'])} on Day {int(row['day'])}")
    
    # Demographics section (only if agent has these variables)
    demo_parts = []
    if 'Sex' in agent_vars['categorical'] and pd.notna(row.get('Sex_text')):
        demo_parts.append(f"is {row['Sex_text'].lower()}")
    if 'Hispanic' in agent_vars['categorical'] and pd.notna(row.get('Hispanic_text')):
        demo_parts.append(f"is {row['Hispanic_text'].lower()}")
    if 'Pre_NAC_IV' in agent_vars['categorical'] and pd.notna(row.get('Pre_NAC_IV_text')):
        if 'received' in row['Pre_NAC_IV_text'].lower() or 'yes' in row['Pre_NAC_IV_text'].lower():
            demo_parts.append("has received prior IV N-acetylcysteine")
        else:
            demo_parts.append("has not received prior IV N-acetylcysteine")
    
    if demo_parts:
        parts.append("Patient " + ", ".join(demo_parts) + ".")
    
    # Laboratory values section (only agent's assigned variables)
    lab_parts = []
    for var in agent_vars['continuous']:
        var_name = var.replace('_', ' ')
        binned = row.get(f"{var}_binned")
        
        if pd.notna(binned):
            lab_parts.append(f"{var_name} is {binned.lower()}")
    
    if lab_parts:
        parts.append("Laboratory values: " + "; ".join(lab_parts) + ".")
    
    # Trend history section (only agent's assigned variables)
    trend_parts = []
    for var in agent_vars['continuous']:
        var_name = var.replace('_', ' ')
        trend_history = row.get(f"{var}_trend_history")
        
        if pd.notna(trend_history):
            trend_parts.append(f"{var_name} trend shows {trend_history.lower()}")
    
    if trend_parts:
        parts.append("Trend analysis: " + "; ".join(trend_parts) + ".")
    
    # Clinical status and treatments (only agent's assigned variables)
    clinical_parts = []
    
    if 'Infection' in agent_vars['categorical'] and pd.notna(row.get('Infection_text')):
        if 'yes' in row['Infection_text'].lower() or 'documented' in row['Infection_text'].lower():
            clinical_parts.append("has documented infection")
        else:
            clinical_parts.append("has no documented infection")
    
    if 'Trt_Ventilator' in agent_vars['categorical'] and pd.notna(row.get('Trt_Ventilator_text')):
        if 'yes' in row['Trt_Ventilator_text'].lower() or 'receiving' in row['Trt_Ventilator_text'].lower():
            clinical_parts.append("is receiving mechanical ventilation")
        else:
            clinical_parts.append("is not on mechanical ventilation")
    
    if 'Trt_Pressors' in agent_vars['categorical'] and pd.notna(row.get('Trt_Pressors_text')):
        if 'yes' in row['Trt_Pressors_text'].lower() or 'receiving' in row['Trt_Pressors_text'].lower():
            clinical_parts.append("is receiving vasopressor support")
        else:
            clinical_parts.append("is not receiving vasopressor support")
    
    if 'Trt_CVVH' in agent_vars['categorical'] and pd.notna(row.get('Trt_CVVH_text')):
        if 'yes' in row['Trt_CVVH_text'].lower() or 'receiving' in row['Trt_CVVH_text'].lower():
            clinical_parts.append("is receiving continuous renal replacement therapy (CVVH)")
        else:
            clinical_parts.append("is not receiving CVVH")
    
    if 'F27Q04' in agent_vars['categorical'] and pd.notna(row.get('F27Q04_text')):
        clinical_parts.append(f"has {row['F27Q04_text'].lower()}")
    
    if clinical_parts:
        parts.append("Clinical status: " + "; ".join(clinical_parts) + ".")
    
    # Note: Spont_Survival21 is the target variable and should NOT be included in vignettes
    
    # Join all parts with newlines
    return "\n".join(parts)

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

