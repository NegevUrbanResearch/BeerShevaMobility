import geopandas as gpd
import folium
from folium.plugins import TimestampedGeoJson
import numpy as np
import os
from data_loader import DataLoader
from config import BASE_DIR, OUTPUT_DIR
import logging

logger = logging.getLogger(__name__)

def load_road_usage():
    file_path = os.path.join(OUTPUT_DIR, "road_usage.geojson")
    print(f"Loading road usage data from: {file_path}")
    road_usage = gpd.read_file(file_path)
    
    road_usage = road_usage[road_usage.geometry.notna()]
    road_usage = road_usage[road_usage.geometry.is_valid]
    
    if road_usage.crs is None or road_usage.crs.to_epsg() != 4326:
        road_usage = road_usage.to_crs(epsg=4326)
    
    return road_usage

def create_animated_map(road_usage):
    m = folium.Map(
        location=[31.2529, 34.7915],
        zoom_start=13,
        tiles='CartoDB dark_matter'
    )
    
    road_usage = road_usage[road_usage['count'] >= 1]
    
    features = []
    for _, row in road_usage.iterrows():
        if row.geometry is None or not row.geometry.is_valid:
            continue
        
        feature = {
            'type': 'Feature',
            'geometry': row.geometry.__geo_interface__,
            'properties': {
                'time': '2023-01-01T00:00:00',  # Example timestamp
                'style': {'color': 'blue', 'weight': 2},
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': 'blue',
                    'fillOpacity': 0.6,
                    'stroke': 'true',
                    'radius': 5
                }
            }
        }
        features.append(feature)
    
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': features},
        period='PT1H',  # Example period
        add_last_point=True,
        auto_play=True,
        loop=True
    ).add_to(m)
    
    return m

def main():
    print("\nStarting road usage visualization...")
    road_usage = load_road_usage()
    print(f"Processing {len(road_usage)} road segments")
    
    m = create_animated_map(road_usage)
    
    output_file = os.path.join(OUTPUT_DIR, "animated_road_usage.html")
    m.save(output_file)
    print(f"\nAnimated map saved to: {output_file}")

if __name__ == "__main__":
    main()
