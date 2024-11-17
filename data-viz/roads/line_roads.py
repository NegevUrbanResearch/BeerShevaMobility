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
    
    # Define central destination as a polygon
    central_polygon = {
        "polygon": [
            [34.795, 31.245],  # SW
            [34.815, 31.245],  # SE
            [34.815, 31.265],  # NE
            [34.795, 31.265],  # NW
            [34.795, 31.245]   # Close the polygon
        ],
        "name": "Beer Sheva Center"
    }
    
    # Prepare line data using actual route geometries
    line_data = []
    max_trips = trips_data['num_trips'].max()
    
    def interpolate_color(t):
        """Interpolate between colors based on trip count ratio (t)
        Blue (low) -> Yellow (medium) -> Red (high)"""
        if t < 0.5:  # Blue to Yellow
            r = int(255 * (2 * t))
            g = int(255 * (2 * t))
            b = int(255 * (1 - 2 * t))
        else:  # Yellow to Red
            t = t * 2 - 1
            r = 255
            g = int(255 * (1 - t))
            b = 0
        return [r, g, b]

    # Process each route
    for _, row in trips_data.iterrows():
        # Calculate color based on trips
        trip_ratio = row['num_trips'] / max_trips
        color = interpolate_color(trip_ratio)
        
        # Get coordinates from the LineString geometry
        coords = list(row.geometry.coords)
        
        # Create line segments with small elevation
        for i in range(len(coords) - 1):
            start = list(coords[i]) + [50]  # Add small elevation
            end = list(coords[i + 1]) + [50]
            
            line_data.append({
                "start": start,
                "end": end,
                "name": f"{row['origin_zone']} to {row['destination']}",
                "trips": float(row['num_trips']),
                "color": color
            })

    # Create 3D polygon layer for destination
    polygon_layer = pdk.Layer(
        "PolygonLayer",
        [central_polygon],
        get_polygon="polygon",
        get_fill_color=[255, 140, 0, 180],  # Semi-transparent orange
        get_line_color=[255, 140, 0],
        get_line_width=2,
        pickable=True,
        filled=True,
        extruded=True,
        get_elevation=500,  # Height of the 3D polygon
        elevation_scale=1,
        wireframe=True
    )

    line_layer = pdk.Layer(
        "LineLayer",
        line_data,
        get_source_position="start",
        get_target_position="end",
        get_color="color",
        get_width="trips / 50",  # Width also scales with trips
        opacity=0.8,
        highlight_color=[255, 255, 255],
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
        layers=[line_layer, polygon_layer],  # Polygon layer on top
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