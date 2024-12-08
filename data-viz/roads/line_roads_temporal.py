import pydeck as pdk
import geopandas as gpd
import os
import sys
import math
from collections import defaultdict
from shapely.ops import split, linemerge
from shapely.geometry import Point, MultiLineString
import numpy as np
from pyproj import Transformer
import json
from datetime import datetime
import pandas as pd
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR, MAPBOX_API_KEY, BUILDINGS_FILE, POI_LOCATIONS
from line_roads_html import create_html_description

# Constants and configurations
attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]

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
            # Filter to business hours and normalize
            dist = df[(df['hour'] >= 6) & (df['hour'] <= 22)]['car_dist'].values
            dist = dist / dist.sum()  # Normalize to ensure sum is 1.0
            distributions[poi_name] = dist
            print(f"Loaded distribution for {poi_name}: sum={dist.sum():.3f}")
        except Exception as e:
            print(f"Error loading distribution for {poi_name}: {e}")
            distributions[poi_name] = np.ones(17) / 17  # Uniform distribution as fallback
    
    return distributions

def load_road_usage():
    """Load the trips data"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    trips = gpd.read_file(file_path)
    print(f"Loaded {len(trips)} unique trip routes")
    return trips

def create_segment_data(trips_data, hour):
    """Break down routes into segments and aggregate trip counts for specific hour"""
    segments = defaultdict(float)
    temporal_dist = load_temporal_distributions()
    hour_index = hour - 6  # Convert to 0-based index for 6:00 start
    
    # Pre-calculate POI lookup for efficiency
    poi_lookup = {}
    for poi_idx, poi_polygon in poi_polygons.iterrows():
        poi_lookup[int(poi_polygon['ID'])] = POI_ID_MAP[int(poi_polygon['ID'])]
    
    for _, row in trips_data.iterrows():
        coords = list(row.geometry.coords)
        base_trips = row['num_trips']
        
        # Determine POI for this route
        dest_point = Point(coords[-1])
        poi_name = None
        for poi_idx, poi_polygon in poi_polygons.iterrows():
            if dest_point.distance(poi_polygon.geometry) < POI_RADIUS:
                poi_name = poi_lookup[int(poi_polygon['ID'])]
                break
        
        if not poi_name or poi_name not in temporal_dist:
            continue
            
        # Get temporal factor for this hour
        hour_factor = temporal_dist[poi_name][hour_index] if hour_index < len(temporal_dist[poi_name]) else 0
        num_trips = base_trips * hour_factor
        
        if num_trips < 0.1:  # Skip negligible contributions
            continue
            
        # Break down each route into segments
        for i in range(len(coords) - 1):
            segment = tuple(sorted([coords[i], coords[i + 1]]))
            segments[segment] += num_trips
    
    return segments

def interpolate_color(t, distance_ratio):
    """Enhanced color interpolation with smoother transitions"""
    t = np.cbrt(t)  # Apply cube root scaling
    
    colors = {
        0.0: [20, 42, 120],   # Dark blue
        0.2: [40, 80, 180],   # Medium blue
        0.4: [65, 182, 196],  # Light blue
        0.6: [120, 200, 150], # Blue-green
        0.8: [200, 220, 100], # Yellow-green
        1.0: [255, 255, 0]    # Bright yellow
    }
    
    # Find interpolation points
    lower_t = max([k for k in colors.keys() if k <= t])
    upper_t = min([k for k in colors.keys() if k >= t])
    
    # Smooth transition between colors
    ratio = (t - lower_t) / (upper_t - lower_t) if upper_t != lower_t else 0
    smoothing = math.exp(-4 * (distance_ratio - 0.5)**2)
    brightness = 0.7 + 0.3 * smoothing
    
    c1 = colors[lower_t]
    c2 = colors[upper_t]
    
    rgb = [
        min(255, int((c1[0] + (c2[0] - c1[0]) * ratio) * brightness)),
        min(255, int((c1[1] + (c2[1] - c1[1]) * ratio) * brightness)),
        min(255, int((c1[2] + (c2[2] - c1[2]) * ratio) * brightness))
    ]
    
    opacity = min(255, int(255 * (0.7 + 0.3 * smoothing)))
    return rgb + [opacity]

def create_line_segments(start_coord, end_coord, trip_count, trip_ratio):
    """Create line segments with smooth transitions"""
    segments = []
    segment_length = 1.995  # Slightly shorter to create gaps
    
    total_distance = math.sqrt(
        (end_coord[0] - start_coord[0])**2 + 
        (end_coord[1] - start_coord[1])**2
    )
    
    if total_distance == 0:
        return segments
    
    # Add small random variations for visual interest
    jitter = 0.00001
    random_offset = [
        (np.random.random() - 0.5) * jitter,
        (np.random.random() - 0.5) * jitter
    ]
    
    # Create segment with gaps
    start_pos = 0.01  # Small gap at start
    end_pos = 0.99   # Small gap at end
    
    start = [
        start_coord[0] + (end_coord[0] - start_coord[0]) * start_pos + random_offset[0],
        start_coord[1] + (end_coord[1] - start_coord[1]) * start_pos + random_offset[1],
        5
    ]
    
    end = [
        start_coord[0] + (end_coord[0] - start_coord[0]) * end_pos + random_offset[0],
        start_coord[1] + (end_coord[1] - start_coord[1]) * end_pos + random_offset[1],
        5
    ]
    
    color = interpolate_color(trip_ratio, 0.5)
    
    segments.append({
        "start": start,
        "end": end,
        "trips": int(trip_count),
        "color": color
    })
    
    return segments

def create_building_layer(bounds):
    """Create building layer with POI highlights"""
    buildings_gdf = gpd.read_file(BUILDINGS_FILE)
    building_features = []
    text_features = []
    poi_borders = []
    poi_fills = []
    
    # Process POI polygons
    for poi_idx, poi_polygon in poi_polygons.iterrows():
        numeric_id = int(poi_polygon['ID'])
        poi_name = POI_ID_MAP.get(numeric_id)
        
        if poi_name:
            color = POI_INFO[poi_name]['color'][:3]
            poi_borders.append({
                "polygon": list(poi_polygon.geometry.exterior.coords),
                "color": color + [255]
            })
            poi_fills.append({
                "polygon": list(poi_polygon.geometry.exterior.coords),
                "color": color + [100]
            })
    
    # Process buildings
    for idx, building in buildings_gdf.iterrows():
        building_color = [74, 80, 87, 160]  # Default color
        try:
            height = float(building.get('height', 20))
            building_height = height * 1.5
            
            # Check POI intersections
            for poi_idx, poi_polygon in poi_polygons.iterrows():
                if building.geometry.intersects(poi_polygon.geometry):
                    numeric_id = int(poi_polygon['ID'])
                    poi_name = POI_ID_MAP.get(numeric_id)
                    
                    if poi_name:
                        building_height = min(40, height * 1000)
                        building_color = POI_INFO[poi_name]['color']
                        
                        text_features.append({
                            "position": [*building.geometry.centroid.coords[0], building_height + 10],
                            "text": poi_name,
                            "color": [255, 255, 255, 255]
                        })
                        break
            
            building_features.append({
                "polygon": building.geometry.exterior.coords[:],
                "height": building_height,
                "color": building_color
            })
        except Exception as e:
            print(f"Skipping building due to error: {e}")
            continue
    
    # Create layers
    layers = [
        pdk.Layer(
            "PolygonLayer",
            poi_fills,
            get_polygon="polygon",
            get_fill_color="color",
            extruded=False,
            pickable=False,
            opacity=0.5
        ),
        pdk.Layer(
            "PolygonLayer",
            building_features,
            get_polygon="polygon",
            get_fill_color="color",
            get_elevation="height",
            elevation_scale=1,
            elevation_range=[0, 1000],
            pickable=True,
            extruded=True,
            wireframe=True,
            get_line_color=[255, 255, 255, 50],
            line_width_min_pixels=1,
            material={
                "ambient": 0.2,
                "diffuse": 0.8,
                "shininess": 32,
                "specularColor": [60, 64, 70]
            }
        ),
        pdk.Layer(
            "TextLayer",
            text_features,
            get_position="position",
            get_text="text",
            get_color="color",
            get_size=16,
            get_angle=0,
            get_text_anchor="middle",
            get_alignment_baseline="center"
        ),
        pdk.Layer(
            "PolygonLayer",
            poi_borders,
            get_polygon="polygon",
            get_line_color="color",
            line_width_min_pixels=2,
            extruded=False,
            pickable=False,
            opacity=1
        )
    ]
    
    return layers

def create_line_layer(trips_data, bounds):
    """Create animated temporal visualization"""
    print("\nProcessing temporal line data...")
    all_line_data = {}
    max_trips_per_hour = {}
    total_trips = 0
    
    # Process each hour
    for hour in range(6, 23):
        print(f"\nProcessing hour {hour:02d}:00...")
        segments = create_segment_data(trips_data, hour)
        
        if segments:
            hour_trips = sum(segments.values())
            max_trips_per_hour[hour] = max(segments.values())
            total_trips += hour_trips
            
            line_data = []
            max_trips = max(segments.values())
            
            for (start_coord, end_coord), trip_count in segments.items():
                trip_ratio = trip_count / max_trips
                line_data.extend(create_line_segments(
                    start_coord, end_coord, trip_count, trip_ratio))
            
            all_line_data[str(hour)] = line_data
            print(f"Hour {hour:02d}:00 - Generated {len(line_data)} segments with {hour_trips:.0f} trips")
    
    # Calculate thresholds
    overall_max = max(max_trips_per_hour.values())
    low_trips = int(overall_max * 0.2)
    med_trips = int(overall_max * 0.6)
    high_trips = int(overall_max)
    
    # Set up view
    view_state = pdk.ViewState(
        latitude=(bounds[1] + bounds[3]) / 2,
        longitude=(bounds[0] + bounds[2]) / 2,
        zoom=12,
        pitch=45,
        bearing=0
    )
    
    # Create base layers
    building_layer = create_building_layer(bounds)
    
    # Initialize decks
    deck_settings = {
        'layers': building_layer,
        'initial_view_state': view_state,
        'parameters': {
            "blendColorOperation": "add",
            "blendColorSrcFactor": "src-alpha",
            "blendColorDstFactor": "one",
            "blendAlphaOperation": "add",
            "blendAlphaSrcFactor": "one-minus-dst-alpha",
            "blendAlphaDstFactor": "one"
        }
    }
    
    deck_carto = pdk.Deck(
        **deck_settings,
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
        map_provider='carto'
    )
    
    deck_mapbox = pdk.Deck(
        **deck_settings,
        map_style="mapbox://styles/mapbox/dark-v11",
        map_provider="mapbox",
        api_keys={"mapbox": MAPBOX_API_KEY}
    )
    
# Prepare template data
    template_data = {
        'low_trips': low_trips,
        'med_trips': med_trips,
        'high_trips': high_trips,
        'total_trips': total_trips,
        'line_data': all_line_data,
        'temporal_stats': {
            str(hour): {
                'total_trips': sum(trip['trips'] for trip in data) if data else 0,
                'num_segments': len(data),
                'max_trips': max_trips_per_hour.get(hour, 0)
            } for hour, data in all_line_data.items()
        }
    }

    return deck_carto, deck_mapbox, create_html_description(template_data), template_data

def main():
    print("\nStarting temporal trip route visualization...")
    
    # Load and filter trip data
    trips_data = load_road_usage()
    bounds = (34.65, 31.15, 34.95, 31.35)  # Beer Sheva area
    trips_data = trips_data.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    print(f"Processing {len(trips_data)} routes after filtering")
    
    # Create visualizations and get returned data
    deck_carto, deck_mapbox, html_description, stats = create_line_layer(trips_data, bounds)
    
    # Save visualizations
    for deck, filename in [
        (deck_carto, "temporal_trip_routes_carto.html"),
        (deck_mapbox, "temporal_trip_routes_mapbox.html")
    ]:
        html = deck.to_html(as_string=True)
        
        # Insert custom CSS and scripts
        custom_resources = """
        <script src="https://unpkg.com/@deck.gl/core@^8.8.0/dist.min.js"></script>
        <script src="https://unpkg.com/@deck.gl/layers@^8.8.0/dist.min.js"></script>
        """
        html = html.replace('</head>', f'{custom_resources}</head>')
        
        # Insert animation controls and description
        html = html.replace('</body>', f'{html_description}</body>')
        
        # Save the file
        output_path = os.path.join(OUTPUT_DIR, filename)
        with open(output_path, 'w') as f:
            f.write(html)
        print(f"\nVisualization saved to: {output_path}")
        
        # Log summary statistics using the passed stats
        print("\nVisualization Statistics:")
        print(f"Total Routes: {len(trips_data)}")
        for hour in range(6, 23):
            hour_stats = stats['temporal_stats'].get(str(hour), {})
            print(f"Hour {hour:02d}:00 - Segments: {hour_stats.get('num_segments', 0):,}, "
                  f"Trips: {hour_stats.get('total_trips', 0):,.0f}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise