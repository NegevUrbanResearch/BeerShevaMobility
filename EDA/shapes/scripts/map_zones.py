import geopandas as gpd
import folium

census_zone_path = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset/statisticalareas_demography2019.gdb'
census_zones = gpd.read_file(census_zone_path)

print(census_zones.head())
print(census_zones.columns)

# Create a base map centered on Beer Sheva's approximate coordinates
m = folium.Map(location=[31.2525, 34.7906], zoom_start=12)

# Add census zones to the map
for idx, row in census_zones.iterrows():
    # Convert the geometry to GeoJSON format
    geo_j = folium.GeoJson(
        row['geometry'].__geo_interface__,
        style_function=lambda x: {
            'fillColor': '#ffcb69',
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.5
        }
    )
    
    # Add a popup with the YISHUV_STAT11 label
    folium.Popup(str(row['YISHUV_STAT11'])).add_to(geo_j)
    geo_j.add_to(m)

# Save the map to an HTML file
m.save('census_zones_map.html')