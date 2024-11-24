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
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR, MAPBOX_API_KEY, BUILDINGS_FILE, POI_LOCATIONS
from shapely.geometry import Polygon
from geopy.distance import geodesic
from data_loader import DataLoader


# Style link
CSS_LINK = '<link href="https://api.mapbox.com/mapbox-gl-js/v2.14.1/mapbox-gl.css" rel="stylesheet" />'

# At the top with other constants
POI_RADIUS = 0.0018  # about 200 meters in decimal degrees

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
    
    # Calculate total unique trips (sum of num_trips for each route)
    total_trips = trips_data['num_trips'].sum()

    num_segments = 1
    segment_length = 1.995  # Slightly shorter to create gaps (99.75% of original 2.0)
    step_size = 2.0
    
    for (start_coord, end_coord), trip_count in segments.items():
        trip_ratio = trip_count / max_trips
        total_distance = math.sqrt(
            (end_coord[0] - start_coord[0])**2 + 
            (end_coord[1] - start_coord[1])**2
        )
        
        if total_distance == 0:
            continue
            
        for i in range(num_segments):
            # Add small random variations
            jitter = 0.00001  # Approximately 1 meter
            random_offset = [
                (np.random.random() - 0.5) * jitter,
                (np.random.random() - 0.5) * jitter
            ]
            
            # Adjust start and end positions to create small gaps
            start_pos = (i * step_size) / total_distance + 0.01  # Add 1% gap at start
            end_pos = start_pos + (segment_length / total_distance) - 0.01  # Subtract 1% gap at end
            
            if start_pos >= 1.0:
                break
            end_pos = min(end_pos, 0.99)  # Never go quite to the end
            
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
            
            mid_pos = (start_pos + end_pos) / 2
            color = interpolate_color(trip_ratio, mid_pos)
            
            line_data.append({
                "start": start,
                "end": end,
                "trips": int(trip_count),
                "color": color
            })

    # Create the layers
    building_layer = create_building_layer(bounds)
    line_layer = pdk.Layer(
        "LineLayer",
        line_data,
        get_source_position="start",
        get_target_position="end",
        get_color="color",
        get_width=3,
        pickable=True,
        opacity=0.8,
    )

    # Define the view state
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    
    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=12,
        pitch=45,
        bearing=0
    )


    # Create description with fully opaque backgrounds
    low_trips = int(max_trips * 0.2)
    med_trips = int(max_trips * 0.6)
    high_trips = int(max_trips)
    
    # Create the deck instances WITHOUT description
    deck_carto = pdk.Deck(
        layers=[building_layer, line_layer],
        initial_view_state=view_state,
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
        map_provider='carto',
        parameters={
            "blendColorOperation": "add",
            "blendColorSrcFactor": "src-alpha",
            "blendColorDstFactor": "one",
            "blendAlphaOperation": "add",
            "blendAlphaSrcFactor": "one-minus-dst-alpha",
            "blendAlphaDstFactor": "one"
        }
    )

    deck_mapbox = pdk.Deck(
        layers=[building_layer, line_layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v10",
        map_provider="mapbox",
        api_keys={"mapbox": MAPBOX_API_KEY},
        parameters={
            "blendColorOperation": "add",
            "blendColorSrcFactor": "src-alpha",
            "blendColorDstFactor": "one",
            "blendAlphaOperation": "add",
            "blendAlphaSrcFactor": "one-minus-dst-alpha",
            "blendAlphaDstFactor": "one"
        }
    )

    return deck_carto, deck_mapbox, create_html_description(low_trips, med_trips, high_trips, total_trips)

def create_html_description(low_trips, med_trips, high_trips, total_trips):
    """Create HTML description to be injected into the template"""
    return f"""
    <style>
        .deck-tooltip {{
            display: none !important;
        }}
        .overlay-container {{
            position: relative;
            z-index: 99999999;
            pointer-events: none;
        }}
        .overlay-container > div {{
            pointer-events: auto;
        }}
        .legend-container {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #000000;
            padding: 12px;
            border-radius: 5px;
            color: #FFFFFF;
            font-family: Arial;
        }}
        .methodology-container {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: #000000;
            padding: 12px;
            border-radius: 5px;
            color: #FFFFFF;
            font-family: Arial;
            max-width: 300px;
        }}
    </style>
    <div class="overlay-container">
        <div class="legend-container">
            <h3 style="margin: 0 0 10px 0;">Trip Intensity</h3>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 4px; background: #142A78; margin-right: 8px;"></div>
                <span>Low (1-{low_trips} trips/day)</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 4px; background: #41B6C4; margin-right: 8px;"></div>
                <span>Medium ({low_trips+1}-{med_trips} trips/day)</span>
            </div>
            <div style="display: flex; align-items: center;">
                <div style="width: 20px; height: 4px; background: #F03434; margin-right: 8px;"></div>
                <span>High ({med_trips+1}-{high_trips} trips/day)</span>
            </div>
        </div>
        <div class="methodology-container">
            <h3 style="margin: 0 0 10px 0;">Methodology</h3>
            <p style="margin: 0; font-size: 0.9em;">
                This visualization represents aggregated trip data across Beer Sheva's road network.
                Total Daily Trips: {total_trips:,}<br><br>
                Colors indicate trip intensity using a cube root scale to highlight both major and minor routes.
                Highlighted buildings indicate Points of Interest:<br>
                • BGU (Green)<br>
                • Gav Yam (Blue)<br>
                • Soroka Hospital (White)
            </p>
        </div>
    </div>
    """

def create_building_layer(bounds):
    """Create a building layer with highlighted POI buildings"""
    buildings_gdf = gpd.read_file(BUILDINGS_FILE)
    building_features = []
    text_features = []
    
    # Define POI colors with subtle tones that match building aesthetic
    poi_info = {
        'BGU': {'color': [40, 120, 40, 160], 'lat': 31.2614375, 'lon': 34.7995625},        # Muted green
        'Gav Yam': {'color': [40, 100, 140, 160], 'lat': 31.2641875, 'lon': 34.8128125},   # Muted teal
        'Soroka Hospital': {'color': [140, 140, 140, 160], 'lat': 31.2579375, 'lon': 34.8003125}  # Muted white
    }
    
    # Create a transformer for POI coordinates
    transformer = Transformer.from_crs("EPSG:4326", buildings_gdf.crs, always_xy=True)
    
    for idx, building in buildings_gdf.iterrows():
        building_color = [74, 80, 87, 160]  # Default color matching the original style
        try:
            # Get actual height from building data, default to 20 if not found
            height = float(building.get('height', 20))
            # Scale height by 1.5 to match trip_roads.py
            building_height = height * 1.5
            
            # Check if building is within radius of main POIs
            for poi_name, info in poi_info.items():
                poi_x, poi_y = transformer.transform(info['lon'], info['lat'])
                poi_point = Point(poi_x, poi_y)
                
                if building.geometry.centroid.distance(poi_point) <= POI_RADIUS:
                    building_height = min(40 ,height * 1000)
                    building_color = info['color']
                    
                    # Add text label for POI
                    text_features.append({
                        "position": [poi_x, poi_y, building_height + 10],  # Position above building
                        "text": poi_name,
                        "color": [150, 150, 150, 255]  # Grey color
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
    
    building_layer = pdk.Layer(
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
    )
    
    text_layer = pdk.Layer(
        "TextLayer",
        text_features,
        get_position="position",
        get_text="text",
        get_color="color",
        get_size=16,
        get_angle=0,
        get_text_anchor="middle",
        get_alignment_baseline="center"
    )
    
    return [building_layer, text_layer]

def main():
    print("\nStarting trip route visualization...")
    trips_data = load_road_usage()
    
    # Filter to the Beer Sheva area
    bounds = (34.65, 31.15, 34.95, 31.35)
    trips_data = trips_data.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    print(f"Processing {len(trips_data)} routes after filtering")
    
    deck_carto, deck_mapbox, html_description = create_line_layer(trips_data, bounds)
    
    # Create HTML files with custom template
    for deck, filename in [(deck_carto, "trip_routes_deck_carto.html"), 
                          (deck_mapbox, "trip_routes_deck_mapbox.html")]:
        html = deck.to_html(as_string=True)
        # Insert our description just before the closing body tag
        html = html.replace('</body>', f'{html_description}</body>')
        
        output_path = os.path.join(OUTPUT_DIR, filename)
        with open(output_path, 'w') as f:
            f.write(html)
        print(f"\nVisualization saved to: {output_path}")
if __name__ == "__main__":
    main()