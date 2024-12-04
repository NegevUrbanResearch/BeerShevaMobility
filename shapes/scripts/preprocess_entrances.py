import geopandas as gpd
import folium
import os
import pandas as pd
import numpy as np
from shapely.geometry import Point
from shapely.wkt import loads
from shapely.errors import GEOSException

def create_output_directory():
    output_dir = "shapes/data/output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return output_dir

def visualize_shapefile(gdf, filename):
    # Determine the center of the map
    center = gdf.geometry.unary_union.centroid.coords[0][::-1]
    
    # Create a folium map centered around the data
    m = folium.Map(location=center, zoom_start=13)
    
    # Add features to the map
    for _, row in gdf.iterrows():
        # Prepare tooltip text
        tooltip_text = "<br>".join([f"{col}: {row[col]}" for col in gdf.columns[:5]])
        
        # Determine color based on name prefix
        if row['Name'].startswith('Uni'):
            color = 'green'
        elif row['Name'].startswith('Hospital'):
            color = 'purple'
        else:
            color = 'blue'  # default color for other points
        
        # Check if the geometry is a point or polygon
        if row.geometry.geom_type == 'Point':
            folium.Marker(
                location=[row.geometry.y, row.geometry.x],
                tooltip=tooltip_text,
                icon=folium.Icon(color=color)
            ).add_to(m)
        elif row.geometry.geom_type in ['Polygon', 'MultiPolygon']:
            folium.GeoJson(
                row.geometry,
                tooltip=tooltip_text,
                style_function=lambda x: {'fillColor': color, 'color': color}
            ).add_to(m)
    
    # Save the map to an HTML file
    output_dir = create_output_directory()
    map_path = os.path.join(output_dir, f"{filename}.html")
    m.save(map_path)
    print(f"Map saved to {map_path}")

def excel_to_geodataframe(df):
    print(df.head())
    # Count total rows before filtering
    total_rows = len(df)
    
    # Remove rows with NaN in geometry
    df_clean = df.dropna(subset=['geometry'])
    
    def safe_convert_geometry(x):
        try:
            if isinstance(x, str):
                # Check if the string starts with 'POINT' before trying to convert
                if x.upper().startswith('POINT'):
                    return loads(x)
                else:
                    print(f"Invalid geometry string found: {x}")
                    return None
            return x
        except (GEOSException, ValueError) as e:
            print(f"Error converting geometry: {e}")
            return None
    
    # Convert geometry column and handle errors
    df_clean['geometry'] = df_clean['geometry'].apply(safe_convert_geometry)
    
    # Remove rows where geometry conversion failed
    df_clean = df_clean.dropna(subset=['geometry'])
    
    # Calculate and print statistics about dropped rows
    final_rows = len(df_clean)
    dropped_rows = total_rows - final_rows
    dropped_percentage = (dropped_rows / total_rows) * 100
    print(f"Dropped {dropped_rows} rows with invalid geometries ({dropped_percentage:.2f}% of total)")
    
    # Create GeoDataFrame using existing geometry column
    gdf = gpd.GeoDataFrame(df_clean, geometry='geometry', crs="EPSG:4326")
    print(gdf.head())
    return gdf

# Load your shapefile
points = gpd.read_file("shapes/data/entrances/Point Notes.shp")

# Convert coordinates from degrees/minutes/seconds to decimal degrees
new_lat = 31 + 15/60 + 45.0/3600  # 31°15'45.0"N
new_lon = 34 + 48/60 + 19.9/3600  # 34°48'19.9"E

# Create new point and add to GeoDataFrame
new_point = gpd.GeoDataFrame({
    'NoteType': [0],
    'Name': ['Uni_West'],
    'Notes': [''],
    'created_us': [''],
    'created_da': [''],
    'last_edite': [''],
    'last_edi_1': ['2024-11-07'],
    'geometry': [Point(new_lon, new_lat)]
}, crs="EPSG:4326")

# Combine with existing points
points = pd.concat([points, new_point], ignore_index=True)

# Filter for specific points
filtered_names = ['Hospital_North_1', 'Uni_South_3', 'Uni_North_3', 'Hospital_North_2',
                 'Hospital_West_1', 'Hospital_South_1', 'Hospital_East_1', 'Hospital_North_3',
                 'Uni_West']  # Include the new point in filtering
points = points[points['Name'].isin(filtered_names)]
points = points[['Name', 'geometry']]

# After filtering points and before visualization
output_dir = create_output_directory()

# Save the updated shapefile
output_shapefile = os.path.join(output_dir, "filtered_entrances.shp")
points.to_file(output_shapefile)
print(f"Updated shapefile saved to: {output_shapefile}")

print('visualizing')
# Visualize each shapefile
print(points.head())
print(points["Name"].unique())
print(points.columns)

visualize_shapefile(points, "entrances_points")

print("Done")

