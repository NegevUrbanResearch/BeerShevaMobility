import pandas as pd
import geopandas as gpd
import os

# File paths
base_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
excel_file = os.path.join(base_dir, 'All-Stages.xlsx')
gdb_file = os.path.join(base_dir, 'statisticalareas_demography2019.gdb')
poi_file = os.path.join(base_dir, 'output/poi_with_approximate_coordinates.csv')
output_dir = os.path.join(base_dir, 'output', 'processed_poi_data')
os.makedirs(output_dir, exist_ok=True)

# POI tract codes and names
poi_dict = {
    '1': 'Emek Shara industrial area',
    '2': 'BGU',
    '3': 'Soroka Hospital',
    '4': 'Yes Planet',
    '5': 'Grand Kenyon',
    '6': 'Omer industrial area',
    '7': 'K collage',
    '8': 'HaNegev Mall',
    '9': 'BIG',
    '10': 'Assuta Hospital',
    '11': 'Gev Yam',
    '12': 'Ramat Hovav Industry',
    '13': 'Sami Shimon collage'
}

print("Loading data...")
df = pd.read_excel(excel_file, sheet_name='StageB1')
zones = gpd.read_file(gdb_file)
poi_df = pd.read_csv(poi_file)

print(zones.columns)

print(f"Number of zones loaded: {len(zones)}")
print(f"CRS of zones: {zones.crs}")
print(f"Columns in zones: {zones.columns.tolist()}")
print(f"Columns in df: {df.columns.tolist()}")

print("\nPreprocessing data...")

# Clean and pad function
def clean_and_pad(value):
    if pd.isna(value):
        return '000000'
    try:
        return f"{int(float(value)):06d}"
    except ValueError:
        return '000000'

# Apply clean_and_pad to relevant columns
df['from_tract'] = df['from_tract'].apply(clean_and_pad)
df['to_tract'] = df['to_tract'].apply(clean_and_pad)
zones['STAT11'] = zones['STAT11'].apply(clean_and_pad)

# Convert zones to WGS84 for Folium
zones = zones.to_crs(epsg=4326)

def process_poi(poi_tract, poi_name):
    print(f"\nProcessing POI: {poi_name} (Tract: {poi_tract})")
    
    # Filter trips to this POI
    poi_trips = df[df['to_tract'] == clean_and_pad(poi_tract)]
    
    # Mark outside trips with '000000' instead of filtering them out
    poi_trips.loc[(poi_trips['IC'] == True) | (poi_trips['from_tract'] == '0'), 'from_tract'] = '000000'
    
    # Calculate total trips and percentages
    total_trips = poi_trips.groupby('from_tract').agg({
        'count': 'sum',
        'Frequency': lambda x: (x == ' Frequent').mean() * 100,
        'mode': lambda x: (x == 'car').mean() * 100,
        'purpose': lambda x: (x == 'Work ').mean() * 100
    }).reset_index()
    
    total_trips.columns = ['from_tract', 'total_trips', 'percent_frequent', 'percent_car', 'percent_work']
    
    print("\nSample of processed data:")
    print(total_trips.head())
    print(f"Total trips to this POI: {total_trips['total_trips'].sum()}")
    
    return total_trips

# Process all POIs
processed_data = {}
for poi_tract, poi_name in poi_dict.items():
    data = process_poi(poi_tract, poi_name)
    if data is not None:
        processed_data[poi_name] = data
        # Save processed data
        output_file = os.path.join(output_dir, f"{poi_name.replace(' ', '_')}_processed_data.csv")
        data.to_csv(output_file, index=False)
        print(f"Processed data saved for {poi_name}")

print("All POI data has been processed and saved in the output directory.")

# Save zones for later use
try:
    zones.to_file(os.path.join(output_dir, "zones.geojson"), driver="GeoJSON")
    print("Zones data saved as GeoJSON.")
except AttributeError as e:
    print(f"Error saving zones data: {e}")
    print("Attempting to save zones data using an alternative method...")
    zones.to_file(os.path.join(output_dir, "zones.shp"))
    print("Zones data saved as Shapefile.")