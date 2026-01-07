import pandas as pd
import numpy as np

# Load the pickle file
df = pd.read_pickle('ALFSG_12MAR2025_processed.pkl')

# Map zVisitNm to day numbers
day_mapping = {
    'ALF Admission': 1,
    'ALF Day 2': 2,
    'ALF Day 3': 3,
    'ALF Day 4': 4,
    'ALF Day 5': 5,
    'ALF Day 6': 6,
    'ALF Day 7': 7
}
df['day'] = df['zVisitNm'].map(day_mapping)

# Rename 'male' to 'Sex'
df = df.rename(columns={'male': 'Sex'})

# Create F27Q04 from Coma columns
coma_cols = ['Coma_0.0', 'Coma_1.0', 'Coma_2.0', 'Coma_3.0', 'Coma_4.0']
df['F27Q04'] = df[coma_cols].idxmax(axis=1).str.extract(r'Coma_(\d+)\.0').astype(float)

# Drop the individual Coma columns and zVisitNm
df = df.drop(columns=coma_cols + ['zVisitNm'])

# Identify static and time-varying columns
static_cols = ['subject_id', 'Spont_Survival21', 'Sex', 'Hispanic', 'Pre_NAC_IV']
time_varying_cols = [col for col in df.columns if col not in static_cols + ['day']]

# Pivot to wide format
# First, get static data (one row per subject)
static_df = df[static_cols].drop_duplicates('subject_id').set_index('subject_id')

# Then pivot time-varying data
wide_df = df.pivot(index='subject_id', columns='day', values=time_varying_cols)

# Flatten column names
wide_df.columns = [f"{col[0]}_day_{col[1]}" for col in wide_df.columns]

# Merge static and time-varying data
final_df = static_df.join(wide_df)

# Reset index to make subject_id a column
final_df = final_df.reset_index()

# Reorder columns to match merged_subjects.xlsx exactly
old_df = pd.read_excel('merged_subjects.xlsx')
final_df = final_df[old_df.columns]

# Convert specific columns to float64 to match merged_subjects.xlsx
# These are the binary/categorical columns that should be float64
float_columns = [
    'Spont_Survival21', 'Hispanic',  # static columns that should be float64
]

# Add all day columns for categorical variables
categorical_vars = ['F27Q04', 'Infection', 'Trt_Ventilator', 'Trt_Pressors', 'Trt_CVVH']
for var in categorical_vars:
    for day in range(1, 8):
        float_columns.append(f"{var}_day_{day}")

# Convert to float64
for col in float_columns:
    if col in final_df.columns:
        final_df[col] = final_df[col].astype('float64')

# Add a temporary row with NaN only for float columns to force float64 dtype inference
temp_row = {}
for col in final_df.columns:
    if col in float_columns:
        temp_row[col] = np.nan
    else:
        # For non-float columns, use a representative value
        if col == 'subject_id':
            temp_row[col] = -999  # dummy subject ID
        elif col == 'Sex':
            temp_row[col] = 0  # keep as int
        else:
            temp_row[col] = 0.0  # default for other columns

temp_df = pd.DataFrame([temp_row])
final_df_with_nan = pd.concat([final_df, temp_df], ignore_index=True)

print("Data types after conversion:")
for col in ['Spont_Survival21', 'Sex', 'F27Q04_day_1', 'Infection_day_1']:
    if col in final_df_with_nan.columns:
        print(f"{col}: {final_df_with_nan[col].dtype}")

# Save to Excel with openpyxl engine
final_df_with_nan.to_excel('ALFSG_12MAR2025_processed_wide.xlsx', index=False, engine='openpyxl')

# Reload and remove the temporary row
df_check = pd.read_excel('ALFSG_12MAR2025_processed_wide.xlsx', engine='openpyxl')
final_df_clean = df_check.iloc[:-1].copy()  # Remove last row (the dummy row)
final_df_clean.to_excel('ALFSG_12MAR2025_processed_wide.xlsx', index=False, engine='openpyxl')

print(f"Transformed data saved to ALFSG_12MAR2025_processed_wide.xlsx")
print(f"Shape: {final_df.shape}")
print(f"Columns: {len(final_df.columns)}")
print(f"Sample columns: {list(final_df.columns)[:10]}")