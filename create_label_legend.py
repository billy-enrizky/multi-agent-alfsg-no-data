import pandas as pd
from create_vignettes import CATEGORICAL_MAPPINGS, BINNING_THRESHOLDS

def create_categorical_label_sheet():
    """Create sheet explaining categorical variable transformations."""
    rows = []
    
    for var_name, mapping in CATEGORICAL_MAPPINGS.items():
        # Get unique numeric values (excluding float duplicates)
        unique_values = set()
        for k, v in mapping.items():
            if isinstance(k, (int, float)):
                unique_values.add(int(k))
        
        for num_val in sorted(unique_values):
            # Get the text label (prefer int key, fallback to float)
            text_label = mapping.get(num_val, mapping.get(float(num_val), 'N/A'))
            
            # Add description
            if var_name == 'F27Q04':
                description = "West Haven Criteria for Hepatic Encephalopathy"
            elif var_name == 'Sex':
                description = "Biological sex"
            elif var_name == 'Hispanic':
                description = "Ethnicity indicator"
            elif var_name == 'Pre_NAC_IV':
                description = "Prior intravenous N-acetylcysteine administration"
            elif var_name == 'Infection':
                description = "Presence of documented or suspected infection"
            elif var_name == 'Trt_Ventilator':
                description = "Patient receiving invasive mechanical ventilation"
            elif var_name == 'Trt_Pressors':
                description = "Receiving vasopressor support"
            elif var_name == 'Trt_CVVH':
                description = "Receiving continuous renal replacement therapy"
            else:
                description = ""
            
            rows.append({
                'Variable Name': var_name,
                'Numeric Value': num_val,
                'Text Label': text_label,
                'Description': description
            })
    
    return pd.DataFrame(rows)

