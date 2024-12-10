import pydeck as pdk
import geopandas as gpd
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
from collections import defaultdict
from shapely.geometry import Point
import numpy as np
import json
import pandas as pd
from config import OUTPUT_DIR, BUILDINGS_FILE

# Constants
POI_INFO = {
    'BGU': {'color': [0, 255, 90, 200], 'lat': 31.2614375, 'lon': 34.7995625},
    'Gav Yam': {'color': [0, 191, 255, 200], 'lat': 31.2641875, 'lon': 34.8128125},
    'Soroka Hospital': {'color': [170, 0, 255, 200], 'lat': 31.2579375, 'lon': 34.8003125}
}

POI_ID_MAP = {
    7: 'BGU',
    12: 'Gav Yam',
    11: 'Soroka Hospital'
}

POI_RADIUS = 0.0018  # about 200 meters in decimal degrees

def load_temporal_distributions():
    """Load temporal distribution data for each POI"""
    distributions = {}
    file_patterns = {
        'BGU': 'ben_gurion_university_inbound_temporal.csv',
        'Gav Yam': 'gav_yam_high_tech_park_inbound_temporal.csv',
        'Soroka Hospital': 'soroka_medical_center_inbound_temporal.csv'
    }
    
    for poi_name, filename in file_patterns.items():
        file_path = os.path.join(OUTPUT_DIR, 'dashboard_data', filename)
        try:
            df = pd.read_csv(file_path)
            dist = df[(df['hour'] >= 6) & (df['hour'] <= 22)]['car_dist'].values
            dist = dist / dist.sum()
            distributions[poi_name] = dist
            print(f"Loaded distribution for {poi_name}: sum={dist.sum():.3f}")
        except Exception as e:
            print(f"Error loading distribution for {poi_name}: {e}")
            distributions[poi_name] = np.ones(17) / 17
    
    return distributions

def interpolate_color(t):
    """Enhanced color interpolation with cube root scaling"""
    t = np.cbrt(t)  # Apply cube root scaling for better distribution
    
    colors = {
        0.0: [20, 42, 120],   # Dark blue
        0.2: [40, 80, 180],   # Medium blue
        0.4: [65, 182, 196],  # Light blue
        0.6: [120, 200, 150], # Blue-green
        0.8: [200, 220, 100], # Yellow-green
        1.0: [255, 255, 0]    # Bright yellow
    }
    
    lower_t = max([k for k in colors.keys() if k <= t])
    upper_t = min([k for k in colors.keys() if k >= t])
    
    ratio = (t - lower_t) / (upper_t - lower_t) if upper_t != lower_t else 0
    brightness = 0.85  # Slightly brighter than original
    
    c1 = colors[lower_t]
    c2 = colors[upper_t]
    
    rgb = [
        min(255, int((c1[0] + (c2[0] - c1[0]) * ratio) * brightness)),
        min(255, int((c1[1] + (c2[1] - c1[1]) * ratio) * brightness)),
        min(255, int((c1[2] + (c2[2] - c1[2]) * ratio) * brightness))
    ]
    
    return rgb + [200]  # Fixed opacity for better visibility

def load_poi_data():
    """Load POI polygon data"""
    attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
    return attractions[attractions['ID'].isin([11, 12, 7])]

def create_hourly_segment_data(trips_data, hour, temporal_dist, poi_polygons):
    """Create segment data for a specific hour"""
    segments = defaultdict(float)
    
    for _, row in trips_data.iterrows():
        coords = list(row.geometry.coords)
        base_trips = row['num_trips']
        
        # Find destination POI
        end_point = Point(coords[-1])
        poi_name = None
        for idx, poi_polygon in poi_polygons.iterrows():
            if end_point.distance(poi_polygon.geometry) < POI_RADIUS:
                poi_name = POI_ID_MAP[int(poi_polygon['ID'])]
                break
        
        if not poi_name or poi_name not in temporal_dist:
            continue
        
        # Apply temporal distribution
        hour_index = hour - 6
        hour_factor = temporal_dist[poi_name][hour_index]
        adjusted_trips = base_trips * hour_factor
        
        # Create segments with trip count and POI info
        for i in range(len(coords) - 1):
            segment = (coords[i], coords[i + 1])
            segments[segment] += adjusted_trips
    
    return segments

