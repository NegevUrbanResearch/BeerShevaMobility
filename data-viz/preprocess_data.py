# dash-preprocess.py

import pandas as pd
import geopandas as gpd
import os
import numpy as np
import json
import datetime
import matplotlib.pyplot as plt
from fuzzywuzzy import process  # Add this import at the top

# File paths (must be changed to the actual paths on your local machine)
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, 'data')
excel_file = os.path.join(data_dir, 'All-Stages.xlsx')
gdb_file = os.path.join(data_dir, 'statisticalareas_demography2019.gdb')
output_dir = os.path.join(base_dir, 'output', 'dashboard_data')
os.makedirs(output_dir, exist_ok=True)

poi_file = os.path.join(data_dir, "poi_with_exact_coordinates.csv")

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


def clean_and_pad(value):
    """Clean and pad zone IDs to 6 digits"""
    if pd.isna(value):
        return '000000'
    try:
        return f"{int(float(value)):06d}"
    except ValueError:
        return '000000'

print("Loading data...")
df = pd.read_excel(excel_file, sheet_name='StageB1')
zones = gpd.read_file(gdb_file)
poi_df = pd.read_csv(poi_file)


def create_city_name_mapping(zones_df, df):
    """Create a mapping of city names with fuzzy matching"""
    # Get unique city names from zones and normalize them
    zone_cities = zones_df['SHEM_YISHUV_ENGLISH'].unique()
    zone_cities = [str(city).upper().strip() for city in zone_cities if pd.notna(city)]
    
    # Get unique city names from the data
    data_cities = set()
    data_cities.update(df['from_name'].dropna().unique())
    data_cities.update(df['to_name'].dropna().unique())
    data_cities = [str(city).upper().strip() for city in data_cities]
    
    # Create mapping using fuzzy matching
    city_mapping = {}
    for city in data_cities:
        if city and not city.isdigit():  # Skip empty strings and numeric values
            match = process.extractOne(city, zone_cities)
            if match and match[1] >= 80:  # 80% similarity threshold
                city_mapping[city] = match[0]
    
    # Debug output
    print("\nFuzzy matching results:")
    print("Sample of matched cities:")
    for i, (orig, matched) in enumerate(city_mapping.items()):
        if i < 10:  # Show first 10 matches
            print(f"'{orig}' -> '{matched}'")
    
    # Create final mapping with IDs
    city_name_to_id = {}
    for orig_name, matched_name in city_mapping.items():
        city_idx = list(zone_cities).index(matched_name)
        city_name_to_id[orig_name] = f"C{city_idx:05d}"
    
    return city_name_to_id

# Update the tract processing
def process_tracts(df, city_name_to_id):
    """Process tracts with improved city matching"""
    def map_tract(row, column_name):
        if pd.isna(row[column_name]) or row[column_name] == 0:
            city_name = str(row[f'{column_name[:-6]}_name']).upper().strip()
            return city_name_to_id.get(city_name, '000000')
        return clean_and_pad(row[column_name])
    
    df['from_tract'] = df.apply(lambda row: map_tract(row, 'from_tract'), axis=1)
    df['to_tract'] = df.apply(lambda row: map_tract(row, 'to_tract'), axis=1)
    
    # Print statistics
    print("\nTract processing statistics:")
    print(f"City-prefixed from_tract: {df['from_tract'].str.startswith('C').sum()}")
    print(f"City-prefixed to_tract: {df['to_tract'].str.startswith('C').sum()}")
    
    return df

# Fix the division by zero in process_poi_trips
def safe_percentage(numerator, denominator):
    """Calculate percentage safely handling zero division"""
    if denominator == 0 or pd.isna(denominator):
        return 0.0
    return (numerator / denominator * 100).round(2)