def create_continuous_label_sheet():
    """Create sheet explaining continuous variable binning."""
    rows = []
    
    for var_name, thresholds in BINNING_THRESHOLDS.items():
        bins = thresholds['bins']
        labels = thresholds['labels']
        unit = thresholds.get('unit', '')
        reference = thresholds.get('reference', '')
        
        # Create bin ranges
        for i in range(len(bins) - 1):
            bin_start = bins[i]
            bin_end = bins[i + 1]
            label = labels[i]
            
            # Format range with inclusive/exclusive notation
            if bin_start == float('-inf') or bin_start == 0:
                if bin_end == float('inf'):
                    range_str = f"≥ {bins[0] if bins[0] > 0 else 'all values'}"
                else:
                    # Special handling for Creatinine first bin (≤ 3.4)
                    if var_name == 'Creat' and bin_end == 3.4:
                        range_str = f"≤ {bin_end}"
                    elif var_name == 'PH' and bin_end == 7.30:
                        range_str = f"< {bin_end:.2f}"
                    else:
                        range_str = f"< {bin_end}"
            elif bin_end == float('inf'):
                # For last bin, use > instead of ≥ for specific variables
                if var_name == 'Lactate' and bin_start == 3.0:
                    range_str = f"> {bin_start}"
                elif var_name == 'Creat' and bin_start == 3.4:
                    range_str = f"> {bin_start}"
                elif var_name == 'INR1' and bin_start == 6.5:
                    range_str = f"> {bin_start}"
                elif var_name == 'Hemoglobin' and bin_start == 8.0:
                    range_str = f"> {bin_start}"
                elif var_name == 'WBC' and bin_start == 40.0:
                    range_str = f"≥ {int(bin_start)}"
                elif var_name == 'Platelet_Cnt' and bin_start == 150.0:
                    range_str = f">= {int(bin_start)}"
                elif var_name == 'Bilirubin' and bin_start == 12.0:
                    range_str = f">= {bin_start:.1f}"
                elif var_name == 'ALT' and bin_start == 800.0:
                    range_str = f"> {int(bin_start)}"
                elif var_name == 'NA' and bin_start == 155.0:
                    range_str = f">= {int(bin_start)}"
                elif var_name == 'HCO3' and bin_start == 22.0:
                    range_str = f"> {int(bin_start)}"
                elif var_name == 'Phosphate' and bin_start == 5.0:
                    range_str = f"> {bin_start:.1f}"
                elif var_name == 'PH' and bin_start == 7.30:
                    range_str = f">= {bin_start:.2f}"
                else:
                    range_str = f"≥ {bin_start}"
            else:
                # For middle bins, use inclusive range notation
                # Special handling for WBC to show upper bound as one decimal less
                if var_name == 'WBC':
                    # Format upper bound as one decimal less than bin_end
                    upper_bound = bin_end - 0.1
                    if bin_start == 0:
                        range_str = f"< {int(bin_end)}"
                    elif upper_bound.is_integer():
                        range_str = f"{int(bin_start)} – {int(upper_bound)}"
                    else:
                        range_str = f"{int(bin_start)} – {upper_bound:.1f}"
                elif var_name == 'Platelet_Cnt':
                    # Format upper bound as one less than bin_end for inclusive ranges
                    upper_bound = bin_end - 1
                    if bin_start == 0:
                        range_str = f"< {int(bin_end)}"
                    else:
                        range_str = f"{int(bin_start)} – {int(upper_bound)}"
                elif var_name == 'Bilirubin':
                    # Format upper bound as one decimal less than bin_end for inclusive ranges
                    upper_bound = bin_end - 0.1
                    if bin_start == 0:
                        range_str = f"< {bin_end:.1f}"
                    elif upper_bound.is_integer():
                        range_str = f"{bin_start:.1f} – {int(upper_bound)}"
                    else:
                        range_str = f"{bin_start:.1f} – {upper_bound:.1f}"
                elif var_name == 'ALT':
                    # Format upper bound as one less than bin_end for inclusive ranges (whole numbers)
                    upper_bound = bin_end - 1
                    if bin_start == 0:
                        range_str = f"< {int(bin_end)}"
                    else:
                        range_str = f"{int(bin_start)} – {int(upper_bound)}"
                elif var_name == 'NA':
                    # Format upper bound as one less than bin_end for inclusive ranges (whole numbers)
                    upper_bound = bin_end - 1
                    if bin_start == 0:
                        range_str = f"< {int(bin_end)}"
                    else:
                        range_str = f"{int(bin_start)} – {int(upper_bound)}"
                elif var_name == 'HCO3':
                    # Format upper bound as one less than bin_end for inclusive ranges (whole numbers)
                    upper_bound = bin_end - 1
                    if bin_start == 0:
                        range_str = f"< {int(bin_end)}"
                    else:
                        range_str = f"{int(bin_start)} – {int(upper_bound)}"
                elif var_name == 'Phosphate':
                    # Format upper bound as one decimal less than bin_end for inclusive ranges
                    upper_bound = bin_end - 0.1
                    if bin_start == 0:
                        range_str = f"< {bin_end:.1f}"
                    elif upper_bound.is_integer():
                        range_str = f"{bin_start:.1f} – {int(upper_bound)}"
                    else:
                        range_str = f"{bin_start:.1f} – {upper_bound:.1f}"
                else:
                    # Standard inclusive range notation (e.g., "2.0 – 3.0")
                    range_str = f"{bin_start} – {bin_end}"
            
            # Add clinical context
            if 'Critical' in label:
                clinical_context = "Requires immediate medical attention"
            elif 'High' in label or 'Severe' in label:
                clinical_context = "Clinically significant abnormality"
            elif 'Elevated' in label:
                clinical_context = "Mild to moderate abnormality"
            elif 'Normal' in label:
                clinical_context = "Within normal clinical range"
            elif 'Low' in label:
                clinical_context = "Below normal range"
            else:
                clinical_context = "Clinical significance varies"
            
            rows.append({
                'Variable Name': var_name,
                'Unit': unit,
                'Value Range': range_str,
                'Binned Label': label,
                'Reference': reference
            })
    
    return pd.DataFrame(rows)

