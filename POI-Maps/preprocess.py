import pandas as pd
import geopandas as gpd
import os

def clean_and_pad(value):
    if pd.isna(value):
        return '000000'
    try:
        return f"{int(float(value)):06d}"
    except ValueError:
        return '000000'

# File paths
base_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
excel_file = os.path.join(base_dir, 'All-Stages.xlsx')
gdb_file = os.path.join(base_dir, 'statisticalareas_demography2019.gdb')
output_dir = os.path.join(base_dir, 'output', 'processed_poi_data')
os.makedirs(output_dir, exist_ok=True)

# Exact path for POI coordinates file
poi_locations_file = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset/output/processed_poi_data/poi_with_exact_coordinates.csv'

print("Loading data...")
df = pd.read_excel(excel_file, sheet_name='StageB1')
zones = gpd.read_file(gdb_file)

print("Preprocessing data...")
df['from_tract'] = df['from_tract'].apply(clean_and_pad)
df['to_tract'] = df['to_tract'].apply(clean_and_pad)
zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].apply(clean_and_pad)
zones = zones.to_crs(epsg=4326)

print("Sample of preprocessed df:")
print(df.head())
print("\nUnique values in from_tract:", df['from_tract'].nunique())
print("Unique values in to_tract:", df['to_tract'].nunique())

# Load POI locations from the exact coordinates file
poi_locations_df = pd.read_csv(poi_locations_file)
poi_locations_df['ID'] = poi_locations_df['ID'].astype(str)
poi_locations = poi_locations_df.set_index('ID').to_dict('index')
print(f"Loaded {len(poi_locations)} POI coordinates")

def process_poi_trips(poi_id, poi_name, trip_type):
    poi_id_padded = clean_and_pad(poi_id)
    print(f"\nProcessing {trip_type} trips for POI: {poi_name} (ID: {poi_id_padded})")
    
    if trip_type == 'inbound':
        poi_trips = df[df['to_tract'] == poi_id_padded]
    else:  # outbound
        poi_trips = df[df['from_tract'] == poi_id_padded]
    
    print(f"Number of trips found: {len(poi_trips)}")
    print("Sample of poi_trips:")
    print(poi_trips.head())
    
    # Separate trips from outside the metro
    outside_trips = poi_trips[(poi_trips['IC'] == True) | (poi_trips['from_tract'] == '000000') | (poi_trips['to_tract'] == '000000')]
    metro_trips = poi_trips[~((poi_trips['IC'] == True) | (poi_trips['from_tract'] == '000000') | (poi_trips['to_tract'] == '000000'))]
    
    # Process metro trips
    group_col = 'from_tract' if trip_type == 'inbound' else 'to_tract'
    
    metro_summary = metro_trips.groupby(group_col).agg({
        'count': 'sum',
        'Frequency': lambda x: (x == ' Frequent').mean() * 100,
        'mode': lambda x: (x == 'car').mean() * 100,
        'purpose': lambda x: (x == 'Work ').mean() * 100
    }).reset_index()
    
    metro_summary.columns = ['tract', 'total_trips', 'percent_frequent', 'percent_car', 'percent_work']
    
    # Calculate total trips
    total_trips = poi_trips['count'].sum()
    metro_trips_total = metro_trips['count'].sum()
    outside_trips_total = outside_trips['count'].sum()
    
    print(f"Total trips: {total_trips}")
    print(f"Trips from/to Beer Sheva metro: {metro_trips_total}")
    print(f"Trips from/to outside metro: {outside_trips_total}")
    
    # Add a row for outside trips
    outside_row = pd.DataFrame({
        'tract': ['000000'],
        'total_trips': [outside_trips_total],
        'percent_frequent': [outside_trips['Frequency'].eq(' Frequent').mean() * 100],
        'percent_car': [outside_trips['mode'].eq('car').mean() * 100],
        'percent_work': [outside_trips['purpose'].eq('Work ').mean() * 100]
    })
    
    trip_summary = pd.concat([metro_summary, outside_row], ignore_index=True)
    
    # Save total trips information
    trips_info = {
        'total_trips': total_trips,
        'metro_trips': metro_trips_total,
        'outside_trips': outside_trips_total
    }
    
    return trip_summary, trips_info

# Process all POIs
for poi_id, poi_info in poi_locations.items():
    for trip_type in ['inbound', 'outbound']:
        data, trips_info = process_poi_trips(poi_id, poi_info['name'], trip_type)
        if data is not None:
            output_file = os.path.join(output_dir, f"{poi_info['name'].replace(' ', '_')}_{trip_type}_trips.csv")
            data.to_csv(output_file, index=False)
            
            # Save trips info
            trips_info_file = os.path.join(output_dir, f"{poi_info['name'].replace(' ', '_')}_{trip_type}_trips_info.csv")
            pd.DataFrame([trips_info]).to_csv(trips_info_file, index=False)
            
            print(f"Processed {trip_type} data saved for {poi_info['name']}")

# Add this debug print to see the unique tract values in the dataframe
print("\nUnique from_tract values:")
print(df['from_tract'].unique())
print("\nUnique to_tract values:")
print(df['to_tract'].unique())

# Save zones for later use
zones.to_file(os.path.join(output_dir, "zones.geojson"), driver="GeoJSON")
print("Zones data saved as GeoJSON.")

print("All POI data has been processed and saved in the output directory.")