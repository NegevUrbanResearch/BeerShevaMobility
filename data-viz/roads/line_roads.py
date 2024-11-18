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
from config import OUTPUT_DIR, MAPBOX_API_KEY
from shapely.geometry import Polygon

# Style link
CSS_LINK = '<link href="https://api.mapbox.com/mapbox-gl-js/v2.14.1/mapbox-gl.css" rel="stylesheet" />'

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

def interpolate_color(t, distance_ratio):
    """Color interpolation based on trip count and distance ratio
    
    Color Scheme:
    - Base colors progress from dark blue -> light blue -> purple -> pink -> bright red
    - Brightness increases with trip count
    - Opacity varies smoothly between segments to reduce blockiness
    
    Args:
        t (float): Normalized trip count (0-1)
        distance_ratio (float): Position along segment (0-1)
    """
    # Apply cube root scaling to trip ratio for better distribution
    t = cube_root_scale(t)
    
    # Base colors (from low to high trip counts, with increasing brightness)
    colors = {
        0.0: [20, 42, 120],     # Dark blue
        0.2: [40, 80, 180],     # Medium blue
        0.4: [65, 182, 196],    # Light blue
        0.6: [127, 132, 204],   # Purple-blue
        0.8: [204, 55, 124],    # Pink-red
        1.0: [240, 52, 52]      # Bright red
    }
    
    # Find and interpolate colors
    lower_t = max([k for k in colors.keys() if k <= t])
    upper_t = min([k for k in colors.keys() if k >= t])
    
    c1 = colors[lower_t]
    c2 = colors[upper_t]
    
    # Smooth transition between segments
    ratio = (t - lower_t) / (upper_t - lower_t) if upper_t != lower_t else 0
    
    # Add gaussian-like falloff for smoother segment transitions
    smoothing = math.exp(-4 * (distance_ratio - 0.5)**2)
    brightness = 0.7 + 0.3 * smoothing
    
    rgb = [
        min(255, int((c1[0] + (c2[0] - c1[0]) * ratio) * brightness)),
        min(255, int((c1[1] + (c2[1] - c1[1]) * ratio) * brightness)),
        min(255, int((c1[2] + (c2[2] - c1[2]) * ratio) * brightness))
    ]
    
    # Smooth opacity transition between segments
    base_opacity = 0.7 + 0.3 * smoothing
    opacity = min(255, int(255 * base_opacity))
    
    return rgb + [opacity]

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

