import pandas as pd
import geopandas as gpd
import os
import folium
from shapely.geometry import Point
import random

# File paths
base_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
excel_file = os.path.join(base_dir, 'All-Stages.xlsx')
gdb_file = os.path.join(base_dir, 'statisticalareas_demography2019.gdb')
poi_file = '/Users/noamgal/Downloads/POI-PlusCode.xlsx'
output_file = os.path.join(base_dir, 'mobility_census_comparison.txt')
output_areas_geojson = os.path.join(base_dir, 'beer_sheva_areas_analysis.geojson')
output_poi_geojson = os.path.join(base_dir, 'beer_sheva_poi_analysis.geojson')

# Function to print and write output
def output(message):
    print(message)
    with open(output_file, 'a') as f:
        f.write(message + '\n')

# Clear the output file if it exists
open(output_file, 'w').close()

# Read the Excel files
output("Reading Excel files...")
df = pd.read_excel(excel_file, sheet_name='StageB1')
poi_df = pd.read_excel(poi_file)

# Read the GDB file
output("Reading GDB file...")
gdf = gpd.read_file(gdb_file)

# Ensure the tract IDs are in the same format
df['from_tract'] = df['from_tract'].astype(str).str.split('.').str[0]
df['to_tract'] = df['to_tract'].astype(str).str.split('.').str[0]
gdf['STAT11'] = gdf['STAT11'].astype(str).str.split('.').str[0]

# Create a dictionary to map POI IDs to names
poi_dict = dict(zip(poi_df['ID'].astype(str), poi_df['Name']))

# Replace tract numbers with POI names in the mobility data
df['from_tract'] = df['from_tract'].map(poi_dict).fillna(df['from_tract'])
df['to_tract'] = df['to_tract'].map(poi_dict).fillna(df['to_tract'])

# Aggregate mobility data
mobility_agg = df.groupby('to_tract').agg({
    'count': 'sum',
    'duration': 'mean'
}).reset_index()

# Ensure 'to_tract' in mobility_agg is string type
mobility_agg['to_tract'] = mobility_agg['to_tract'].astype(str)

# Merge GDF with aggregated mobility data
merged_gdf = gdf.merge(mobility_agg, left_on='STAT11', right_on='to_tract', how='left')

# Function to generate dummy coordinates around Beer Sheva
def get_dummy_coords():
    lat = 31.2524
    lon = 34.7909
    offset = 0.05
    return Point(lon + random.uniform(-offset, offset), 
                 lat + random.uniform(-offset, offset))

# Create point geometries for POIs
poi_gdf = gpd.GeoDataFrame(poi_df, geometry=[get_dummy_coords() for _ in range(len(poi_df))])
poi_gdf = poi_gdf.set_crs(gdf.crs)

# Save the GeoDataFrames to GeoJSON
output("Saving data to GeoJSON...")
merged_gdf.to_file(output_areas_geojson, driver="GeoJSON")
poi_gdf.to_file(output_poi_geojson, driver="GeoJSON")

output(f"Analysis complete. Results saved to {output_file}")
output(f"Areas GeoDataFrame saved to {output_areas_geojson}")
output(f"POI GeoDataFrame saved to {output_poi_geojson}")

# Create Folium map
output("Creating Folium map...")
m = folium.Map(location=[31.2524, 34.7909], zoom_start=11)

# Add the areas GeoJSON to the map
folium.GeoJson(merged_gdf).add_to(m)

# Add POI markers
for _, row in poi_gdf.iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=row['Name'],
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)

# Save the map
map_output = os.path.join(base_dir, 'beer_sheva_mobility_map.html')
m.save(map_output)
output(f"Folium map saved to {map_output}")