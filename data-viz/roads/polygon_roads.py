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
from pyproj import Transformer
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
    # Dictionary to store segment data: (start_coord, end_coord) -> (trips, route_points)
    segments = defaultdict(lambda: {"trips": 0.0, "routes": []})
    
    for _, row in trips_data.iterrows():
        coords = list(row.geometry.coords)
        num_trips = row['num_trips']
        
        # Break down each route into segments
        for i in range(len(coords) - 1):
            # Sort coordinates to ensure consistent segment keys
            segment = tuple(sorted([coords[i], coords[i + 1]]))
            segments[segment]["trips"] += num_trips
            # Store the original sequence of points for this route
            segments[segment]["routes"].append(coords)
    
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
    """Color interpolation based on trip count and distance ratio"""
    # Apply cube root scaling to trip ratio for better distribution
    t = cube_root_scale(t)
    
    # Base colors (from low to high trip counts, with increasing brightness)
    colors = {
        0.0: [20, 42, 120],     # Dark blue
        0.2: [40, 80, 180],     # Medium blue
        0.4: [65, 182, 196],    # Light blue
        0.6: [120, 200, 150],   # Blue-green
        0.8: [200, 220, 100],   # Yellow-green
        1.0: [255, 255, 0]      # Bright yellow
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

def bezier_point(p0, p1, p2, t):
    """Calculate point along a quadratic Bezier curve"""
    x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
    y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
    return (x, y)

def get_control_point(p1, p2, next_p):
    """Calculate control point for smooth curve"""
    if next_p is None:
        return ((p1[0] + p2[0])/2, (p1[1] + p2[1])/2)
    
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    
    # Use the next point to influence the control point
    return (p2[0] + dx*0.25, p2[1] + dy*0.25)

def create_line_layer(trips_data, bounds):
    segments = create_segment_data(trips_data)
    polygon_data = []
    max_trips = max(seg["trips"] for seg in segments.values())
    total_trips = sum(seg["trips"] for seg in segments.values())
    
    for segment, data in segments.items():
        start_coord, end_coord = segment
        trip_count = data["trips"]
        trip_ratio = trip_count / max_trips
        height = 100 * (trip_ratio ** 0.5)
        
        # Use the first route's points for this segment to generate smooth curves
        route_points = data["routes"][0]  # Take the first route as reference
        curve_points = []
        
        for i in range(len(route_points)-1):
            p1 = route_points[i]
            p2 = route_points[i+1]
            next_p = route_points[i+2] if i < len(route_points)-2 else None
            
            control = get_control_point(p1, p2, next_p)
            
            # Generate points along the curve
            for t in np.linspace(0, 1, 10):  # 10 points per segment
                point = bezier_point(p1, control, p2, t)
                curve_points.append(point)
        
        # Create polygon coordinates with variable width
        width = 0.00015  # Base width
        width_scale = 0.5 + 0.5 * (trip_ratio ** 0.5)  # Scale width by trip count
        adjusted_width = width * width_scale
        
        # Generate polygon points
        polygon_points = []
        for i in range(len(curve_points)):
            if i < len(curve_points) - 1:
                p1 = curve_points[i]
                p2 = curve_points[i + 1]
                
                # Calculate perpendicular vector
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = math.sqrt(dx*dx + dy*dy)
                if length == 0:
                    continue
                
                # Normalize and rotate 90 degrees
                nx = -dy * adjusted_width / length
                ny = dx * adjusted_width / length
                
                # Add points for both sides of the road
                if i == 0:  # First segment
                    polygon_points.append([p1[0] + nx, p1[1] + ny, 0])
                polygon_points.append([p2[0] + nx, p2[1] + ny, 0])
        
        # Add return points (other side of the road)
        for i in range(len(curve_points) - 1, -1, -1):
            if i > 0:
                p1 = curve_points[i]
                p2 = curve_points[i - 1]
                
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = math.sqrt(dx*dx + dy*dy)
                if length == 0:
                    continue
                
                nx = -dy * adjusted_width / length
                ny = dx * adjusted_width / length
                
                polygon_points.append([p1[0] - nx, p1[1] - ny, 0])
        
        # Close the polygon
        if polygon_points:
            polygon_points.append(polygon_points[0])
        
        # Create top surface points
        top_points = [[x, y, height] for x, y, _ in polygon_points]
        
        # Combine bottom and top points
        all_points = polygon_points + top_points
        
        color = interpolate_color(trip_ratio, 0.5)
        
        polygon_data.append({
            "polygon": all_points,
            "trips": int(trip_count),
            "color": color,
            "height": height
        })

    # Create the layers
    building_layer = create_building_layer(bounds)
    route_layer = pdk.Layer(
        "PolygonLayer",
        polygon_data,
        get_polygon="polygon",
        get_fill_color="color",
        get_line_color=[255, 255, 255, 50],
        wireframe=True,
        filled=True,
        extruded=True,
        get_elevation="height",
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

    # Create description HTML
    description = f"""
    <style>
        .legend {{
            position: absolute;
            bottom: 20px;
            right: 20px;
            background: rgba(0,0,0,0.8);
            padding: 12px;
            border-radius: 5px;
            color: white;
            font-family: Arial;
        }}
        .methodology {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0,0,0,0.8);
            padding: 12px;
            border-radius: 5px;
            color: white;
            font-family: Arial;
            max-width: 300px;
        }}
    </style>
    <div class="legend">
        <h3 style="margin: 0 0 10px 0;">Trip Intensity</h3>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 20px; height: 4px; background: rgb(20,42,120); margin-right: 8px;"></div>
            <span>Low</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 20px; height: 4px; background: rgb(65,182,196); margin-right: 8px;"></div>
            <span>Medium</span>
        </div>
        <div style="display: flex; align-items: center;">
            <div style="width: 20px; height: 4px; background: rgb(240,52,52); margin-right: 8px;"></div>
            <span>High</span>
        </div>
    </div>
    <div class="methodology">
        <h3 style="margin: 0 0 10px 0;">Methodology</h3>
        <p style="margin: 0; font-size: 0.9em;">
            This visualization represents aggregated trip data across Beer Sheva's road network.
            Total Trips: {int(total_trips):,}<br><br>
            Colors indicate trip intensity using a cube root scale to highlight both major and minor routes.
            Segments are rendered with overlapping gradients for smooth transitions.
        </p>
    </div>
    """

    # Create the deck instances
    deck_carto = pdk.Deck(
        layers=[building_layer, route_layer],
        initial_view_state=view_state,
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
        parameters={
            "blendColorOperation": "add",
            "blendColorSrcFactor": "src-alpha",
            "blendColorDstFactor": "one",
            "blendAlphaOperation": "add",
            "blendAlphaSrcFactor": "one-minus-dst-alpha",
            "blendAlphaDstFactor": "one"
        },
        description=description
    )

    deck_mapbox = pdk.Deck(
        layers=[building_layer, route_layer],
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
        api_keys={"mapbox": MAPBOX_API_KEY},
        map_provider="mapbox",
        description=description
    )

    return deck_carto, deck_mapbox

def create_building_layer(bounds):
    """Create a deck.gl layer for buildings with highlighted POIs"""
    buildings_gdf = gpd.read_file(BUILDINGS_FILE)
    
    # Define POI colors with subtle tones that match building aesthetic
    poi_info = {
        'BGU': {'color': [40, 120, 40, 160], 'lat': 31.2614375, 'lon': 34.7995625},        # Muted green
        'Gav Yam': {'color': [40, 100, 140, 160], 'lat': 31.2641875, 'lon': 34.8128125},   # Muted teal
        'Soroka Hospital': {'color': [140, 140, 140, 160], 'lat': 31.2579375, 'lon': 34.8003125}  # Muted white
    }
    
    # Create a transformer for POI coordinates
    transformer = Transformer.from_crs("EPSG:4326", buildings_gdf.crs, always_xy=True)
    
    building_data = []
    text_features = []
    
    for _, building in buildings_gdf.iterrows():
        try:
            building_color = [74, 80, 87, 160]  # Default color
            coords = list(building.geometry.exterior.coords)
            height = float(building.get('height', 20))
            building_height = height * 2  # Double the height as before
            
            # Check if building is within radius of main POIs
            for poi_name, info in poi_info.items():
                poi_x, poi_y = transformer.transform(info['lon'], info['lat'])
                poi_point = Point(poi_x, poi_y)
                
                if building.geometry.centroid.distance(poi_point) <= POI_RADIUS:
                    building_height = min(80, height * 2000)  # Increased height for POIs
                    building_color = info['color']
                    
                    # Add text label for POI
                    text_features.append({
                        "position": [poi_x, poi_y, building_height + 10],
                        "text": poi_name,
                        "color": [150, 150, 150, 255]
                    })
                    break
            
            building_data.append({
                "polygon": [[float(x), float(y)] for x, y in coords],
                "height": building_height,
                "color": building_color
            })
        except Exception as e:
            print(f"Skipping building due to error: {e}")
            continue
    
    building_layer = pdk.Layer(
        "PolygonLayer",
        building_data,
        extruded=True,
        wireframe=True,
        opacity=0.8,
        get_polygon="polygon",
        get_elevation="height",
        get_fill_color="color",
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
    
    deck_carto, deck_mapbox = create_line_layer(trips_data, bounds)
    output_path_carto = os.path.join(OUTPUT_DIR, "trip_routes_deck_polygon_carto.html")
    deck_carto.to_html(output_path_carto)
    output_path_mapbox = os.path.join(OUTPUT_DIR, "trip_routes_deck_polygon_mapbox.html")
    deck_mapbox.to_html(output_path_mapbox)
    
    print(f"\nVisualization saved to: {output_path_carto}")
    print(f"\nVisualization saved to: {output_path_mapbox}")
if __name__ == "__main__":
    main()