import pandas as pd
import geopandas as gpd
import os
import requests
import time

def geocode_plus_code(plus_code):
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": plus_code,
        "key": "AIzaSyCaPaazlDYXSJIGFXuzjlhcAE1zt-cyQ8U"  # Replace with your Google Maps API key
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
    return None

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
poi_file = os.path.join(base_dir, 'POI-PlusCode.xlsx')
output_dir = os.path.join(base_dir, 'output', 'processed_poi_data')
os.makedirs(output_dir, exist_ok=True)

print("Loading data...")
df = pd.read_excel(excel_file, sheet_name='StageB1')
zones = gpd.read_file(gdb_file)
poi_df = pd.read_excel(poi_file)

print("Preprocessing data...")
df['from_tract'] = df['from_tract'].apply(clean_and_pad)
df['to_tract'] = df['to_tract'].apply(clean_and_pad)
zones['STAT11'] = zones['STAT11'].apply(clean_and_pad)
zones = zones.to_crs(epsg=4326)

print("Geocoding POI locations...")
poi_locations = {}
for _, row in poi_df.iterrows():
    plus_code = row['Plus-Code']
    if "Israel" not in plus_code:
        plus_code += " Israel"
    print(f"Processing POI: {row['Name']} (Plus Code: {plus_code})")
    
    location = geocode_plus_code(plus_code)
    if location:
        lat, lon = location
        poi_locations[str(row['ID'])] = {
            'name': row['Name'],
            'lat': lat,
            'lon': lon,
            'tract': clean_and_pad(row['ID'])
        }
        print(f"Successfully geocoded: {row['Name']}")
    else:
        print(f"Could not geocode Plus Code for {row['Name']}")
    
    time.sleep(0.5)  # Add a small delay between requests to avoid rate limiting

# Save POI locations with coordinates
poi_locations_df = pd.DataFrame.from_dict(poi_locations, orient='index')
poi_locations_df = poi_locations_df.reset_index().rename(columns={'index': 'ID'})
poi_locations_df['ID'] = poi_locations_df['ID'].astype(int)
poi_locations_df.to_csv(os.path.join(output_dir, 'poi_with_exact_coordinates.csv'), index=False)
print("POI locations with exact coordinates saved.")

def process_poi_trips(poi_tract, poi_name, trip_type):
    print(f"\nProcessing {trip_type} trips for POI: {poi_name} (Tract: {poi_tract})")
    
    if trip_type == 'inbound':
        poi_trips = df[df['to_tract'] == poi_tract]
    else:  # outbound
        poi_trips = df[df['from_tract'] == poi_tract]
    
    # Separate trips from outside the metro
    outside_trips = poi_trips[(poi_trips['IC'] == True) | (poi_trips['from_tract'] == '000000') | (poi_trips['to_tract'] == '000000')]
    metro_trips = poi_trips[~((poi_trips['IC'] == True) | (poi_trips['from_tract'] == '000000') | (poi_trips['to_tract'] == '000000'))]
    
    # Process metro trips
    if trip_type == 'inbound':
        group_col = 'from_tract'
    else:
        group_col = 'to_tract'
    
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
    
    return trip_summary

# Process all POIs
for poi_id, poi_info in poi_locations.items():
    for trip_type in ['inbound', 'outbound']:
        data = process_poi_trips(poi_info['tract'], poi_info['name'], trip_type)
        if data is not None:
            output_file = os.path.join(output_dir, f"{poi_info['name'].replace(' ', '_')}_{trip_type}_trips.csv")
            data.to_csv(output_file, index=False)
            print(f"Processed {trip_type} data saved for {poi_info['name']}")

# Save zones for later use
zones.to_file(os.path.join(output_dir, "zones.geojson"), driver="GeoJSON")
print("Zones data saved as GeoJSON.")

print("All POI data has been processed and saved in the output directory.")