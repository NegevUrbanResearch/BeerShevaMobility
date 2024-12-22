import pandas as pd

bgu_path = "/Users/noamgal/DSProjects/BeerShevaMobility/data-viz/output/dashboard_data/ben-gurion-university_inbound_temporal.csv"
soroka_path = "/Users/noamgal/DSProjects/BeerShevaMobility/data-viz/output/dashboard_data/soroka-medical-center_inbound_temporal.csv"
bgu_df = pd.read_csv(bgu_path)
print(bgu_df.head())
print(bgu_df.columns)

bgu_df = bgu_df['pedestrian_dist']
print(bgu_df)
print(len(bgu_df))


soroka_df = pd.read_csv(soroka_path)
soroka_df = soroka_df['pedestrian_dist']

print(soroka_df)
print(len(soroka_df))

# Filter for hours 6-22 and reweight distributions
def filter_and_reweight(df):
    # Filter hours between 6 and 22 (inclusive)
    mask = (df.index >= 6) & (df.index <= 22)
    filtered_df = df[mask]
    
    # Reweight to sum to 1
    return filtered_df / filtered_df.sum()

# Apply to both dataframes
bgu_df = bgu_df[bgu_df.index.isin(range(6, 23))]  # 6 to 22 inclusive
bgu_df = filter_and_reweight(bgu_df)

soroka_df = soroka_df[soroka_df.index.isin(range(6, 23))]
soroka_df = filter_and_reweight(soroka_df)

# Verify the results
print("BGU distribution (should sum to 1):", bgu_df.sum())
print("Soroka distribution (should sum to 1):", soroka_df.sum())
print(bgu_df)
print(soroka_df)