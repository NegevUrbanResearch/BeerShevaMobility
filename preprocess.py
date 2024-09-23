import pandas as pd
import geopandas as gpd
import os
import folium
from shapely.geometry import Point, LineString
import random
import json
from datetime import datetime, time

# File paths (update these as needed)
base_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
excel_file = os.path.join(base_dir, 'All-Stages.xlsx')
gdb_file = os.path.join(base_dir, 'statisticalareas_demography2019.gdb')
poi_file = '/Users/noamgal/Downloads/POI-PlusCode.xlsx'
output_dir = os.path.join(base_dir, 'output')
os.makedirs(output_dir, exist_ok=True)

# Read the Excel files
print("Reading Excel files...")
df = pd.read_excel(excel_file, sheet_name='StageB1')
poi_df = pd.read_excel(poi_file)

# Print information about the DataFrame
print("\nDataFrame Info:")
print(df.info())

print("\nFirst few rows of the DataFrame:")
print(df.head())

print("\nUnique values in 'time_bin' column:")
print(df['time_bin'].unique())

# Read the GDB file
print("\nReading GDB file...")
gdf = gpd.read_file(gdb_file)

# Ensure the tract IDs are in the same format
df['from_tract'] = df['from_tract'].astype(str).str.split('.').str[0]
df['to_tract'] = df['to_tract'].astype(str).str.split('.').str[0]
gdf['STAT11'] = gdf['STAT11'].astype(str).str.split('.').str[0]

# Create dictionaries for mapping
city_name_col = 'SHEM_YISHUV'
city_code_col = 'SEMEL_YISHUV'
city_code_dict = dict(zip(gdf[city_name_col], gdf[city_code_col]))
poi_dict = dict(zip(poi_df['ID'].astype(str), poi_df['Name']))

# Function to get city code
def get_city_code(city_name):
    return city_code_dict.get(city_name, None)

# Replace tract numbers with POI names and add city codes
df['from_poi'] = df['from_tract'].map(poi_dict).fillna(df['from_tract'])
df['to_poi'] = df['to_tract'].map(poi_dict).fillna(df['to_tract'])
df['from_city_code'] = df['from_name'].apply(get_city_code)
df['to_city_code'] = df['to_name'].apply(get_city_code)

# Temporal data processing
print("\nProcessing time_bin column...")

def time_to_hour(x):
    if isinstance(x, time):
        return x.hour
    elif isinstance(x, (int, float)):
        return int(x * 24) % 24
    else:
        try:
            return int(float(x) * 24) % 24
        except:
            print(f"Unexpected value in time_bin: {x}")
            return None

df['time_bin'] = df['time_bin'].apply(time_to_hour)

print("Unique values in processed 'time_bin' column:")
print(df['time_bin'].unique())

df['is_frequent'] = df['Frequency'].str.contains('Frequent')

# Aggregate mobility data
mobility_agg = df.groupby(['to_city_code', 'time_bin', 'is_frequent', 'purpose', 'mode']).agg({
    'count': 'sum',
    'duration': 'mean',
    'IC': 'first'
}).reset_index()

# Merge GDF with aggregated mobility data
merged_gdf = gdf.merge(mobility_agg, left_on=city_code_col, right_on='to_city_code', how='left')

# Function to generate dummy coordinates around Beer Sheva
def get_dummy_coords():
    lat, lon = 31.2524, 34.7909
    offset = 0.05
    return Point(lon + random.uniform(-offset, offset), lat + random.uniform(-offset, offset))

# Create point geometries for POIs
poi_gdf = gpd.GeoDataFrame(poi_df, geometry=[get_dummy_coords() for _ in range(len(poi_df))])
poi_gdf = poi_gdf.set_crs(gdf.crs)

# Save the GeoDataFrames to GeoJSON
print("Saving data to GeoJSON...")
merged_gdf.to_file(os.path.join(output_dir, 'beer_sheva_areas_analysis.geojson'), driver="GeoJSON")
poi_gdf.to_file(os.path.join(output_dir, 'beer_sheva_poi_analysis.geojson'), driver="GeoJSON")

# Create Folium map with enhanced popup
print("Creating Folium map...")
m = folium.Map(location=[31.2524, 34.7909], zoom_start=11)

def style_function(feature):
    return {
        'fillColor': '#ffaf00',
        'color': 'black',
        'weight': 2,
        'fillOpacity': 0.7
    }

def highlight_function(feature):
    return {
        'fillColor': '#ff0000',
        'color': 'black',
        'weight': 3,
        'fillOpacity': 0.9
    }

# Create a custom popup with all data
def create_popup(feature):
    html = "<table>"
    for key, value in feature['properties'].items():
        html += f"<tr><th>{key}</th><td>{value}</td></tr>"
    html += "</table>"
    return folium.Popup(html)

folium.GeoJson(
    merged_gdf,
    style_function=style_function,
    highlight_function=highlight_function,
    tooltip=folium.GeoJsonTooltip(
        fields=['SHEM_YISHUV', 'count', 'duration', 'purpose', 'mode', 'time_bin', 'is_frequent'],
        aliases=['City', 'Count', 'Avg Duration', 'Purpose', 'Mode', 'Time', 'Frequent'],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
    ),
    popup=create_popup
).add_to(m)

for _, row in poi_gdf.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=row['Name'],
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)

# Save the map
m.save(os.path.join(output_dir, 'beer_sheva_mobility_map.html'))

# Prepare data for Kepler.gl
print("Preparing data for Kepler.gl...")
for poi in poi_df['Name']:
    inbound_trips = df[df['to_poi'] == poi].copy()
    outbound_trips = df[df['from_poi'] == poi].copy()
    
    inbound_trips.to_csv(os.path.join(output_dir, f'{poi}_inbound_trips.csv'), index=False)
    outbound_trips.to_csv(os.path.join(output_dir, f'{poi}_outbound_trips.csv'), index=False)

# Prepare data for connectivity map
print("Preparing data for connectivity map...")
connectivity_data = df.groupby(['from_poi', 'to_poi']).agg({
    'count': 'sum',
    'duration': 'mean'
}).reset_index()

connectivity_data.to_csv(os.path.join(output_dir, 'connectivity_data.csv'), index=False)

# Export clean shapefile with all necessary data
print("Exporting clean shapefile...")
merged_gdf.to_file(os.path.join(output_dir, 'beer_sheva_areas_with_data.shp'))

# Export raw data for interactive dashboard
print("Exporting raw data for interactive dashboard...")
df.to_csv(os.path.join(output_dir, 'raw_mobility_data.csv'), index=False)

# Prepare data for temporal analysis
print("Preparing data for temporal analysis...")
temporal_data = df.groupby(['time_bin', 'from_poi', 'to_poi']).agg({
    'count': 'sum',
    'duration': 'mean',
    'IC': 'first',
    'Frequency': 'first',
    'purpose': lambda x: ', '.join(set(x)),
    'mode': lambda x: ', '.join(set(x))
}).reset_index()

temporal_data.to_csv(os.path.join(output_dir, 'temporal_data.csv'), index=False)

print("Data preprocessing and export complete.")