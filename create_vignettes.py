import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Clinical binning thresholds based on medical literature and README examples
BINNING_THRESHOLDS = {
    'Lactate': {
        'bins': [0, 2.0, 3.0, float('inf')],
        'labels': ['Likely Spontaneous Recovery (Low Risk)', 'Intermediate Risk (Requires Trend Monitoring)', 'Urgent Transplant Candidate (High Risk) (Post-Fluid Resuscitation)'],
        'unit': 'mmol/L',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/11867109/'
    },
    'Creat': {
        'bins': [0, 3.4, float('inf')],
        'labels': ['Lower Risk (Does not meet the specific renal transplant criterion)', 'High Risk (Meets King\'s College Criteria component for urgent transplant consideration)'],
        'unit': 'mg/dL',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/2490426/'
    },
    'INR1': {
        'bins': [0, 1.5, 6.5, float('inf')],
        'labels': ['No Acute Liver Failure (Acute Liver Injury or Normal)', 'Acute Liver Failure / Monitor (Standard medical management)', 'High Risk / Transplant Candidate (Criteria met if used in isolation with other markers*)'],
        'unit': '',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/2490426/'
    },
    'Hemoglobin': {
        'bins': [0, 7.0, 8.0, float('inf')],
        'labels': ['Urgent Intervention (Restrictive Threshold)', 'Conditional/Pre-Operative Alert', 'Hemodynamically Adequate'],
        'unit': 'g/dL',
        'reference': 'https://jamanetwork.com/journals/jama/article-abstract/2569055'
    },
    'WBC': {
        'bins': [0, 1.0, 3.0, 15.0, 20.0, 40.0, float('inf')],
        'labels': ['Critical Low', 'Moderate Low', 'Normal', 'Mild High', 'Moderate High', 'Critical High'],
        'unit': 'k/uL',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/3928249/'
    },
    'Platelet_Cnt': {
        'bins': [0, 20, 50, 100, 150, float('inf')],
        'labels': ['4 (Extreme Thrombocytopenia / Risk of Spontaneous Bleeding)', '3 (Severe Thrombocytopenia)', '2 (Moderate Thrombocytopenia)', '1 (Mild Thrombocytopenia)', '0 (No Coagulopathy)'],
        'unit': 'k/uL',
        'reference': 'https://files.asprtracie.hhs.gov/documents/aspr-tracie-sofa-score-fact-sheet.pdf'
    },
    'Bilirubin': {
        'bins': [0, 1.2, 2.0, 6.0, 12.0, float('inf')],
        'labels': ['0 (Normal function)', '1 (Mild dysfunction)', '2 (Moderate dysfunction)', '3 (Severe dysfunction)', '4 (Critical liver failure)'],
        'unit': 'mg/dL',
        'reference': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC9837980/'
    },
    'ALT': {
        'bins': [0, 120, 200, 800, float('inf')],
        'labels': ['Grade 1 (Mild)', 'Grade 2 (Moderate)', 'Grade 3 (Severe)', 'Grade 4 (Life-Threatening / Acute Liver Failure)'],
        'unit': 'U/L',
        'reference': 'https://www.ncbi.nlm.nih.gov/books/NBK548241/'
    },
    'NA': {
        'bins': [0, 135, 145, 155, float('inf')],
        'labels': ['Hyponatremia / High Risk', 'Sub-therapeutic / Monitor', 'Therapeutic Target / Neuroprotective', 'Hypernatremia / Monitor'],
        'unit': 'mEq/L',
        'reference': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7432735/'
    },
    'HCO3': {
        'bins': [0, 10, 22, float('inf')],
        'labels': ['Severe Metabolic Acidosis', 'Mild to Moderate Metabolic Acidosis', 'Normal / Compensated'],
        'unit': 'mEq/L',
        'reference': 'https://www.ncbi.nlm.nih.gov/books/NBK482146/'
    },
    'Phosphate': {
        'bins': [0, 2.5, 5.0, float('inf')],
        'labels': ['High Likelihood of Spontaneous Recovery', 'Indeterminate / Moderate Risk', 'High Risk of Mortality / Urgent Transplant Candidate'],
        'unit': 'mg/dL',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/12829902/'
    },
    'PH': {
        'bins': [0, 7.30, float('inf')],
        'labels': ['Urgent Transplant Candidate (High likelihood of mortality without liver transplantation; meets the single KCC criterion for listing regardless of encephalopathy grade)', 'Monitor / Assess Other Criteria (Survival is possible with supportive care unless the patient meets the alternative criteria triad: INR > 6.5, Creatinine > 3.4 mg/dL, and Grade III/IV Encephalopathy)'],
        'unit': '',
        'reference': 'https://www.ncbi.nlm.nih.gov/books/NBK441917/'
    },
    'Arterial_Ammonia': {
        'bins': [0, 150, 200, float('inf')],
        'labels': ['Lower Risk (Intracranial hypertension is infrequent below this threshold, though hepatic encephalopathy may still be present)', 'High Risk (Significant risk of developing intracranial hypertension; indicates need for aggressive monitoring)', 'Critical Risk (Strongly associated with cerebral herniation; immediate neuroprotective strategies and transplant assessment required)'],
        'unit': 'μmol/L',
        'reference': 'https://onlinelibrary.wiley.com/doi/10.1002/hep.510290309'
    },
    'Venous_Ammonia': {
        'bins': [0, 100, 150, float('inf')],
        'labels': ['Lower Risk (Associated with lower risk of cerebral complications; favors continued medical management and assessment for spontaneous recovery)', 'High Risk (Predictive of severe Hepatic Encephalopathy [Grade III/IV]; indicates deterioration requiring intensive monitoring)', 'Critical Risk (High probability of intracranial hypertension and cerebral edema; triggers immediate neuroprotective protocols and urgent transplant listing assessment)'],
        'unit': 'μmol/L',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/17685471/'
    },
    'ammonia': {
        'bins': [0, 100, 200, float('inf')],
        'labels': ['Lower Risk of Neurotoxicity', 'High Risk of Intracranial Hypertension (ICH) & Severe Encephalopathy', 'Critical Risk of Cerebral Herniation'],
        'unit': 'μmol/L',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/17685471/'
    },
    'Ratio_PO2_FiO2': {
        'bins': [0, 100, 200, 300, float('inf')],
        'labels': ['Severe ARDS (Critical instability; high risk of hypoxia-induced cerebral edema)', 'Moderate ARDS (Significant respiratory compromise; potential contraindication for immediate transport/surgery)', 'Mild ARDS (Early sign of deterioration; warning for AI monitoring)', 'No ARDS (Physiologically stable respiratory status)'],
        'unit': 'mmHg',
        'reference': 'https://jamanetwork.com/journals/jama/article-abstract/1160659'
    },
    'Prothrom_Sec': {
        'bins': [0, 13.5, 100, float('inf')],
        'labels': ['Normal / Low Risk (Physiological baseline)', 'Abnormal / Monitor Trajectory (Indicates coagulopathy and liver injury requiring dynamic trend analysis)', 'Critical / Transplant Consideration (Meets King\'s College Criteria threshold for poor prognosis in acetaminophen toxicity)'],
        'unit': 'seconds',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/2490426/'
    },
    'PMN': {
        'bins': [0, 40, 80, float('inf')],
        'labels': ['Neutropenia / Immune Paralysis', 'Normal Physiologic Range', 'Hyper-inflammatory / SIRS'],
        'unit': '%',
        'reference': 'https://www.ucsfhealth.org/medical-tests/blood-differential-test'
    },
    'Lymph': {
        'bins': [0, 5.6, 17.8, float('inf')],
        'labels': ['High Risk / Severe Lymphopenia', 'Intermediate Risk / Warning', 'Low Risk / Normal'],
        'unit': '%',
        'reference': 'https://pubmed.ncbi.nlm.nih.gov/25045842/'
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
    
    # Special handling for Lactate with inclusive middle range and exclusive upper bound
    if var_name == 'Lactate':
        if value < 2.0:
            return labels[0]  # < 2.0 mmol/L: Likely Spontaneous Recovery (Low Risk)
        elif 2.0 <= value <= 3.0:
            return labels[1]  # 2.0 – 3.0 mmol/L: Intermediate Risk (Requires Trend Monitoring)
        elif value > 3.0:
            return labels[2]  # > 3.0 mmol/L: Urgent Transplant Candidate (High Risk)
        else:
            return None
    
    # Special handling for Creatinine with King's College Criteria threshold
    if var_name == 'Creat':
        if value <= 3.4:
            return labels[0]  # ≤ 3.4 mg/dL: Lower Risk (Does not meet the specific renal transplant criterion)
        elif value > 3.4:
            return labels[1]  # > 3.4 mg/dL: High Risk (Meets King's College Criteria component for urgent transplant consideration)
        else:
            return None
    
    # Special handling for INR1 with King's College Criteria thresholds
    if var_name == 'INR1':
        if value < 1.5:
            return labels[0]  # < 1.5: No Acute Liver Failure (Acute Liver Injury or Normal)
        elif 1.5 <= value <= 6.5:
            return labels[1]  # 1.5 – 6.5: Acute Liver Failure / Monitor (Standard medical management)
        elif value > 6.5:
            return labels[2]  # > 6.5: High Risk / Transplant Candidate (Criteria met if used in isolation with other markers*)
        else:
            return None
    
    # Special handling for Hemoglobin with restrictive transfusion thresholds
    if var_name == 'Hemoglobin':
        if value < 7.0:
            return labels[0]  # < 7 g/dL: Urgent Intervention (Restrictive Threshold)
        elif 7.0 <= value <= 8.0:
            return labels[1]  # 7 – 8 g/dL: Conditional/Pre-Operative Alert
        elif value > 8.0:
            return labels[2]  # > 8 g/dL: Hemodynamically Adequate
        else:
            return None
    
    # Special handling for WBC with APACHE II thresholds
    if var_name == 'WBC':
        if value < 1.0:
            return labels[0]  # < 1 k/uL: Critical Low
        elif 1.0 <= value < 3.0:
            return labels[1]  # 1 – 2.9 k/uL: Moderate Low
        elif 3.0 <= value < 15.0:
            return labels[2]  # 3 – 14.9 k/uL: Normal
        elif 15.0 <= value < 20.0:
            return labels[3]  # 15 – 19.9 k/uL: Mild High
        elif 20.0 <= value < 40.0:
            return labels[4]  # 20 – 39.9 k/uL: Moderate High
        elif value >= 40.0:
            return labels[5]  # ≥ 40 k/uL: Critical High
        else:
            return None
    
    # Special handling for Platelet_Cnt with SOFA score thresholds
    if var_name == 'Platelet_Cnt':
        if value < 20.0:
            return labels[0]  # < 20 k/uL: 4 (Extreme Thrombocytopenia / Risk of Spontaneous Bleeding)
        elif 20.0 <= value < 50.0:
            return labels[1]  # 20 – 49 k/uL: 3 (Severe Thrombocytopenia)
        elif 50.0 <= value < 100.0:
            return labels[2]  # 50 – 99 k/uL: 2 (Moderate Thrombocytopenia)
        elif 100.0 <= value < 150.0:
            return labels[3]  # 100 – 149 k/uL: 1 (Mild Thrombocytopenia)
        elif value >= 150.0:
            return labels[4]  # >= 150 k/uL: 0 (No Coagulopathy)
        else:
            return None
    
    # Special handling for Bilirubin with SOFA score thresholds
    if var_name == 'Bilirubin':
        if value < 1.2:
            return labels[0]  # < 1.2 mg/dL: 0 (Normal function)
        elif 1.2 <= value < 2.0:
            return labels[1]  # 1.2 – 1.9 mg/dL: 1 (Mild dysfunction)
        elif 2.0 <= value < 6.0:
            return labels[2]  # 2.0 – 5.9 mg/dL: 2 (Moderate dysfunction)
        elif 6.0 <= value < 12.0:
            return labels[3]  # 6.0 – 11.9 mg/dL: 3 (Severe dysfunction)
        elif value >= 12.0:
            return labels[4]  # >= 12.0 mg/dL: 4 (Critical liver failure)
        else:
            return None
    
    # Special handling for ALT with LiverTox severity grading
    if var_name == 'ALT':
        if value < 120.0:
            return labels[0]  # < 120 U/L: Grade 1 (Mild)
        elif 120.0 <= value < 200.0:
            return labels[1]  # 120 – 200 U/L: Grade 2 (Moderate)
        elif 200.0 <= value < 800.0:
            return labels[2]  # 200 – 800 U/L: Grade 3 (Severe)
        elif value > 800.0:
            return labels[3]  # > 800 U/L: Grade 4 (Life-Threatening / Acute Liver Failure)
        else:
            return None
    
    # Special handling for NA (Sodium) with neuroprotective thresholds
    if var_name == 'NA':
        if value < 135.0:
            return labels[0]  # < 135 mEq/L: Hyponatremia / High Risk
        elif 135.0 <= value < 145.0:
            return labels[1]  # 135 – 145 mEq/L: Sub-therapeutic / Monitor
        elif 145.0 <= value < 155.0:
            return labels[2]  # 145 – 155 mEq/L: Therapeutic Target / Neuroprotective
        elif value >= 155.0:
            return labels[3]  # >= 155 mEq/L: Hypernatremia / Monitor
        else:
            return None
    
    # Special handling for HCO3 (Bicarbonate) with metabolic acidosis thresholds
    if var_name == 'HCO3':
        if value < 10.0:
            return labels[0]  # < 10 mEq/L: Severe Metabolic Acidosis
        elif 10.0 <= value < 22.0:
            return labels[1]  # 10 – 22 mEq/L: Mild to Moderate Metabolic Acidosis
        elif value > 22.0:
            return labels[2]  # > 22 mEq/L: Normal / Compensated
        else:
            return None
    
    # Special handling for Phosphate with acute liver failure prognostic thresholds
    if var_name == 'Phosphate':
        if value < 2.5:
            return labels[0]  # < 2.5 mg/dL: High Likelihood of Spontaneous Recovery
        elif 2.5 <= value < 5.0:
            return labels[1]  # 2.5 – 5.0 mg/dL: Indeterminate / Moderate Risk
        elif value > 5.0:
            return labels[2]  # > 5.0 mg/dL: High Risk of Mortality / Urgent Transplant Candidate
        else:
            return None
    
    # Special handling for PH with King's College Criteria threshold
    if var_name == 'PH':
        if value < 7.30:
            return labels[0]  # < 7.30: Urgent Transplant Candidate (High likelihood of mortality without liver transplantation; meets the single KCC criterion for listing regardless of encephalopathy grade)
        elif value >= 7.30:
            return labels[1]  # >= 7.30: Monitor / Assess Other Criteria (Survival is possible with supportive care unless the patient meets the alternative criteria triad)
        else:
            return None
    
    # Special handling for Arterial_Ammonia with intracranial hypertension risk thresholds
    if var_name == 'Arterial_Ammonia':
        if value < 150.0:
            return labels[0]  # < 150 μmol/L: Lower Risk (Intracranial hypertension is infrequent below this threshold, though hepatic encephalopathy may still be present)
        elif 150.0 <= value < 200.0:
            return labels[1]  # 150 – 200 μmol/L: High Risk (Significant risk of developing intracranial hypertension; indicates need for aggressive monitoring)
        elif value > 200.0:
            return labels[2]  # > 200 μmol/L: Critical Risk (Strongly associated with cerebral herniation; immediate neuroprotective strategies and transplant assessment required)
        else:
            return None
    
    # Special handling for Venous_Ammonia with hepatic encephalopathy and intracranial hypertension risk thresholds
    if var_name == 'Venous_Ammonia':
        if value < 100.0:
            return labels[0]  # < 100 μmol/L: Lower Risk (Associated with lower risk of cerebral complications; favors continued medical management and assessment for spontaneous recovery)
        elif 100.0 <= value < 150.0:
            return labels[1]  # 100 – 150 μmol/L: High Risk (Predictive of severe Hepatic Encephalopathy [Grade III/IV]; indicates deterioration requiring intensive monitoring)
        elif value > 150.0:
            return labels[2]  # > 150 μmol/L: Critical Risk (High probability of intracranial hypertension and cerebral edema; triggers immediate neuroprotective protocols and urgent transplant listing assessment)
        else:
            return None
    
    # Special handling for ammonia with intracranial hypertension and cerebral herniation risk thresholds
    if var_name == 'ammonia':
        if value < 100.0:
            return labels[0]  # < 100 μmol/L: Lower Risk of Neurotoxicity
        elif 100.0 <= value < 200.0:
            return labels[1]  # 100 – 200 μmol/L: High Risk of Intracranial Hypertension (ICH) & Severe Encephalopathy
        elif value > 200.0:
            return labels[2]  # > 200 μmol/L: Critical Risk of Cerebral Herniation
        else:
            return None
    
    # Special handling for Ratio_PO2_FiO2 with ARDS classification thresholds
    if var_name == 'Ratio_PO2_FiO2':
        if value <= 100.0:
            return labels[0]  # ≤ 100 mmHg: Severe ARDS (Critical instability; high risk of hypoxia-induced cerebral edema)
        elif 100.0 < value <= 200.0:
            return labels[1]  # 100 < x ≤ 200 mmHg: Moderate ARDS (Significant respiratory compromise; potential contraindication for immediate transport/surgery)
        elif 200.0 < value <= 300.0:
            return labels[2]  # 200 < x ≤ 300 mmHg: Mild ARDS (Early sign of deterioration; warning for AI monitoring)
        elif value > 300.0:
            return labels[3]  # > 300 mmHg: No ARDS (Physiologically stable respiratory status)
        else:
            return None
    
    # Special handling for Prothrom_Sec with King's College Criteria threshold
    if var_name == 'Prothrom_Sec':
        if value < 13.5:
            return labels[0]  # < 13.5 seconds: Normal / Low Risk (Physiological baseline)
        elif 13.5 <= value < 100.0:
            return labels[1]  # 13.5 – 100 seconds: Abnormal / Monitor Trajectory (Indicates coagulopathy and liver injury requiring dynamic trend analysis)
        elif value >= 100.0:
            return labels[2]  # >= 100 seconds: Critical / Transplant Consideration (Meets King's College Criteria threshold for poor prognosis in acetaminophen toxicity)
        else:
            return None
    
    # Special handling for PMN with blood differential test ranges
    if var_name == 'PMN':
        if value < 40.0:
            return labels[0]  # < 40%: Neutropenia / Immune Paralysis
        elif 40.0 <= value <= 80.0:
            return labels[1]  # 40% – 80%: Normal Physiologic Range
        elif value > 80.0:
            return labels[2]  # > 80%: Hyper-inflammatory / SIRS
        else:
            return None
    
    # Special handling for Lymph with neutrophil-lymphocyte ratio prognostic thresholds
    if var_name == 'Lymph':
        if value < 5.6:
            return labels[0]  # < 5.6%: High Risk / Severe Lymphopenia
        elif 5.6 <= value <= 17.8:
            return labels[1]  # 5.6% – 17.8%: Intermediate Risk / Warning
        elif value > 17.8:
            return labels[2]  # > 17.8%: Low Risk / Normal
        else:
            return None
    
    # Standard binning for other variables
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

