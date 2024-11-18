import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR

def load_trip_data():
    """Load and process trip data for animation"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    logger.info(f"Loading trip data from: {file_path}")
    
    try:
        trips_gdf = gpd.read_file(file_path)
        logger.info(f"Loaded {len(trips_gdf)} trips")
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise
    
    # Convert to format needed for animation
    trips_data = []
    for idx, row in trips_gdf.iterrows():
        try:
            coords = list(row.geometry.coords)
            timestamps = list(range(len(coords)))  # Create sequential timestamps
            
            # Format data to match the expected structure from the React example
            trip_data = {
                'vendor': 0,
                'path': [[float(x), float(y)] for x, y in coords],
                'timestamps': timestamps,
                'trips': int(row['num_trips'])
            }
            trips_data.append(trip_data)
            
            if idx == 0:  # Log first trip for debugging
                logger.debug(f"Sample trip data: {json.dumps(trip_data, indent=2)}")
                
        except Exception as e:
            logger.error(f"Error processing trip {idx}: {str(e)}")
            continue
    
    # Get bounds for view state
    bounds = trips_gdf.total_bounds
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    
    logger.info(f"Processed {len(trips_data)} trips")
    logger.info(f"Center coordinates: {center_lat}, {center_lon}")
    
    return trips_data, center_lat, center_lon

def create_animation():
    trips_data, center_lat, center_lon = load_trip_data()
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'>
        <title>Trip Animation</title>
        <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
        <script src='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js'></script>
        <script src='https://unpkg.com/popmotion@11.0.0/dist/popmotion.js'></script>
        <link href='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css' rel='stylesheet' />
        <style>
            body { margin: 0; padding: 0; }
            #container { width: 100vw; height: 100vh; position: relative; }
            .control-panel {
                position: absolute;
                top: 20px;
                left: 20px;
                background: white;
                padding: 10px;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div class="control-panel">
            <div>
                <label>Trail Length: <span id="trail-value">30</span></label>
                <input type="range" min="1" max="100" value="30" id="trail-length" style="width: 200px">
            </div>
            <div>
                <label>Animation Speed: <span id="speed-value">1</span></label>
                <input type="range" min="0.1" max="5" step="0.1" value="1" id="animation-speed" style="width: 200px">
            </div>
        </div>
        <script>
            const DATA = %s;
            const INITIAL_VIEW_STATE = {
                longitude: %f,
                latitude: %f,
                zoom: 11,
                pitch: 45,
                bearing: 0
            };
            
            const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json';
            
            let trailLength = 30;
            let animationSpeed = 1;
            const loopLength = 1800;
            let animation;
            
            const deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: MAP_STYLE,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true
            });
            
            function animate() {
                animation = popmotion.animate({
                    from: 0,
                    to: loopLength,
                    duration: (loopLength * 60) / animationSpeed,
                    repeat: Infinity,
                    onUpdate: time => {
                        const layer = new deck.TripsLayer({
                            id: 'trips',
                            data: DATA,
                            getPath: d => d.path,
                            getTimestamps: d => d.timestamps,
                            getColor: [253, 128, 93],
                            opacity: 0.3,
                            widthMinPixels: 2,
                            rounded: true,
                            trailLength,
                            currentTime: time
                        });
                        
                        deckgl.setProps({
                            layers: [layer]
                        });
                    }
                });
            }
            
            // Control panel handlers
            document.getElementById('trail-length').oninput = function() {
                trailLength = Number(this.value);
                document.getElementById('trail-value').textContent = this.value;
            };
            
            document.getElementById('animation-speed').oninput = function() {
                animationSpeed = Number(this.value);
                document.getElementById('speed-value').textContent = this.value;
                if (animation) {
                    animation.stop();
                }
                animate();
            };
            
            animate();
        </script>
    </body>
    </html>
    """
    
    # Generate the HTML file
    output_path = os.path.join(OUTPUT_DIR, "trip_animation.html")
    try:
        with open(output_path, 'w') as f:
            f.write(html_template % (
                json.dumps(trips_data),
                center_lon,
                center_lat
            ))
        logger.info(f"Animation saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error writing HTML file: {str(e)}")
        raise
    
    return output_path

if __name__ == "__main__":
    try:
        output_file = create_animation()
        print(f"Animation saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to create animation: {str(e)}")
        sys.exit(1) 