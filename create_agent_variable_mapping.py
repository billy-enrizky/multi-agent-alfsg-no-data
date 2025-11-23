import pandas as pd
import logging
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Agent to Variable Mapping (from README.md and create_vignettes.py)
AGENT_VARIABLES = {
    'AI Hepatologist': {
        'continuous': ['ALT', 'Arterial_Ammonia', 'Bilirubin', 'Creat', 'INR1', 'Lymph', 'Platelet_Cnt', 'Prothrom_Sec', 'Venous_Ammonia', 'WBC', 'ammonia'],
        'categorical': ['Sex', 'Hispanic', 'Pre_NAC_IV', 'F27Q04']
    },
    'AI Transplant Surgeon': {
        'continuous': ['Bilirubin', 'Creat', 'Hemoglobin', 'INR1', 'NA', 'Platelet_Cnt', 'Prothrom_Sec', 'Ratio_PO2_FiO2'],
        'categorical': ['Hispanic', 'F27Q04', 'Infection', 'Trt_CVVH', 'Trt_Pressors', 'Trt_Ventilator']
    },
    'AI Critical Care Physician': {
        'continuous': ['Arterial_Ammonia', 'Creat', 'HCO3', 'Hemoglobin', 'INR1', 'Lactate', 'Lymph', 'NA', 'PMN', 'Phosphate', 'Platelet_Cnt', 'Ratio_PO2_FiO2', 'Venous_Ammonia', 'WBC', 'ammonia'],
        'categorical': ['F27Q04', 'Infection', 'Trt_CVVH', 'Trt_Pressors', 'Trt_Ventilator']
    }
}

def combine_variables(agent_vars: Dict[str, List[str]]) -> str:
    """Combine continuous and categorical variables into a comma-separated string."""
    all_vars = agent_vars['continuous'] + agent_vars['categorical']
    # Sort for consistent output
    all_vars_sorted = sorted(set(all_vars))
    return ', '.join(all_vars_sorted)

def create_agent_variable_mapping() -> pd.DataFrame:
    """Create a DataFrame with agent to variable mapping."""
    logger.info("Creating agent to variable mapping...")
    
    rows = []
    for agent_name, agent_vars in AGENT_VARIABLES.items():
        variables_str = combine_variables(agent_vars)
        rows.append({
            'Agent': agent_name,
            'Assigned Variables': variables_str
        })
    
    df = pd.DataFrame(rows)
    logger.info(f"Created mapping for {len(df)} agents")
    return df

def main():
    logger.info("Starting agent variable mapping generation")
    
    # Create mapping DataFrame
    mapping_df = create_agent_variable_mapping()
    
    # Save to Excel
    output_file = 'agent_variable_mapping.xlsx'
    mapping_df.to_excel(output_file, index=False, engine='openpyxl')
    logger.info(f"Saved agent variable mapping to {output_file}")
    
    # Print summary
    logger.info("\n" + "="*60)
    logger.info("AGENT VARIABLE MAPPING SUMMARY")
    logger.info("="*60)
    for idx, row in mapping_df.iterrows():
        logger.info(f"\n{row['Agent']}:")
        logger.info(f"  Variables: {row['Assigned Variables']}")
    
    logger.info(f"\nTotal agents: {len(mapping_df)}")
    logger.info(f"Output file: {output_file}")

if __name__ == '__main__':
    main()

