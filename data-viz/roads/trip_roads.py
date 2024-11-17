import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
from datetime import datetime
import os
import sys
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
from config import MAPBOX_API_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR

def load_trip_data():
    """Load the trip data and convert to format needed for TripLayer"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    trips_gdf = gpd.read_file(file_path)
    
    logger.info(f"Loading {len(trips_gdf)} trips")
    
    # Get bounds for view state
    bounds = trips_gdf.total_bounds
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    
    # Group trips by route_id to deduplicate
    unique_routes = {}
    route_trips = {}
    
    for _, row in trips_gdf.iterrows():
        route_id = row['route_id']
        
        # Store unique route geometries
        if route_id not in unique_routes:
            coords = list(row.geometry.coords)
            if not coords or len(coords) < 2:
                continue
                
            # Validate coordinates
            if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in coords):
                continue
                
            unique_routes[route_id] = {
                "coordinates": [[float(x), float(y)] for x, y in coords]
            }
            route_trips[route_id] = []
            
        # Store trip timing information
        route_trips[route_id].append({
            'departure_time': pd.to_datetime(row['departure_time']),
            'arrival_time': pd.to_datetime(row['arrival_time'])
        })
    
    logger.info(f"Processed {len(unique_routes)} unique routes")
    
    # Process timing for each route
    min_time = pd.to_datetime(trips_gdf['departure_time'].min())
    time_scale = 30.0 / (3 * 3600)  # 30 seconds / 3 hours
    
    trip_data = []
    for route_id, route in unique_routes.items():
        coords = route['coordinates']
        for trip in route_trips[route_id]:
            start_time = trip['departure_time']
            end_time = trip['arrival_time']
            
            start_seconds = (start_time - min_time).total_seconds() * time_scale
            end_seconds = start_seconds + (end_time - start_time).total_seconds() * time_scale
            
            timestamps = np.linspace(start_seconds, end_seconds, len(coords))
            
            trip_data.append({
                "coordinates": coords,
                "timestamps": timestamps.tolist()
            })
    
    logger.info(f"Generated {len(trip_data)} trip animations")
    return pd.DataFrame(trip_data), center_lat, center_lon

def create_trip_layer():
    """Create a deck.gl visualization with TripLayer and controls"""
    trips_df, center_lat, center_lon = load_trip_data()
    
    layer = pdk.Layer(
        "TripsLayer",
        trips_df,
        get_path="coordinates",
        get_timestamps="timestamps",
        get_color=[255, 140, 0],
        opacity=1.0,
        width_min_pixels=4,
        width_scale=2,
        rounded=True,
        trail_length=300,
        current_time=0,
        pickable=True,
        auto_highlight=True
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=11,
        pitch=45,
        bearing=0
    )

    # Create HTML with controls
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            #controls {
                position: absolute;
                top: 10px;
                left: 10px;
                background: rgba(255, 255, 255, 0.9);
                padding: 10px;
                border-radius: 5px;
            }
            .control-group {
                margin: 10px 0;
            }
            label {
                display: block;
                margin-bottom: 5px;
            }
        </style>
    </head>
    <body>
        <div id="controls">
            <div class="control-group">
                <label for="trail-length">Trail Length: <span id="trail-value">300</span></label>
                <input type="range" id="trail-length" min="50" max="500" value="300">
            </div>
            <div class="control-group">
                <label for="animation-speed">Speed: <span id="speed-value">1x</span></label>
                <input type="range" id="animation-speed" min="0.1" max="3" step="0.1" value="1">
            </div>
            <div class="control-group">
                <button id="play-pause">Pause</button>
            </div>
        </div>
        <script>
            let animationFrameId;
            let isPlaying = true;
            let currentTime = 0;
            let trailLength = 300;
            let animationSpeed = 1;
            
            // Control handlers
            document.getElementById('trail-length').addEventListener('input', (e) => {
                trailLength = parseInt(e.target.value);
                document.getElementById('trail-value').textContent = trailLength;
                updateLayer();
            });
            
            document.getElementById('animation-speed').addEventListener('input', (e) => {
                animationSpeed = parseFloat(e.target.value);
                document.getElementById('speed-value').textContent = animationSpeed + 'x';
            });
            
            document.getElementById('play-pause').addEventListener('click', (e) => {
                isPlaying = !isPlaying;
                e.target.textContent = isPlaying ? 'Pause' : 'Play';
                if (isPlaying) {
                    animate();
                } else {
                    cancelAnimationFrame(animationFrameId);
                }
            });
            
            function updateLayer() {
                deck.setProps({
                    layers: [
                        new deck.TripsLayer({
                            ...deck.props.layers[0].props,
                            currentTime: currentTime,
                            trailLength: trailLength
                        })
                    ]
                });
            }
            
            function animate() {
                const loopLength = 30000;
                const timestamp = Date.now() / 1000;
                const loopTime = loopLength / animationSpeed;
                currentTime = ((timestamp % loopTime) / loopTime) * loopLength;
                
                updateLayer();
                
                if (isPlaying) {
                    animationFrameId = window.requestAnimationFrame(animate);
                }
            }
            
            animate();
        </script>
    </body>
    </html>
    """

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style='dark',
        parameters={"animate": True}
    )

    return deck, html_template

def main():
    logger.info("Starting trip visualization creation...")
    try:
        deck, html_template = create_trip_layer()
        output_path = os.path.join(OUTPUT_DIR, "trip_visualization.html")
        
        # Combine deck's HTML with our template
        html_content = deck.to_html(as_string=True)
        final_html = html_template.replace('<body>', f'<body>{html_content}')
        
        with open(output_path, 'w') as f:
            f.write(final_html)
            
        logger.info(f"Visualization saved to: {output_path}")
        
    except Exception as e:
        logger.error(f"Error creating visualization: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 