def create_time_trend_label_sheet():
    """Create sheet explaining time series trend categorization."""
    rows = []
    
    # Trend categories based on calculate_trend_detailed function
    trend_categories = [
        {
            'Percent Change Range': '< -100%',
            'Trend Label': 'Rapidly Improving',
            'Description': 'Very large decrease (>100% reduction)'
        },
        {
            'Percent Change Range': '-100% to -50%',
            'Trend Label': 'Rapidly Decreasing',
            'Description': 'Large decrease (50-100% reduction)'
        },
        {
            'Percent Change Range': '-50% to -20%',
            'Trend Label': 'Improving',
            'Description': 'Moderate decrease (20-50% reduction)'
        },
        {
            'Percent Change Range': '-20% to -5%',
            'Trend Label': 'Mildly Decreasing',
            'Description': 'Small decrease (5-20% reduction)'
        },
        {
            'Percent Change Range': '-5% to +5%',
            'Trend Label': 'Stable',
            'Description': 'Minimal change (<5% change in either direction)'
        },
        {
            'Percent Change Range': '+5% to +20%',
            'Trend Label': 'Mildly Increasing',
            'Description': 'Small increase (5-20% increase)'
        },
        {
            'Percent Change Range': '+20% to +50%',
            'Trend Label': 'Worsening',
            'Description': 'Moderate increase (20-50% increase)'
        },
        {
            'Percent Change Range': '+50% to +100%',
            'Trend Label': 'Rapidly Increasing',
            'Description': 'Large increase (50-100% increase)'
        },
        {
            'Percent Change Range': '> +100%',
            'Trend Label': 'Rapidly Worsening',
            'Description': 'Very large increase (>100% increase)'
        }
    ]
    
    df = pd.DataFrame(trend_categories)
    
    # Add additional context rows
    context_rows = [
        {
            'Percent Change Range': '---',
            'Trend Label': 'Calculation Method',
            'Description': 'Percent change = ((current_value - previous_value) / previous_value) × 100'
        },
        {
            'Percent Change Range': '---',
            'Trend Label': 'Context Enhancement',
            'Description': 'Trend labels include bin context: "trend (from previous_bin to current_bin)" or "trend (remains bin)"'
        },
        {
            'Percent Change Range': '---',
            'Trend Label': 'Cumulative History',
            'Description': 'For day i, shows all trends from day 1 to day i: "day 1 to day 2: trend, then day 2 to day 3: trend, ..."'
        },
        {
            'Percent Change Range': '---',
            'Trend Label': 'Day 1 (Baseline)',
            'Description': 'No trend data available (admission day, no previous day for comparison)'
        }
    ]
    
    context_df = pd.DataFrame(context_rows)
    return pd.concat([df, context_df], ignore_index=True)

def main():
    """Create Excel file with label legend sheets."""
    print("Creating vignette_label_legend.xlsx...")
    
    # Create DataFrames for each sheet
    categorical_df = create_categorical_label_sheet()
    continuous_df = create_continuous_label_sheet()
    trend_df = create_time_trend_label_sheet()
    
    # Write to Excel with multiple sheets
    with pd.ExcelWriter('vignette_label_legend.xlsx', engine='openpyxl') as writer:
        categorical_df.to_excel(writer, sheet_name='categorical label', index=False)
        continuous_df.to_excel(writer, sheet_name='continuous label', index=False)
        trend_df.to_excel(writer, sheet_name='time trend label', index=False)
    
    print(f"✓ Created categorical label sheet: {len(categorical_df)} rows")
    print(f"✓ Created continuous label sheet: {len(continuous_df)} rows")
    print(f"✓ Created time trend label sheet: {len(trend_df)} rows")
    print("\nFile saved: vignette_label_legend.xlsx")

if __name__ == '__main__':
    main()