def create_line_layer(trips_data, bounds):
    """Create a deck.gl visualization with smooth segment transitions"""
    segments = create_segment_data(trips_data)
    line_data = []
    max_trips = max(segments.values())
    
    num_segments = 30
    segment_length = 2.0  # Each segment is 2 units long
    step_size = 1.0      # Move forward by 1 unit each time (creates 50% overlap)
    
    for (start_coord, end_coord), trip_count in segments.items():
        trip_ratio = trip_count / max_trips
        total_distance = math.sqrt(
            (end_coord[0] - start_coord[0])**2 + 
            (end_coord[1] - start_coord[1])**2
        )
        
        # Check if total_distance is zero
        if total_distance == 0:
            continue  # Skip this segment if there's no distance
        
        # Create segments with exact 50% overlap
        for i in range(num_segments):
            # Calculate the start and end positions for this segment
            start_pos = (i * step_size) / total_distance
            end_pos = start_pos + (segment_length / total_distance)
            
            # Ensure we don't extend beyond the line
            if start_pos >= 1.0:
                break
            end_pos = min(end_pos, 1.0)
            
            start = [
                start_coord[0] + (end_coord[0] - start_coord[0]) * start_pos,
                start_coord[1] + (end_coord[1] - start_coord[1]) * start_pos,
                5
            ]
            end = [
                start_coord[0] + (end_coord[0] - start_coord[0]) * end_pos,
                start_coord[1] + (end_coord[1] - start_coord[1]) * end_pos,
                5
            ]
            
            # Calculate the midpoint for color interpolation
            mid_pos = (start_pos + end_pos) / 2
            color = interpolate_color(trip_ratio, mid_pos)
            
            line_data.append({
                "start": start,
                "end": end,
                "trips": int(trip_count),
                "color": color
            })

    # Create the line layer
    line_layer = pdk.Layer(
        "LineLayer",
        line_data,
        get_source_position="start",
        get_target_position="end",
        get_color="color",
        get_width=5,
        highlight_color=[255, 255, 0, 128],
        picking_radius=10,
        auto_highlight=True,
        pickable=True
    )

    # Update view state for better 3D perspective
    view_state = pdk.ViewState(
        latitude=31.2627,  # Ben Gurion University
        longitude=34.8113, # Ben Gurion University
        zoom=13,
        pitch=60,  # Increased pitch for better 3D view
        bearing=0
    )

    # Create the layers
    building_layer = create_building_layer(bounds)
    
    # Create and return the carto deck
    deck_carto = pdk.Deck(
        layers=[building_layer, line_layer],  # Add building layer first
        initial_view_state=view_state,
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
        parameters={
            "blendColorOperation": "add",
            "blendColorSrcFactor": "src-alpha",
            "blendColorDstFactor": "one",
            "blendAlphaOperation": "add",
            "blendAlphaSrcFactor": "one-minus-dst-alpha",
            "blendAlphaDstFactor": "one"
        }
    )
    # Create and return the mapbox deck
    deck_mapbox = pdk.Deck( 
        layers=[building_layer, line_layer],  # Add building layer first
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v10",
        parameters={
            "blendColorOperation": "add",
            "blendColorSrcFactor": "src-alpha",
            "blendColorDstFactor": "one",
            "blendAlphaOperation": "add",
            "blendAlphaSrcFactor": "one-minus-dst-alpha",
            "blendAlphaDstFactor": "one"
        },
        api_keys={"mapbox":MAPBOX_API_KEY},
        map_provider="mapbox"
    )
    

    return deck_carto, deck_mapbox

def create_building_layer(bounds):
    """Create a deck.gl layer for buildings"""
    # Load building data
    buildings_path = os.path.join(OUTPUT_DIR, "buildings.geojson")
    buildings_gdf = gpd.read_file(buildings_path)
    
    # Filter to bounds
    buildings_gdf = buildings_gdf.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    
    building_data = []
    for _, row in buildings_gdf.iterrows():
        try:
            coords = list(row.geometry.exterior.coords)
            height = float(row.get('height', 20))  # Fix: use get() on row directly
            building_data.append({
                "polygon": [[float(x), float(y)] for x, y in coords],
                "height": height * 2  # Double the height
            })
        except Exception as e:
            print(f"Skipping building due to error: {e}")
            continue
    
    return pdk.Layer(
        "PolygonLayer",
        building_data,
        extruded=True,
        wireframe=True,
        opacity=0.8,
        get_polygon="polygon",
        get_elevation="height",
        get_fill_color=[74, 80, 87],
        get_line_color=[255, 255, 255, 50],
        line_width_min_pixels=1,
        material={
            "ambient": 0.2,
            "diffuse": 0.8,
            "shininess": 32,
            "specularColor": [60, 64, 70]
        }
    )

def main():
    print("\nStarting trip route visualization...")
    trips_data = load_road_usage()
    
    # Filter to the Beer Sheva area
    bounds = (34.65, 31.15, 34.95, 31.35)
    trips_data = trips_data.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    print(f"Processing {len(trips_data)} routes after filtering")
    
    deck_carto, deck_mapbox = create_line_layer(trips_data, bounds)
    output_path_carto = os.path.join(OUTPUT_DIR, "trip_routes_deck_carto.html")
    deck_carto.to_html(output_path_carto)
    output_path_mapbox = os.path.join(OUTPUT_DIR, "trip_routes_deck_mapbox.html")
    deck_mapbox.to_html(output_path_mapbox)
    
    print(f"\nVisualization saved to: {output_path_carto}")
    print(f"\nVisualization saved to: {output_path_mapbox}")
if __name__ == "__main__":
    main()

