import pydeck as pdk
import requests
import json
import math
from pprint import pprint
import geopandas as gpd
import os

OUTPUT_DIR = "/Users/noamgal/DSProjects/BeerShevaMobility/data-viz/output/dashboard_data"

# Constants from the example
DATA_URL = {
    "AIRPORTS": "https://raw.githubusercontent.com/visgl/deck.gl-data/master/examples/line/airports.json",
    "FLIGHT_PATHS": "https://raw.githubusercontent.com/visgl/deck.gl-data/master/examples/line/heathrow-flights.json",
}

INITIAL_VIEW_STATE = pdk.ViewState(
    latitude=47.65,
    longitude=7,
    zoom=4.5,
    max_zoom=16,
    pitch=50,
    bearing=0
)

GET_COLOR_JS = [
    "255 * (1 - (start[2] / 10000) * 2)",
    "128 * (start[2] / 10000)",
    "255 * (start[2] / 10000)",
    "255 * (1 - (start[2] / 10000))",
]

def load_road_usage():
    """Load the trips data"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    trips = gpd.read_file(file_path)
    return trips

# Load and examine the example data
def load_example_data():
    """Load and analyze the example flight data"""
    airports = requests.get(DATA_URL["AIRPORTS"]).json()
    flights = requests.get(DATA_URL["FLIGHT_PATHS"]).json()
    
    print("\nExample Flight Data Analysis:")
    print("-----------------------------")
    print(f"Number of airports: {len(airports)}")
    print(f"Number of flight paths: {len(flights)}")
    
    # Find a valid sample flight (non-zero distance)
    sample_flight = None
    for flight in flights:
        start = flight['start']
        end = flight['end']
        distance = math.sqrt((end[0]-start[0])**2 + (end[1]-start[1])**2)
        if distance > 0:
            sample_flight = flight
            break
    
    if sample_flight:
        print("\nSample Flight Path:")
        pprint(sample_flight)
        
        # Calculate actual distance and height
        start = sample_flight['start']
        end = sample_flight['end']
        distance = math.sqrt((end[0]-start[0])**2 + (end[1]-start[1])**2)
        height = start[2]  # Z-coordinate
        
        print(f"\nStart coordinates: {start}")
        print(f"End coordinates: {end}")
        print(f"Distance: {distance:.2f}")
        print(f"Height: {height}")
        if distance > 0:
            print(f"Height/Distance ratio: {height/distance:.2f}")
    
    # Analyze height distribution
    print("\nHeight Distribution:")
    heights = [flight['start'][2] for flight in flights]
    print(f"Min height: {min(heights)}")
    print(f"Max height: {max(heights)}")
    print(f"Average height: {sum(heights)/len(heights):.2f}")
    
    # Analyze distance distribution
    print("\nDistance Distribution:")
    distances = []
    for flight in flights:
        start = flight['start']
        end = flight['end']
        dist = math.sqrt((end[0]-start[0])**2 + (end[1]-start[1])**2)
        if dist > 0:
            distances.append(dist)
    
    if distances:
        print(f"Min distance: {min(distances):.2f}")
        print(f"Max distance: {max(distances):.2f}")
        print(f"Average distance: {sum(distances)/len(distances):.2f}")
    
    # Look at a few more samples
    print("\nFirst 5 valid flights:")
    count = 0
    for flight in flights:
        if count >= 5:
            break
        start = flight['start']
        end = flight['end']
        dist = math.sqrt((end[0]-start[0])**2 + (end[1]-start[1])**2)
        if dist > 0:
            print(f"\nFlight {count+1}:")
            print(f"Start: {start}")
            print(f"End: {end}")
            print(f"Distance: {dist:.2f}")
            count += 1
    
    return airports, flights

# Create both visualizations side by side for comparison
def create_comparison():
    # First create the example layers
    airports, flights = load_example_data()
    
    scatterplot = pdk.Layer(
        "ScatterplotLayer",
        airports,
        radius_scale=20,
        get_position="coordinates",
        get_fill_color=[255, 140, 0],
        get_radius=60,
        pickable=True,
    )

    line_layer = pdk.Layer(
        "LineLayer",
        flights,
        get_source_position="start",
        get_target_position="end",
        get_color=GET_COLOR_JS,
        get_width=10,
        highlight_color=[255, 255, 0],
        picking_radius=10,
        auto_highlight=True,
        pickable=True,
    )
    
    # Original example visualization
    example_deck = pdk.Deck(
        layers=[line_layer, scatterplot],
        initial_view_state=INITIAL_VIEW_STATE,
        map_style='dark'
    )
    
    # Our data with similar structure
    trips_data = load_road_usage()
    
    # Calculate distances and heights similar to example
    line_data = []
    center_point = [34.805, 31.255]
    
    for _, row in trips_data.iterrows():
        start = row.geometry.coords[0]
        
        # Calculate distance
        distance = math.sqrt(
            (center_point[0]-start[0])**2 + 
            (center_point[1]-start[1])**2
        )
        
        # Use similar height/distance ratio as example
        height = distance * 5000  # Adjust this multiplier based on example ratio
        
        line_data.append({
            "start": [start[0], start[1], height],
            "end": [center_point[0], center_point[1], 0],
            "name": f"{row.origin_zone} to Beer Sheva",
            "trips": float(row.num_trips),
            "distance": distance
        })
    
    print("\nOur Data Analysis:")
    print("------------------")
    print(f"Number of routes: {len(line_data)}")
    print("\nSample Route:")
    pprint(line_data[0])
    
    # Create our visualization with same parameters
    our_line_layer = pdk.Layer(
        "LineLayer",
        line_data,
        get_source_position="start",
        get_target_position="end",
        get_color=GET_COLOR_JS,
        get_width=10,
        highlight_color=[255, 255, 0],
        picking_radius=10,
        auto_highlight=True,
        pickable=True,
    )
    
    our_view_state = pdk.ViewState(
        latitude=31.255,
        longitude=34.805,
        zoom=12,
        pitch=50,
        bearing=0
    )
    
    our_deck = pdk.Deck(
        layers=[our_line_layer],
        initial_view_state=our_view_state,
        map_style='dark'
    )
    
    # Save both for comparison
    example_deck.to_html("example_visualization.html")
    our_deck.to_html("our_visualization.html")

if __name__ == "__main__":
    # Create both visualizations for comparison
    create_comparison() 