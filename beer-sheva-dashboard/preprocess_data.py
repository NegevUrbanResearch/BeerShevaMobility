# dash-preprocess.py

import pandas as pd
import geopandas as gpd
import os
import numpy as np
import json
import datetime
from utils.zone_utils import (
    clean_zone_id, is_valid_zone_id, standardize_zone_ids,
    analyze_zone_ids, ZONE_FORMATS
)
from config import (
    BASE_DIR, DATA_DIR, PROCESSED_DIR, OUTPUT_DIR,
    POI_FILE, ZONES_WITH_CITIES_FILE, FINAL_ZONES_FILE, 
    FINAL_TRIPS_PATTERN, TRIPS_WITH_CITIES_FILE
)

# Replace all directory definitions with config paths
print(f"Using paths:")
print(f"Base directory: {BASE_DIR}")
print(f"Data directory: {DATA_DIR}")
print(f"Processed directory: {PROCESSED_DIR}")
print(f"Output directory: {OUTPUT_DIR}")

# Input files
excel_file = TRIPS_WITH_CITIES_FILE
zones_file = ZONES_WITH_CITIES_FILE
poi_file = POI_FILE

print("Loading data...")
df = pd.read_excel(excel_file)
zones = gpd.read_file(zones_file)
poi_df = pd.read_csv(poi_file)

# Add after loading data
print("\nDiagnostic information:")
print("Sample from_tract values before cleaning:", df['from_tract'].head())
print("Sample to_tract values before cleaning:", df['to_tract'].head())
print("Sample YISHUV_STAT11 values before cleaning:", zones['YISHUV_STAT11'].head())

print(df.head())
print(zones.head())
print(poi_df.head())

print("Preprocessing data...")
# Apply consistent formatting to all zone IDs using the utility function
df = standardize_zone_ids(df, ['from_tract', 'to_tract'])
zones = standardize_zone_ids(zones, ['YISHUV_STAT11'])

# Add validation to check the different types of zones
def validate_zone_types(df, zones):
    """Validate that we have proper formatting for each zone type"""
    print("\nZone type validation (sample):")
    
    # First check individual zone IDs
    invalid_trips = [(col, val) for col in ['from_tract', 'to_tract'] 
                    for val in df[col].unique() 
                    if not is_valid_zone_id(val)]
    
    invalid_zones = [(val) for val in zones['YISHUV_STAT11'].unique() 
                    if not is_valid_zone_id(val)]
    
    if invalid_trips:
        print("\nWARNING: Invalid zone IDs found in trips data:")
        for col, val in invalid_trips:
            print(f"{col}: {val}")
    
    if invalid_zones:
        print("\nWARNING: Invalid zone IDs found in zones data:")
        for val in invalid_zones:
            print(val)
    
    # Then analyze zone types distribution
    trip_validation = analyze_zone_ids(df, ['from_tract', 'to_tract'])
    print("\nTrip data zones:")
    print(f"City zones: {trip_validation['city']}")
    print(f"Statistical areas: {trip_validation['statistical']}")
    print(f"POI zones: {trip_validation['poi']}")
    print(f"Unknown: {trip_validation['unknown']}")
    
    # Validate GeoJSON zones
    geo_validation = analyze_zone_ids(zones, ['YISHUV_STAT11'])
    print("\nGeoJSON zones:")
    print(f"City zones: {geo_validation['city']}")
    print(f"Statistical areas: {geo_validation['statistical']}")
    print(f"Unknown: {geo_validation['unknown']}")

# Run validation
validate_zone_types(df, zones)

# Create a dictionary to map POI tracts to names (with proper formatting)
poi_names = {
    clean_zone_id(str(tract)): name 
    for tract, name in zip(poi_df['tract'].astype(str), poi_df['name'])
}

print("\nSample of formatted POI IDs:")
print(list(poi_names.keys())[:5])

def parse_time(time_str):
    try:
        # Try parsing as HH:MM:SS
        return pd.to_datetime(time_str, format='%H:%M:%S').time()
    except ValueError:
        try:
            # Try parsing as float (assuming it's fraction of a day)
            hours = float(time_str) * 24
            return pd.to_datetime(f"{int(hours):02d}:{int(hours % 1 * 60):02d}:00").time()
        except ValueError:
            # If all else fails, return None
            return None

def process_poi_trips(poi_id, poi_name, trip_type):
    """Process trips for a specific POI"""
    poi_id_padded = clean_zone_id(str(poi_id).zfill(8))
    print(f"\nProcessing {trip_type} trips for POI: {poi_name} (ID: {poi_id_padded})")
    
    # Get relevant trips
    if trip_type == 'inbound':
        poi_trips = df[df['to_tract'] == poi_id_padded].copy()
        tract_column = 'from_tract'
    else:  # outbound
        poi_trips = df[df['from_tract'] == poi_id_padded].copy()
        tract_column = 'to_tract'
    
    if len(poi_trips) == 0:
        print(f"No {trip_type} trips found for this POI")
        return pd.DataFrame()

    # Group by tract and calculate total trips
    trip_summary = poi_trips.groupby(tract_column).agg({
        'count': 'sum'
    }).reset_index()
    
    # Rename columns consistently
    trip_summary = trip_summary.rename(columns={
        tract_column: 'tract',
        'count': 'total_trips'
    })
    
    # Calculate mode percentages correctly
    mode_columns = ['mode']
    for mode in poi_trips['mode'].unique():
        mode_trips = poi_trips[poi_trips['mode'] == mode].groupby(tract_column)['count'].sum()
        trip_summary[f'mode_{mode.strip().lower()}'] = trip_summary['tract'].map(mode_trips).fillna(0)
        # Convert to percentage of total trips for that tract
        trip_summary[f'mode_{mode.strip().lower()}'] = (
            trip_summary[f'mode_{mode.strip().lower()}'] / trip_summary['total_trips'] * 100
        )
    
    # Similarly for frequency and purpose
    for category in ['Frequency', 'purpose']:
        for value in poi_trips[category].unique():
            cat_trips = poi_trips[poi_trips[category] == value].groupby(tract_column)['count'].sum()
            col_name = f'{category.lower()}_{value.strip()}'
            trip_summary[col_name] = trip_summary['tract'].map(cat_trips).fillna(0)
            trip_summary[col_name] = (
                trip_summary[col_name] / trip_summary['total_trips'] * 100
            )
    
    # Handle time bins
    for hour in range(24):
        time_str = f"{hour:02d}:00"
        time_trips = poi_trips[poi_trips['time_bin'] == time_str].groupby(tract_column)['count'].sum()
        col_name = f'arrival_{time_str}'
        trip_summary[col_name] = trip_summary['tract'].map(time_trips).fillna(0)
        trip_summary[col_name] = (
            trip_summary[col_name] / trip_summary['total_trips'] * 100
        )
    
    # Verify that mode percentages sum to 100% for each tract
    mode_cols = [col for col in trip_summary.columns if col.startswith('mode_')]
    mode_sums = trip_summary[mode_cols].sum(axis=1)
    if not all(abs(mode_sums - 100) < 0.01):
        print(f"WARNING: Mode percentages don't sum to 100% for some tracts in {poi_name}")
        print("Sample problematic tracts:")
        print(trip_summary[abs(mode_sums - 100) > 0.01][['tract'] + mode_cols])
    
    return trip_summary

# Process all POIs
processed_files = 0
for poi_id, poi_name in poi_names.items():
    for trip_type in ['inbound', 'outbound']:
        trip_summary = process_poi_trips(poi_id, poi_name, trip_type)
        if not trip_summary.empty:
            output_file = os.path.join(OUTPUT_DIR, f"{poi_name.replace(' ', '_')}_{trip_type}_trips.csv")
            trip_summary.to_csv(output_file, index=False)
            processed_files += 1
            print(f"Processed {trip_type} data saved for {poi_name}")

print(f"\nPreprocessing complete. Processed {processed_files} files.")

# Print sample outputs
print("\nSample outputs:")
sample_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('_trips.csv')][:5]
for sample_file in sample_files:
    df_sample = pd.read_csv(os.path.join(OUTPUT_DIR, sample_file))
    print(f"\nSample from {sample_file}:")
    print(df_sample.head(3).to_string(index=False))

print("\nUnique from_tract values:")
# Add this debug print to see the unique tract values in the dataframe
print("\nUnique from_tract values:")
print(df['from_tract'].unique())
print("\nUnique to_tract values:")
print(df['to_tract'].unique())

# Save zones for later use
zones.to_file(os.path.join(OUTPUT_DIR, "zones.geojson"), driver="GeoJSON")
print("Zones data saved as GeoJSON.")

print("All POI data has been processed and saved in the output directory.")

# Add a comment about percentages at the end of the file
print("Note: All columns except 'tract' and 'total_trips' represent percentages.")

print("\nAfter cleaning:")
print("Sample from_tract values after cleaning:", df['from_tract'].head())
print("Sample to_tract values after cleaning:", df['to_tract'].head())
print("Sample YISHUV_STAT11 values after cleaning:", zones['YISHUV_STAT11'].head())

# After preprocessing, before saving
print("\nVerifying data format before save:")
print("Trip data from_tract format:", df['from_tract'].head())
print("Trip data to_tract format:", df['to_tract'].head())
print("Zones YISHUV_STAT11 format:", zones['YISHUV_STAT11'].head())

# When saving the data
# Save zones with proper format
zones = standardize_zone_ids(zones, ['YISHUV_STAT11'])
zones.to_file(FINAL_ZONES_FILE, driver='GeoJSON')

# Save trip data with proper format
df = standardize_zone_ids(df, ['from_tract', 'to_tract'])
output_file = os.path.join(OUTPUT_DIR, f'{poi_name}_{trip_type}_trips.csv')
df.to_csv(output_file, index=False)
#