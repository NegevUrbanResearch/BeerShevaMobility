import pandas as pd
import geopandas as gpd
import os
from datetime import datetime, time

def clean_and_pad(value):
    if pd.isna(value):
        return '000000'
    try:
        return f"{int(float(value)):06d}"
    except ValueError:
        return '000000'

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
            return None

def process_poi_trips(df, zones, poi_info, trip_type):
    poi_id = clean_and_pad(poi_info['tract'])
    print(f"\nProcessing {trip_type} trips for POI: {poi_info['name']} (ID: {poi_id})")
    
    # Filter trips based on trip type
    if trip_type == 'inbound':
        poi_trips = df[df['to_tract'] == poi_id].copy()
        origin_col = 'from_tract'
        dest_col = 'to_tract'
    else:  # outbound
        poi_trips = df[df['from_tract'] == poi_id].copy()
        origin_col = 'to_tract'
        dest_col = 'from_tract'
    
    # Convert time_bin to datetime
    poi_trips['time_bin'] = poi_trips['time_bin'].apply(parse_time)
    poi_trips = poi_trips.dropna(subset=['time_bin'])
    
    # Get centroids for zones
    zone_centroids = zones.copy()
    zone_centroids['centroid'] = zone_centroids.geometry.centroid
    zone_centroids['longitude'] = zone_centroids.centroid.x
    zone_centroids['latitude'] = zone_centroids.centroid.y
    
    # Create a dictionary for quick centroid lookup
    centroid_dict = zone_centroids.set_index('YISHUV_STAT11')[['latitude', 'longitude']].to_dict('index')
    
    # Add POI coordinates to centroid dictionary
    centroid_dict[poi_id] = {
        'latitude': poi_info['lat'],
        'longitude': poi_info['lon']
    }
    
    # Group by origin/destination and time bin, sum all trips
    grouped_trips = (poi_trips.groupby([origin_col, 'time_bin'])
                    .agg({'count': 'sum'})  # Sum all trips regardless of attributes
                    .reset_index())
    
    arc_data = []
    for _, trip in grouped_trips.iterrows():
        origin_tract = clean_and_pad(trip[origin_col])
        
        # Skip if we don't have coordinates
        if origin_tract not in centroid_dict or poi_id not in centroid_dict:
            continue
        
        # Get coordinates
        origin = centroid_dict[origin_tract]
        dest = centroid_dict[poi_id]
        
        # Format time for Kepler.gl
        time_str = trip['time_bin'].strftime('%H:%M')
        
        arc_data.append({
            'time': time_str,
            'origin_lat': origin['latitude'],
            'origin_lon': origin['longitude'],
            'dest_lat': dest['latitude'] if trip_type == 'inbound' else origin['latitude'],
            'dest_lon': dest['longitude'] if trip_type == 'inbound' else origin['longitude'],
            'trip_count': trip['count']  # Raw count without any filtering
        })
    
    # Convert to DataFrame and sort by time
    arc_df = pd.DataFrame(arc_data)
    arc_df = arc_df.sort_values('time')
    
    return arc_df

# File paths
base_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
excel_file = os.path.join(base_dir, 'All-Stages.xlsx')
gdb_file = os.path.join(base_dir, 'statisticalareas_demography2019.gdb')
poi_file = os.path.join(base_dir, 'output/processed_poi_data/poi_with_exact_coordinates.csv')
output_dir = os.path.join(base_dir, 'output', 'kepler_arc_data')
os.makedirs(output_dir, exist_ok=True)

# Load data
print("Loading data...")
df = pd.read_excel(excel_file, sheet_name='StageB1')
zones = gpd.read_file(gdb_file)
poi_df = pd.read_csv(poi_file)

# Preprocess data
print("Preprocessing data...")
df['from_tract'] = df['from_tract'].apply(clean_and_pad)
df['to_tract'] = df['to_tract'].apply(clean_and_pad)
zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].apply(clean_and_pad)
zones = zones.to_crs(epsg=4326)

# Process each POI
for _, poi in poi_df.iterrows():
    for trip_type in ['inbound', 'outbound']:
        arc_df = process_poi_trips(df, zones, poi, trip_type)
        
        if not arc_df.empty:
            output_file = os.path.join(output_dir, f"{poi['name'].replace(' ', '_')}_{trip_type}_arcs.csv")
            arc_df.to_csv(output_file, index=False)
            
            # Calculate and print total trips
            total_trips = arc_df['trip_count'].sum()
            total_time_bins = arc_df['time'].nunique()
            total_origins = arc_df[['origin_lat', 'origin_lon']].drop_duplicates().shape[0]
            
            print(f"\nStats for {poi['name']} ({trip_type}):")
            print(f"Total trips: {total_trips:,.0f}")
            print(f"Number of time bins: {total_time_bins}")
            print(f"Number of unique origins: {total_origins}")
            print(f"Average trips per time bin: {total_trips/total_time_bins:,.1f}")
            print("-" * 50)

print("\nAll POI arc data has been processed and saved in the output directory.")
