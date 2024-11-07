# dash-preprocess.py

import pandas as pd
import geopandas as gpd
import os
import numpy as np
import json
import datetime

# File paths (must be changed to the actual paths on your local machine)
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, 'data')
excel_file = os.path.join(data_dir, 'All-Stages.xlsx')
gdb_file = os.path.join(data_dir, 'statisticalareas_demography2019.gdb')
output_dir = os.path.join(base_dir, 'output', 'dashboard_data')
os.makedirs(output_dir, exist_ok=True)

poi_file = os.path.join(data_dir, "poi_with_exact_coordinates.csv")

def clean_and_pad(value):
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

print("Preprocessing data...")
df['from_tract'] = df['from_tract'].apply(clean_and_pad)
df['to_tract'] = df['to_tract'].apply(clean_and_pad)
zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].apply(clean_and_pad)

# Create a dictionary to map POI tracts to names
poi_names = dict(zip(poi_df['tract'].astype(str), poi_df['name']))

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
    poi_id_padded = clean_and_pad(poi_id)
    print(f"\nProcessing {trip_type} trips for POI: {poi_name} (ID: {poi_id_padded})")
    
    if trip_type == 'inbound':
        poi_trips = df[df['to_tract'] == poi_id_padded].copy()
        origin_column = 'from_tract'
    else:  # outbound
        poi_trips = df[df['from_tract'] == poi_id_padded].copy()
        origin_column = 'to_tract'
    
    num_trip_types = len(poi_trips)
    num_unique_origins = poi_trips[origin_column].nunique()
    print(f"Number of trip types found: {num_trip_types}")
    print(f"Number of unique {'origin' if trip_type == 'inbound' else 'destination'} zones: {num_unique_origins}")
    
    # Convert time_bin to datetime
    poi_trips['time_bin'] = poi_trips['time_bin'].apply(parse_time)
    poi_trips = poi_trips.dropna(subset=['time_bin'])  # Remove rows with invalid time_bin
    
    # Calculate total trips and split into metro and outside
    total_trips = poi_trips['count'].sum()
    metro_trips = poi_trips[poi_trips['IC'] == False]
    outside_trips = poi_trips[poi_trips['IC'] == True]
    
    metro_trips_total = metro_trips['count'].sum()
    outside_trips_total = outside_trips['count'].sum()
    
    print(f"Total trips: {total_trips:.1f}")
    print(f"Metro trips: {metro_trips_total:.1f}, Outside trips: {outside_trips_total:.1f}")

    # Debug: Print unique values in each column
    for column in poi_trips.columns:
        print(f"\nUnique values in {column}:")
        print(poi_trips[column].unique())

    # Process metro trips
    metro_summary = metro_trips.groupby(origin_column).agg({
        'count': 'sum',
        'Frequency': lambda x: x.value_counts(normalize=True).to_dict(),
        'mode': lambda x: x.value_counts().to_dict(),
        'purpose': lambda x: x.value_counts().to_dict()
    }).reset_index()
    
    metro_summary.columns = ['tract', 'total_trips', 'frequency', 'mode', 'purpose']
    
    # Get unique frequency, mode, and purpose values
    frequency_values = poi_trips['Frequency'].unique()
    mode_values = poi_trips['mode'].unique()
    purpose_values = poi_trips['purpose'].unique()

    # Calculate percentages for frequency, modes, and purposes
    for column, values in zip(['frequency', 'mode', 'purpose'], [frequency_values, mode_values, purpose_values]):
        for value in values:
            metro_summary[f'{column}_{value.strip()}'] = metro_summary[column].apply(lambda x: x.get(value, 0) / sum(x.values()) * 100)

    # Calculate percentages for arrival times
    time_bins = sorted(poi_trips['time_bin'].unique())
    for time_bin in time_bins:
        col_name = f'arrival_{time_bin.strftime("%H:%M")}'
        time_counts = metro_trips[metro_trips['time_bin'] == time_bin].groupby(origin_column)['count'].sum()
        metro_summary[col_name] = metro_summary['tract'].map(time_counts).fillna(0) / metro_summary['total_trips'] * 100

    # Debug: Print sample of metro_summary
    print("\nSample of metro_summary:")
    print(metro_summary.head().to_string())

    # Process outside trips
    outside_summary = pd.DataFrame({
        'tract': ['0'],
        'total_trips': [outside_trips_total]
    })

    # Calculate percentages for frequency, modes, and purposes for outside trips
    for column, values in zip(['Frequency', 'mode', 'purpose'], [frequency_values, mode_values, purpose_values]):
        column_total = outside_trips[column].map(outside_trips['count']).sum()
        for value in values:
            count = outside_trips[outside_trips[column] == value]['count'].sum()
            outside_summary[f'{column.lower()}_{value.strip()}'] = (count / column_total * 100).round(2)

    # Calculate percentages for arrival times for outside trips
    for time_bin in time_bins:
        col_name = f'arrival_{time_bin.strftime("%H:%M")}'
        count = outside_trips[outside_trips['time_bin'] == time_bin]['count'].sum()
        outside_summary[col_name] = (count / outside_trips_total * 100).round(2)

    # Combine metro and outside summaries
    trip_summary = pd.concat([metro_summary, outside_summary], ignore_index=True)

    # Sort columns
    time_columns = [col for col in trip_summary.columns if col.startswith('arrival_')]
    sorted_time_columns = sorted(time_columns, key=lambda x: pd.to_datetime(x.split('_')[-1], format='%H:%M').time())
    column_order = ['tract', 'total_trips'] + \
                   [col for col in trip_summary.columns if col.startswith(('frequency_', 'mode_', 'purpose_'))] + \
                   sorted_time_columns
    trip_summary = trip_summary[column_order]

    # Replace NaN values with 0.0
    trip_summary = trip_summary.fillna(0.0)

    # Debug: Check for data issues
    print("\nChecking for data issues:")
    nan_columns = trip_summary.columns[trip_summary.isna().any()].tolist()
    zero_columns = trip_summary.columns[(trip_summary == 0).all()].tolist()
    hundred_columns = trip_summary.columns[(trip_summary == 100).all()].tolist()

    print(f"Columns with NaN values: {nan_columns}")
    print(f"Columns with all zero values: {zero_columns}")
    print(f"Columns with all 100 values: {hundred_columns}")

    # Print a sample of the processed data
    print("\nSample of processed data:")
    print(trip_summary.head().to_string())

    # Save total trips information
    trips_info = {
        'total_trips': total_trips,
        'metro_trips': metro_trips_total,
        'outside_trips': outside_trips_total,
        'num_trip_types': num_trip_types,
        'num_unique_origins': num_unique_origins
    }

    return trip_summary, trips_info

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

# Print sample outputs
print("\nSample outputs:")
sample_files = [f for f in os.listdir(output_dir) if f.endswith('_trips.csv')][:5]
for sample_file in sample_files:
    df_sample = pd.read_csv(os.path.join(output_dir, sample_file))
    print(f"\nSample from {sample_file}:")
    print(df_sample.head(3).to_string(index=False))

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