def process_poi_trips(poi_id, poi_name, trip_type):
    poi_id_padded = clean_and_pad(poi_id)
    print(f"\nProcessing {trip_type} trips for POI: {poi_name} (ID: {poi_id_padded})")
    
    # Filter trips for this POI
    if trip_type == 'inbound':
        poi_trips = df[df['to_tract'] == poi_id_padded].copy()
        origin_column = 'from_tract'
    else:  # outbound
        poi_trips = df[df['from_tract'] == poi_id_padded].copy()
        origin_column = 'to_tract'
    
    if poi_trips.empty:
        print(f"No trips found for {poi_name} ({trip_type})")
        return pd.DataFrame(), {'total_trips': 0, 'zone_trips': 0, 'city_trips': 0}
    
    # Calculate statistics with zone/city split
    total_trips = poi_trips['count'].sum()
    zone_trips = poi_trips[~poi_trips[origin_column].str.startswith('C', na=False)]['count'].sum()
    city_trips = poi_trips[poi_trips[origin_column].str.startswith('C', na=False)]['count'].sum()
    
    print(f"\nTrip Summary:")
    print(f"Total trips: {total_trips:.1f}")
    print(f"├── Statistical Zone trips: {zone_trips:.1f}")
    print(f"└── City-level trips: {city_trips:.1f}")
    
    # Convert time_bin to datetime
    poi_trips['time_bin'] = poi_trips['time_bin'].apply(parse_time)
    poi_trips = poi_trips.dropna(subset=['time_bin'])
    
    # Process metro trips (both zone and city)
    metro_trips = poi_trips[~poi_trips[origin_column].str.startswith('0', na=False)]
    metro_summary = metro_trips.groupby(origin_column).agg({
        'count': 'sum',
        'Frequency': lambda x: x.value_counts(normalize=True).to_dict(),
        'mode': lambda x: x.value_counts(normalize=True).to_dict(),
        'purpose': lambda x: x.value_counts(normalize=True).to_dict()
    }).reset_index()
    
    metro_summary.columns = ['tract', 'total_trips', 'frequency', 'mode', 'purpose']
    
    # Get unique values for categorical columns
    frequency_values = poi_trips['Frequency'].unique()
    mode_values = poi_trips['mode'].unique()
    purpose_values = poi_trips['purpose'].unique()
    
    # Calculate percentages for categorical columns
    for column, values in zip(['frequency', 'mode', 'purpose'], 
                            [frequency_values, mode_values, purpose_values]):
        for value in values:
            value_str = value.strip()
            metro_summary[f'{column}_{value_str}'] = metro_summary[column].apply(
                lambda x: x.get(value, 0) * 100)
    
    # Calculate time distributions
    time_bins = sorted(poi_trips['time_bin'].unique())
    for time_bin in time_bins:
        if time_bin and 7 <= time_bin.hour < 23:
            col_name = f'arrival_{time_bin.strftime("%H:%M")}'
            time_counts = metro_trips[metro_trips['time_bin'] == time_bin].groupby(origin_column)['count'].sum()
            metro_summary[col_name] = (metro_summary['tract'].map(time_counts).fillna(0) / 
                                     metro_summary['total_trips'] * 100)
    
    # Clean up and sort columns
    trip_summary = metro_summary.drop(columns=['frequency', 'mode', 'purpose'], errors='ignore')
    time_columns = [col for col in trip_summary.columns if col.startswith('arrival_')]
    sorted_time_columns = sorted(time_columns, 
                               key=lambda x: pd.to_datetime(x.split('_')[1], format='%H:%M').time())
    
    column_order = ['tract', 'total_trips'] + \
                  [col for col in trip_summary.columns if col.startswith(('frequency_', 'mode_', 'purpose_'))] + \
                  sorted_time_columns
    
    trip_summary = trip_summary[column_order].fillna(0.0)
    
    return trip_summary, {
        'total_trips': total_trips,
        'zone_trips': zone_trips,
        'city_trips': city_trips
    }

# Create city mapping
city_name_to_id = create_city_name_mapping(zones, df)

# Process tracts
df = process_tracts(df, city_name_to_id)

# Create a dictionary to map POI tracts to names
poi_names = dict(zip(poi_df['tract'].astype(str), poi_df['name']))

# Process all POIs
processed_files = 0
for poi_id, poi_name in poi_names.items():
    for trip_type in ['inbound', 'outbound']:
        data, trips_info = process_poi_trips(poi_id, poi_name, trip_type)
        if not data.empty:
            output_file = os.path.join(output_dir, f"{poi_name.replace(' ', '_')}_{trip_type}_trips.csv")
            data.to_csv(output_file, index=False)
            # Save trips info
            trips_info_file = os.path.join(output_dir, f"{poi_name.replace(' ', '_')}_{trip_type}_trips_info.csv")
            pd.DataFrame([trips_info]).to_csv(trips_info_file, index=False)
            processed_files += 1
            print(f"Processed {trip_type} data saved for {poi_name}")

print(f"\nPreprocessing complete. Processed {processed_files} files.")


print("\nUnique from_tract values:")
# Add this debug print to see the unique tract values in the dataframe
print("\nUnique from_tract values:")
print(df['from_tract'].unique())
print("\nUnique to_tract values:")
print(df['to_tract'].unique())

# Save zones for later use
zones.to_file(os.path.join(output_dir, "zones.geojson"), driver="GeoJSON")
print("Zones data saved as GeoJSON.")

print("All POI data has been processed and saved in the output directory.")

# Add a comment about percentages at the end of the file
print("Note: All columns except 'tract' and 'total_trips' represent percentages.")

# After processing tracts, add this new code:
def get_polygon_info(geom):
    """Helper function to get info about polygon/multipolygon geometries"""
    if geom.geom_type == 'Polygon':
        return len(geom.exterior.coords), 1
    elif geom.geom_type == 'MultiPolygon':
        total_vertices = sum(len(poly.exterior.coords) for poly in geom.geoms)
        return total_vertices, len(geom.geoms)
    return 0, 0