def create_line_features(segments):
    """Convert segments to deck.gl line features"""
    features = []
    if not segments:
        return features
        
    max_trips = max(segments.values())
    
    for (start, end), trips in segments.items():
        trip_ratio = trips / max_trips
        color = interpolate_color(trip_ratio)
        
        features.append({
            "start": [start[0], start[1], 5],
            "end": [end[0], end[1], 5],
            "trips": int(trips),
            "color": color
        })
    
    return features

def create_line_layer(trips_data, bounds):
    """Create visualization data for all hours"""
    print("\nProcessing temporal line data...")
    
    # Load POI data
    poi_polygons = load_poi_data()
    
    # Load temporal distributions
    temporal_dist = load_temporal_distributions()
    all_line_data = {}
    max_trips_per_hour = {}
    total_trips = trips_data['num_trips'].sum()
    
    # Process each hour
    for hour in range(6, 23):
        print(f"\nProcessing hour {hour:02d}:00...")
        segments = create_hourly_segment_data(trips_data, hour, temporal_dist, poi_polygons)
        
        if segments:
            hour_trips = sum(segments.values())
            max_trips_per_hour[hour] = max(segments.values())
            
            line_features = create_line_features(segments)
            all_line_data[str(hour)] = line_features
            print(f"Hour {hour:02d}:00 - Generated {len(line_features)} segments with {hour_trips:.0f} trips")
    
    # Create initial view state
    initial_view_state = {
        'latitude': (bounds[1] + bounds[3]) / 2,
        'longitude': (bounds[0] + bounds[2]) / 2,
        'zoom': 12,
        'pitch': 45,
        'bearing': 0
    }
    
    # Create building layers
    building_layers = create_building_layer(bounds)
    
    # Prepare template data
    template_data = {
        'initial_view_state': initial_view_state,
        'total_trips': total_trips,
        'line_data': all_line_data,
        'temporal_stats': {
            str(hour): {
                'total_trips': sum(trip['trips'] for trip in data) if data else 0,
                'num_segments': len(data),
                'max_trips': max_trips_per_hour.get(hour, 0)
            } for hour, data in all_line_data.items()
        },
        'building_layers': building_layers
    }
    
    return template_data

def create_building_layer(bounds):
    """Create building layer with POI highlights"""
    # Load building data
    buildings_gdf = gpd.read_file(BUILDINGS_FILE)
    building_features = []
    
    # Load POI data
    poi_polygons = load_poi_data()
    
    # Process buildings and POIs
    for idx, building in buildings_gdf.iterrows():
        try:
            height = float(building.get('height', 20))
            color = [74, 80, 87, 160]  # Default color
            
            # Check POI intersections
            for poi_idx, poi_polygon in poi_polygons.iterrows():
                if building.geometry.intersects(poi_polygon.geometry):
                    poi_id = int(poi_polygon['ID'])
                    poi_name = POI_ID_MAP.get(poi_id)
                    if poi_name:
                        color = POI_INFO[poi_name]['color']
                        height = min(40, height * 2)
            
            building_features.append({
                "polygon": list(building.geometry.exterior.coords),
                "height": height,
                "color": color
            })
            
        except Exception as e:
            print(f"Skipping building: {e}")
            continue
    
    return building_features

def main():
    print("\nStarting temporal trip route visualization...")
    
    # Load and filter trips data
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    trips_data = gpd.read_file(file_path)
    bounds = (34.65, 31.15, 34.95, 31.35)
    trips_data = trips_data.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    print(f"Processing {len(trips_data)} routes after filtering")
    
    # Create visualization data
    template_data = create_line_layer(trips_data, bounds)
    
    # Generate HTML using template
    from line_roads_html import create_html_template
    html = create_html_template(template_data)
    
    # Save file
    output_path = os.path.join(OUTPUT_DIR, "temporal_trip_routes.html")
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"\nVisualization saved to: {output_path}")

if __name__ == "__main__":
    main()