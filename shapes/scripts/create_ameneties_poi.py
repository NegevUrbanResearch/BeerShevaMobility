import geopandas as gpd
import folium
from shapely.ops import unary_union
import os
import pandas as pd

# Load the data
attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
google_points = gpd.read_file("shapes/data/output/google_points.shp")
entry_points = gpd.read_file("shapes/data/entrances/Point Notes.shp")

# Filter the data
poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]
entry_points = entry_points[~entry_points['Name'].str.startswith('Dorm')]


print(google_points['top_classi'].str.lower().str.startswith('parks').sum())

google_points = google_points[google_points['top_classi'].str.lower().str.startswith('parks')]


# Create a buffer of 0.5km (approximately 0.0045 degrees) around the polygons
buffer_union = unary_union(poi_polygons.geometry).buffer(0.0045)

# Filter points within buffer
points_within = google_points[google_points.geometry.within(buffer_union)]

# Create output directory if it doesn't exist
output_dir = "shapes/data/output"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Create the map
center_lat = poi_polygons.geometry.centroid.y.mean()
center_lon = poi_polygons.geometry.centroid.x.mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=14)

# Add polygons
for idx, row in poi_polygons.iterrows():
    # Create tooltip with first 5 columns
    tooltip_text = "<br>".join([f"{col}: {row[col]}" for col in poi_polygons.columns[:5]])
    
    folium.GeoJson(
        row.geometry,
        style_function=lambda x: {
            'fillColor': '#ff7800',
            'color': '#000000',
            'weight': 2,
            'fillOpacity': 0.35
        },
        tooltip=tooltip_text
    ).add_to(m)

# Add points within buffer
for idx, row in points_within.iterrows():
    # Create tooltip with first 5 columns
    tooltip_text = "<br>".join([f"{col}: {row[col]}" for col in points_within.columns[:5]])
    
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x],
        radius=5,
        color='blue',
        fill=True,
        popup=row['source'],
        tooltip=tooltip_text
    ).add_to(m)

# Add entry points with gate icon
for idx, row in entry_points.iterrows():
    # Create tooltip with first 5 columns
    tooltip_text = "<br>".join([f"{col}: {row[col]}" for col in entry_points.columns[:4]])
    
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        icon=folium.Icon(color='red', icon='door-open', prefix='fa'),
        popup=row['Name'],
        tooltip=tooltip_text
    ).add_to(m)

# Save the map
map_path = os.path.join(output_dir, "walking_amenities_poi.html")
m.save(map_path)
print(f"Map saved to {map_path}")

# Save as GeoDatabase with separate layers
gdb_path = os.path.join(output_dir, "walking_amenities_poi.gdb")

# Save each layer separately to the GeoDatabase
poi_polygons.to_file(gdb_path, layer='polygons', driver="FileGDB")
points_within.to_file(gdb_path, layer='points', driver="FileGDB")
entry_points.to_file(gdb_path, layer='entrances', driver="FileGDB")

print("GeoDatabase saved with three layers: polygons, points, and entrances")
