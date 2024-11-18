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

def create_line_layer(trips_data):
    """Create a deck.gl visualization with properly blended line segments"""
    segments = create_segment_data(trips_data)
    line_data = []
    max_trips = max(segments.values())
    
    def cube_root_scale(t):
        """Apply cube root scale to compress high values"""
        return np.cbrt(t)
    
    def interpolate_color(t, distance_ratio=0.5):
        """Enhanced color interpolation with cube root scaling
        t: trip count ratio (0-1)
        distance_ratio: how far along the segment we are (0-1)"""
        # Apply cube root scaling to trip ratio
        t = cube_root_scale(t)
        
        colors = {
            0.0: [65, 182, 196],    # Light blue
            0.3: [127, 132, 204],   # Purple-blue
            0.6: [179, 77, 184],    # Purple
            0.8: [204, 55, 124],    # Pink-red
            1.0: [240, 52, 52]      # Deep red
        }
        
        # Find the two colors to interpolate between
        lower_t = max([k for k in colors.keys() if k <= t])
        upper_t = min([k for k in colors.keys() if k >= t])
        
        c1 = colors[lower_t]
        c2 = colors[upper_t]
        
        # Interpolate between the two colors
        if upper_t == lower_t:
            rgb = c1
        else:
            ratio = (t - lower_t) / (upper_t - lower_t)
            rgb = [
                int(c1[0] + (c2[0] - c1[0]) * ratio),
                int(c1[1] + (c2[1] - c1[1]) * ratio),
                int(c1[2] + (c2[2] - c1[2]) * ratio)
            ]
        
        # Adjust opacity based on distance from endpoints
        opacity = min(255, int(255 * (0.4 + 0.6 * (1 - abs(2 * distance_ratio - 1)))))
        return rgb + [opacity]  # Return [R,G,B,A]

    # Process each segment
    for (start_coord, end_coord), trip_count in segments.items():
        trip_ratio = trip_count / max_trips
        
        num_steps = 10
        for i in range(num_steps):
            distance_ratio = i / (num_steps - 1)
            # Interpolate position with height variation
            height = 10  # set height to 10 meters to ensure visibility above basemap
            start = [
                start_coord[0] + (end_coord[0] - start_coord[0]) * distance_ratio,
                start_coord[1] + (end_coord[1] - start_coord[1]) * distance_ratio,
                height  # Higher elevation
            ]
            end = [
                start_coord[0] + (end_coord[0] - start_coord[0]) * ((i + 1) / (num_steps - 1)),
                start_coord[1] + (end_coord[1] - start_coord[1]) * ((i + 1) / (num_steps - 1)),
                height  # Higher elevation
            ]
            
            color = interpolate_color(trip_ratio, distance_ratio)
            
            line_data.append({
                "start": start,
                "end": end,
                "trips": int(trip_count),  # Convert to int for cleaner tooltip
                "count": int(trip_count),  # Add explicit count field for tooltip
                "color": color
            })

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
        pickable=True,
        # Add tooltip configuration
        tooltip={
            "html": "<b>Trip Count:</b> {count}",
            "style": {
                "backgroundColor": "steelblue",
                "color": "white"
            }
        }
    )

    # Update view state for better 3D perspective
    view_state = pdk.ViewState(
        latitude=31.25,  # Adjust to your map center
        longitude=34.8,  # Adjust to your map center
        zoom=12,
        pitch=60,  # Increased pitch for better 3D view
        bearing=0
    )

    # Create and return the deck
    deck = pdk.Deck(
        layers=[line_layer],
        initial_view_state=view_state,
        map_style='dark'
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