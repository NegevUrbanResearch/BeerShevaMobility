import pydeck as pdk
import geopandas as gpd
import os
import sys
import math
from collections import defaultdict
from shapely.ops import split, linemerge
from shapely.geometry import Point, MultiLineString
import numpy as np
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR
from shapely.geometry import Polygon

def load_road_usage():
    """Load the trips data"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    trips = gpd.read_file(file_path)
    print(f"Loaded {len(trips)} unique trip routes")
    return trips

def create_segment_data(trips_data):
    """Break down routes into segments and aggregate trip counts"""
    # Dictionary to store segment data: (start_coord, end_coord) -> trips
    segments = defaultdict(float)
    
    for _, row in trips_data.iterrows():
        coords = list(row.geometry.coords)
        num_trips = row['num_trips']
        
        # Break down each route into segments
        for i in range(len(coords) - 1):
            # Sort coordinates to ensure consistent segment keys
            segment = tuple(sorted([coords[i], coords[i + 1]]))
            segments[segment] += num_trips
    
    return segments

def get_route_distance(coords):
    """Calculate total route distance"""
    total_distance = 0
    for i in range(len(coords) - 1):
        dx = coords[i+1][0] - coords[i][0]
        dy = coords[i+1][1] - coords[i][1]
        total_distance += math.sqrt(dx*dx + dy*dy)
    return total_distance

def cube_root_scale(t):
        """Apply cube root scale to compress high values"""
        return np.cbrt(t)

def get_route_distance_ratio(coord, start_coord, end_coord):
    """Calculate distance ratio with bias towards destination"""
    dist_to_start = math.sqrt((coord[0] - start_coord[0])**2 + (coord[1] - start_coord[1])**2)
    dist_to_end = math.sqrt((coord[0] - end_coord[0])**2 + (coord[1] - end_coord[1])**2)
    total_dist = math.sqrt((end_coord[0] - start_coord[0])**2 + (end_coord[1] - start_coord[1])**2)
    
    if total_dist == 0:
        return 0
    
    # Calculate position along route (0 = start, 1 = end)
    position = dist_to_start / total_dist
    
    # Adjust the curve to peak at endpoints and minimum at 1/3 distance
    if position <= 1/3:
        ratio = 1 - (position * 3)  # 1 to 0
    elif position >= 2/3:
        ratio = (position - 2/3) * 3  # 0 to 1
    else:
        ratio = 0  # Minimum brightness in middle section
    
    return ratio

def interpolate_color(t, distance_ratio):
    """Color interpolation with enhanced opacity near endpoints"""
    t = cube_root_scale(t)
    
    colors = {
        0.0: [20, 42, 120],    # Dark blue
        0.2: [40, 80, 180],    # Medium blue
        0.4: [65, 182, 196],   # Light blue
        0.6: [127, 132, 204],  # Purple-blue
        0.8: [204, 55, 124],   # Pink-red
        1.0: [240, 52, 52]     # Bright red
    }
    
    lower_t = max([k for k in colors.keys() if k <= t])
    upper_t = min([k for k in colors.keys() if k >= t])
    
    c1 = colors[lower_t]
    c2 = colors[upper_t]
    
    ratio = (t - lower_t) / (upper_t - lower_t) if upper_t != lower_t else 0
    
    rgb = [
        min(255, int(c1[0] + (c2[0] - c1[0]) * ratio)),
        min(255, int(c1[1] + (c2[1] - c1[1]) * ratio)),
        min(255, int(c1[2] + (c2[2] - c1[2]) * ratio))
    ]
    
    # Enhanced opacity calculation
    base_opacity = 0.7 + (0.3 * distance_ratio)  # Opacity range from 70% to 100%
    opacity = min(255, int(255 * base_opacity))
    
    return rgb + [opacity]

def get_turn_angle(coord1, coord2, coord3):
    """Calculate the turn angle between three coordinates"""
    v1 = (coord2[0] - coord1[0], coord2[1] - coord1[1])
    v2 = (coord3[0] - coord2[0], coord3[1] - coord2[1])
    
    # Calculate angle between vectors
    dot_product = v1[0]*v2[0] + v1[1]*v2[1]
    v1_norm = math.sqrt(v1[0]**2 + v1[1]**2)
    v2_norm = math.sqrt(v2[0]**2 + v2[1]**2)
    
    # Avoid division by zero
    if v1_norm * v2_norm == 0:
        return 0
        
    cos_angle = dot_product / (v1_norm * v2_norm)
    cos_angle = max(min(cos_angle, 1), -1)  # Ensure value is in [-1, 1]
    return math.acos(cos_angle)

def create_line_layer(trips_data):
    """Create a deck.gl visualization with continuous routes"""
    segments = create_segment_data(trips_data)
    line_data = []
    max_trips = max(segments.values())
    
    for (start_coord, end_coord), trip_count in segments.items():
        trip_ratio = trip_count / max_trips
        
        # Calculate distance ratio from endpoints for opacity
        mid_point = ((start_coord[0] + end_coord[0])/2, (start_coord[1] + end_coord[1])/2)
        distance_ratio = get_route_distance_ratio(mid_point, start_coord, end_coord)
        
        line_data.append({
            "start": [start_coord[0], start_coord[1], 5],
            "end": [end_coord[0], end_coord[1], 5],
            "trips": int(trip_count),
            "color": interpolate_color(trip_ratio, distance_ratio),
            "width": 4 + (trip_ratio * 2)
        })

    # Create the line layer
    line_layer = pdk.Layer(
        "LineLayer",
        line_data,
        get_source_position="start",
        get_target_position="end",
        get_color="color",
        get_width="width",
        opacity=1,  
        highlight_color=[255, 255, 0, 128],
        picking_radius=10,
        auto_highlight=True,
        pickable=True
    )

    # Set up view and deck with same blending parameters as JavaScript example
    view_state = pdk.ViewState(
        latitude=31.25,
        longitude=34.8,
        zoom=12,
        pitch=60,
        bearing=0
    )

    deck = pdk.Deck(
        layers=[line_layer],
        initial_view_state=view_state,
        map_style='dark',
        parameters={
            "blendColorOperation": "add",
            "blendColorSrcFactor": "src-alpha",
            "blendColorDstFactor": "one",
            "blendAlphaOperation": "add",
            "blendAlphaSrcFactor": "one-minus-dst-alpha",
            "blendAlphaDstFactor": "one"
        }
    )

    return deck

def main():
    print("\nStarting trip route visualization...")
    trips_data = load_road_usage()
    
    # Filter to the Beer Sheva area
    bounds = (34.65, 31.15, 34.95, 31.35)
    trips_data = trips_data.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    print(f"Processing {len(trips_data)} routes after filtering")
    
    deck = create_line_layer(trips_data)
    output_path = os.path.join(OUTPUT_DIR, "trip_routes_deck.html")
    deck.to_html(output_path)
    
    print(f"\nVisualization saved to: {output_path}")

if __name__ == "__main__":
    main()