def validate_and_save_geometries():
    # Get unique tract IDs from trips data (both from and to)
    active_tracts = set(df['from_tract'].unique()) | set(df['to_tract'].unique())
    active_tracts.discard('000000')  # Remove null tract
    
    # Separate city and statistical zone IDs
    city_ids = {t for t in active_tracts if t.startswith('C')}
    stat_ids = {t for t in active_tracts if t.isdigit()}
    
    print(f"\nActive areas in trip data:")
    print(f"Cities: {len(city_ids)}")
    print(f"Statistical Zones: {len(stat_ids)}")
    
    # Print some examples of the IDs we're looking for
    print("\nExample city IDs:", list(city_ids)[:5])
    print("Example statistical zone IDs:", list(stat_ids)[:5])
    
    # Create statistical zones dataset
    stat_zones = zones[zones['YISHUV_STAT11'].notna()].copy()
    stat_zones = stat_zones[['YISHUV_STAT11', 'SEMEL_YISHUV', 'geometry']].copy()
    stat_zones['YISHUV_STAT11'] = stat_zones['YISHUV_STAT11'].astype(str)
    
    # Print some examples of what we have in the data
    print("\nExample YISHUV_STAT11 values in zones data:", stat_zones['YISHUV_STAT11'].head().tolist())
    print("Example SEMEL_YISHUV values in zones data:", stat_zones['SEMEL_YISHUV'].head().tolist())
    
    # Filter for active statistical zones
    stat_zones = stat_zones[stat_zones['YISHUV_STAT11'].isin(stat_ids)]
    stat_zones = stat_zones.dropna(subset=['geometry'])
    
    # Validate and clean statistical zone geometries
    stat_zones['geometry'] = stat_zones['geometry'].make_valid()
    stat_zones = stat_zones[stat_zones['geometry'].is_valid]
    
    # Create cities dataset
    city_zones = zones[zones['SEMEL_YISHUV'].notna()].copy()
    city_zones['city_id'] = city_zones.index.map(lambda x: f"C{x:05d}")
    city_zones = city_zones[['city_id', 'SHEM_YISHUV_ENGLISH', 'geometry']].copy()
    
    # Filter for active cities
    city_zones = city_zones[city_zones['city_id'].isin(city_ids)]
    city_zones = city_zones.dropna(subset=['geometry'])
    
    # Validate and clean city geometries
    city_zones['geometry'] = city_zones['geometry'].make_valid()
    city_zones = city_zones[city_zones['geometry'].is_valid]
    
    print(f"\nProcessed geometries:")
    print(f"Statistical Zones: {len(stat_zones)}")
    print(f"Cities: {len(city_zones)}")
    
    # Only save if we have data
    if len(city_zones) > 0:
        city_zones.to_file(
            os.path.join(output_dir, "city_zones.geojson"), 
            driver="GeoJSON"
        )
        print("Saved city zones to GeoJSON")
        
        # Print sample city data if available
        sample_city = city_zones.iloc[0]
        print("\n1. City Zones (city_zones.geojson):")
        vertices, parts = get_polygon_info(sample_city['geometry'])
        print(f"- city_id: {sample_city['city_id']} (format: C##### - unique identifier)")
        print(f"- SHEM_YISHUV_ENGLISH: {sample_city['SHEM_YISHUV_ENGLISH']} (city name)")
        print(f"- geometry: {sample_city['geometry'].geom_type} with {vertices} vertices in {parts} part(s)")
    else:
        print("\nWarning: No matching city geometries found!")
        print("Available city IDs in trips:", sorted(list(city_ids))[:10], "...")
    
    if len(stat_zones) > 0:
        stat_zones[['YISHUV_STAT11', 'geometry']].to_file(
            os.path.join(output_dir, "statistical_zones.geojson"), 
            driver="GeoJSON"
        )
        print("Saved statistical zones to GeoJSON")
        
        # Print sample statistical zone data if available
        sample_stat = stat_zones.iloc[0]
        print("\n2. Statistical Zones (statistical_zones.geojson):")
        vertices, parts = get_polygon_info(sample_stat['geometry'])
        print(f"- YISHUV_STAT11: {sample_stat['YISHUV_STAT11']} (format: ###### - combined city and zone code)")
        print(f"- geometry: {sample_stat['geometry'].geom_type} with {vertices} vertices in {parts} part(s)")
    else:
        print("\nWarning: No matching statistical zone geometries found!")
        print("Available statistical zone IDs in trips:", sorted(list(stat_ids))[:10], "...")
    
    return city_zones, stat_zones

# Add this call after processing the POIs
city_zones, stat_zones = validate_and_save_geometries()
