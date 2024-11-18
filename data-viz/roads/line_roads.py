import pydeck as pdk
import geopandas as gpd
import os
import sys
import math
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

def create_line_layer(trips_data):
    """Create a deck.gl visualization with lines following actual road routes"""
    
    # Prepare line data using actual route geometries
    line_data = []
    max_trips = trips_data['num_trips'].max()
    
    def interpolate_color(t):
        """Interpolate between colors based on trip count ratio (t)
        Blue (low) -> Red (high)"""
        return [
            int(255 * t),        # Red increases with t
            int(128 * (1 - t)),  # Green decreases
            int(255 * (1 - t))   # Blue decreases with t
        ]

    # Process each route
    for _, row in trips_data.iterrows():
        # Calculate color based on trips
        trip_ratio = row['num_trips'] / max_trips
        color = interpolate_color(trip_ratio)
        
        # Get coordinates from the LineString geometry
        coords = list(row.geometry.coords)
        
        # Create line segments with fixed low elevation
        for i in range(len(coords) - 1):
            start = list(coords[i]) + [10]  # Fixed low elevation
            end = list(coords[i + 1]) + [10]
            
            line_data.append({
                "start": start,
                "end": end,
                "name": f"{row['origin_zone']} to {row['destination']}",
                "trips": float(row['num_trips']),
                "color": color
            })

    line_layer = pdk.Layer(
        "LineLayer",
        line_data,
        get_source_position="start",
        get_target_position="end",
        get_color="color",
        get_width="trips / 50",
        highlight_color=[255, 255, 0],
        picking_radius=10,
        auto_highlight=True,
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=31.255,
        longitude=34.805,
        zoom=12,
        pitch=50,
        bearing=0
    )

    deck = pdk.Deck(
        layers=[line_layer],
        initial_view_state=view_state,
        tooltip={"text": "{name}: {trips} trips"},
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