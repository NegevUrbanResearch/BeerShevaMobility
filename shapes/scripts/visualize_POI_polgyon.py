import geopandas as gpd
import folium
import os

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

# Load your shapefiles
amenities_gdb = gpd.read_file("shapes/data/GDB/B7GDB.gdb")
points = gpd.read_file("shapes/data/entrances/Point Notes.shp")
polygons = gpd.read_file("shapes/data/entrances/Polygon Notes.shp")
combined = gpd.read_file("shapes/data/maps/combined_shapes.shp")
attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")

print(amenities_gdb.head())
print(points.head())
print(polygons.head())
print(combined.head())
print(attractions.head())

print('visualizing')
# Visualize each shapefile
visualize_shapefile(amenities_gdb, "amenities_gdb")
visualize_shapefile(points, "entrances_points")
visualize_shapefile(polygons, "entrances_polygons")
visualize_shapefile(combined, "combined_shapes")
visualize_shapefile(attractions, "attractions")

print("Done")