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


def calculate_global_statistics(all_segments):
    """Calculate global statistics for consistent color scaling"""
    all_trips = []
    for hour_segments in all_segments.values():
        all_trips.extend(hour_segments.values())
    
    all_trips = np.array(all_trips)
    global_mean = np.mean(all_trips)
    global_std = np.std(all_trips)
    global_max = np.max(all_trips)
    
    # Create logarithmic bins
    lower_bins = np.logspace(0, np.log10(global_mean), num=5)
    upper_bins = np.logspace(np.log10(global_mean), np.log10(global_max), num=3)
    bins = np.unique(np.concatenate([lower_bins, upper_bins]))
    
    return global_mean, global_std, global_max, bins

def get_color_for_value(value, global_stats):
    """Get color for a value based on global statistics"""
    global_mean, global_std, global_max, bins = global_stats
    
    # Color scale definition
    colors = {
        0.0: [10, 20, 90],     # Dark blue for very low values
        0.2: [65, 105, 225],   # Royal blue for low values
        0.4: [30, 144, 255],   # Dodger blue for below average
        0.6: [0, 191, 255],    # Deep sky blue for average
        0.8: [255, 215, 0],    # Gold for high values
        1.0: [255, 69, 0]      # Red-orange for very high values
    }
    
    # Find which bin the value falls into
    bin_index = np.digitize(value, bins) - 1
    position = bin_index / (len(bins) - 1)
    
    # Apply sigmoid transformation for better contrast
    position = 1 / (1 + np.exp(-4 * (position - 0.5)))
    
    # Get color positions
    color_positions = sorted(colors.keys())
    
    # Find appropriate color interval
    for i in range(len(color_positions) - 1):
        if position <= color_positions[i + 1]:
            lower_pos = color_positions[i]
            upper_pos = color_positions[i + 1]
            lower_color = colors[lower_pos]
            upper_color = colors[upper_pos]
            
            # Interpolate color
            factor = (position - lower_pos) / (upper_pos - lower_pos)
            color = [
                int(lower_color[0] + (upper_color[0] - lower_color[0]) * factor),
                int(lower_color[1] + (upper_color[1] - lower_color[1]) * factor),
                int(lower_color[2] + (upper_color[2] - lower_color[2]) * factor)
            ]
            
            return color + [200]  # Add alpha channel
    
    return colors[1.0] + [200]

def create_line_layer(trips_data, bounds):
    """Create visualization data for all hours with enhanced color scaling"""
    print("\nProcessing temporal line data...")
    
    # Load POI data and temporal distributions
    poi_polygons = load_poi_data()
    temporal_dist = load_temporal_distributions()
    
    # First pass: collect all segment data
    all_segments = {}
    total_trips = trips_data['num_trips'].sum()
    
    for hour in range(6, 23):
        print(f"\nCollecting data for hour {hour:02d}:00...")
        segments = create_hourly_segment_data(trips_data, hour, temporal_dist, poi_polygons)
        if segments:
            all_segments[hour] = segments
    
    # Calculate global statistics for consistent color scaling
    global_stats = calculate_global_statistics(all_segments)
    
    # Second pass: create features with consistent color scaling
    all_line_data = {}
    max_trips_per_hour = {}
    
    for hour, segments in all_segments.items():
        print(f"Processing visualization for hour {hour:02d}:00...")
        features = []
        
        # Calculate trips for this hour
        hour_trips = 0
        for _, row in trips_data.iterrows():
            # Find destination POI
            end_point = Point(list(row.geometry.coords)[-1])
            for _, poi_polygon in poi_polygons.iterrows():
                if end_point.distance(poi_polygon.geometry) < POI_RADIUS:
                    poi_name = POI_ID_MAP[int(poi_polygon['ID'])]
                    if poi_name in temporal_dist:
                        hour_trips += row['num_trips'] * temporal_dist[poi_name][hour-6]
                    break
        
        max_trips_per_hour[hour] = max(segments.values())
        
        for (start, end), trips in segments.items():
            color = get_color_for_value(trips, global_stats)
            
            features.append({
                "start": [start[0], start[1], 5],
                "end": [end[0], end[1], 5],
                "trips": int(trips),
                "color": color
            })
        
        all_line_data[str(hour)] = features
        print(f"Hour {hour:02d}:00 - Generated {len(features)} segments with {hour_trips:.0f} trips")
    
    # Create initial view state and building layers
    initial_view_state = {
        'latitude': (bounds[1] + bounds[3]) / 2,
        'longitude': (bounds[0] + bounds[2]) / 2,
        'zoom': 12,
        'pitch': 45,
        'bearing': 0
    }
    
    building_layers = create_building_layer(bounds)
    
    # Prepare color scale information for legend
    global_mean, global_std, global_max, bins = global_stats
    color_scale_info = {
        'min_value': int(bins[0]),
        'mean_value': int(global_mean),
        'max_value': int(global_max),
        'bin_edges': [int(b) for b in bins]
    }
    
    # Calculate temporal stats with correct trip counts
    temporal_stats = {}
    for hour, data in all_line_data.items():
        hour_int = int(hour)
        hour_trips = 0
        for _, row in trips_data.iterrows():
            end_point = Point(list(row.geometry.coords)[-1])
            for _, poi_polygon in poi_polygons.iterrows():
                if end_point.distance(poi_polygon.geometry) < POI_RADIUS:
                    poi_name = POI_ID_MAP[int(poi_polygon['ID'])]
                    if poi_name in temporal_dist:
                        hour_trips += row['num_trips'] * temporal_dist[poi_name][hour_int-6]
                    break
        
        temporal_stats[hour] = {
            'total_trips': int(hour_trips),
            'num_segments': len(data),
            'max_trips': max_trips_per_hour.get(hour_int, 0)
        }
    
    # Prepare template data
    template_data = {
        'initial_view_state': initial_view_state,
        'total_trips': total_trips,
        'line_data': all_line_data,
        'temporal_stats': temporal_stats,
        'building_layers': building_layers,
        'color_scale': color_scale_info
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