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
        
        # Check if the geometry is a point or polygon
        if row.geometry.geom_type == 'Point':
            folium.Marker(
                location=[row.geometry.y, row.geometry.x],
                tooltip=tooltip_text
            ).add_to(m)
        elif row.geometry.geom_type in ['Polygon', 'MultiPolygon']:
            folium.GeoJson(
                row.geometry,
                tooltip=tooltip_text
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

# Load your shapefiles
points = gpd.read_file("shapes/data/entrances/Point Notes.shp")
polygons = gpd.read_file("shapes/data/entrances/Polygon Notes.shp")
attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
google_points = pd.read_excel("shapes/data/FINAL/FINAL.xlsx", sheet_name="final")

# Convert to GeoDataFrame
google_points_gdf = excel_to_geodataframe(google_points)

# Save as shapefile
output_dir = create_output_directory()
shapefile_path = os.path.join(output_dir, "google_points.shp")
google_points_gdf.to_file(shapefile_path)
print(f"Shapefile saved to {shapefile_path}")

# Visualize using our existing function
visualize_shapefile(google_points_gdf, "google_points_map")



print('visualizing')
# Visualize each shapefile

visualize_shapefile(points, "entrances_points")
visualize_shapefile(polygons, "entrances_polygons")
visualize_shapefile(attractions, "attractions")

print("Done")

#attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]
