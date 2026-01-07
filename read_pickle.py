import pandas as pd

df = pd.read_pickle('ALFSG_12MAR2025_processed.pkl')
print('Shape:', df.shape)
print('Columns:', list(df.columns))
print('Head:')
print(df.head())
df.to_excel('ALFSG_12MAR2025_processed.xlsx', index=False)