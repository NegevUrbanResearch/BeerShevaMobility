import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
import json
import logging
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR, BUILDINGS_FILE
from animation_components.animation_helpers import (
    validate_animation_data, 
    load_temporal_distributions,
    apply_temporal_distribution,
    debug_file_paths
)
from animation_components.js_modules import get_base_layers_js, get_animation_js
from trip_roads import load_trip_data, load_building_data

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# POI information
POI_INFO = {
    'BGU': {'color': [0, 255, 90, 200], 'lat': 31.2614375, 'lon': 34.7995625},
    'Gav Yam': {'color': [0, 191, 255, 200], 'lat': 31.2641875, 'lon': 34.8128125},
    'Soroka Hospital': {'color': [170, 0, 255, 200], 'lat': 31.2579375, 'lon': 34.8003125}
}

def create_time_based_animation():
    """Create animation with time-based distribution of trips"""
    try:
        # Debug file paths
        debug_file_paths(OUTPUT_DIR)
        
        # Load base data
        logger.info("Loading base data...")
        trips_data, center_lat, center_lon, total_trips = load_trip_data()
        buildings_data, text_features, poi_borders, poi_fills = load_building_data()
        
        # Load temporal distributions for each POI
        logger.info("Loading temporal distributions...")
        temporal_dists = {
            'BGU': load_temporal_distributions('Ben-Gurion-University'),
            'Gav Yam': load_temporal_distributions('Gav-Yam-High-Tech-Park'),
            'Soroka Hospital': load_temporal_distributions('Soroka-Medical-Center')
        }
        
        # Check if temporal distributions were loaded successfully
        if not all(temporal_dists.values()):
            raise ValueError("Failed to load temporal distributions for all POIs")
        
        # Apply temporal distributions to trips
        logger.info("Applying temporal distributions...")
        trips_data = apply_temporal_distribution(trips_data, temporal_dists, POI_INFO)
        
        # Validate data
        logger.info("Validating animation data...")
        if not validate_animation_data(trips_data, buildings_data, poi_borders, poi_fills):
            raise ValueError("Animation data validation failed")
        
        # Get JavaScript components
        logger.info("Preparing JavaScript components...")
        base_layers_js = get_base_layers_js()
        animation_js = get_animation_js()
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset='utf-8'>
            <title>Time-Based Trip Animation</title>
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
                    background: #000000;
                    padding: 12px;
                    border-radius: 5px;
                    color: #FFFFFF;
                    font-family: Arial;
                }
                .time-control {
                    position: absolute;
                    bottom: 20px;
                    left: 50%%;
                    transform: translateX(-50%%);
                    background: #000000;
                    padding: 12px;
                    border-radius: 5px;
                    color: #FFFFFF;
                    font-family: Arial;
                    text-align: center;
                }
                #time-display {
                    display: block;
                    font-size: 1.2em;
                    margin-top: 5px;
                }
            </style>
        </head>
        <body>
            <div id="container"></div>
            <div class="control-panel">
                <div>
                    <label>Trail Length: <span id="trail-value">2</span></label>
                    <input type="range" min="1" max="100" value="2" id="trail-length" style="width: 200px">
                </div>
                <div>
                    <label>Animation Speed: <span id="speed-value">4</span></label>
                    <input type="range" min="0.1" max="5" step="0.1" value="4" id="animation-speed" style="width: 200px">
                </div>
            </div>
            <div class="time-control">
                <input type="range" min="0" max="23" value="0" id="time-slider" style="width: 300px">
                <span id="time-display">00:00</span>
            </div>
            <script>
                // Initialize global variables
                let animation;
                let animationSpeed = 4;
                let trailLength = 2;
                let deckgl;

                // Initialize deck.gl
                deckgl = new deck.DeckGL({
                    container: 'container',
                    initialViewState: {
                        longitude: %(center_lon)f,
                        latitude: %(center_lat)f,
                        zoom: 13,
                        pitch: 45,
                        bearing: 0
                    },
                    controller: true,
                    getTooltip: ({object}) => object && {
                        html: `<div>Trips: ${object.num_trips}</div>`,
                        style: {
                            backgroundColor: '#000',
                            color: '#fff'
                        }
                    },
                    layers: []
                });

                const TRIPS_DATA = %(trips_data)s;
                const BUILDINGS_DATA = %(buildings_data)s;
                const POI_BORDERS = %(poi_borders)s;
                const POI_FILLS = %(poi_fills)s;
                const POI_RADIUS = %(poi_radius)f;
                const BGU_INFO = %(bgu_info)s;
                const GAV_YAM_INFO = %(gav_yam_info)s;
                const SOROKA_INFO = %(soroka_info)s;
                
                %(base_layers_js)s
                %(animation_js)s
                
                // Time control logic
                const FRAMES_PER_HOUR = 150;
                const TOTAL_FRAMES = FRAMES_PER_HOUR * 24;
                
                document.getElementById('time-slider').oninput = function() {
                    const hour = parseInt(this.value);
                    document.getElementById('time-display').textContent = 
                        `${hour.toString().padStart(2, '0')}:00`;
                        
                    // Update animation frame
                    const frameStart = hour * FRAMES_PER_HOUR;
                    if (animation) {
                        animation.stop();
                    }
                    animate(frameStart);
                };
                
                function animate(startFrame = 0) {
                    if (animation) {
                        animation.stop();
                    }
                    
                    animation = popmotion.animate({
                        from: startFrame,
                        to: startFrame + FRAMES_PER_HOUR,
                        duration: FRAMES_PER_HOUR / animationSpeed * 1000,
                        repeat: Infinity,
                        onUpdate: time => {
                            const layers = [
                                createBuildingsLayer(),
                                ...createPOILayers(),
                                createTripsLayer(time, trailLength)
                            ];
                            
                            deckgl.setProps({ layers });
                        }
                    });
                }

                // Event handlers for controls
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
                
                // Initialize animation
                animate();
            </script>
        </body>
        </html>
        """
        
        # Format template with data
        format_values = {
            'trips_data': json.dumps(trips_data),
            'buildings_data': json.dumps(buildings_data),
            'poi_borders': json.dumps(poi_borders),
            'poi_fills': json.dumps(poi_fills),
            'poi_radius': 0.0018,
            'bgu_info': json.dumps(POI_INFO['BGU']),
            'gav_yam_info': json.dumps(POI_INFO['Gav Yam']),
            'soroka_info': json.dumps(POI_INFO['Soroka Hospital']),
            'base_layers_js': base_layers_js,
            'animation_js': animation_js,
            'center_lat': center_lat,
            'center_lon': center_lon
        }
        
        try:
            # Format the HTML
            formatted_html = html_template % format_values
            
            # Write to file
            output_path = Path(OUTPUT_DIR) / "trip_animation_time.html"
            with open(output_path, 'w') as f:
                f.write(formatted_html)
                
            logger.info(f"Time-based animation saved to: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error writing HTML file: {str(e)}")
            raise
    except Exception as e:
        logger.error(f"Error creating time-based animation: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        output_file = create_time_based_animation()
        print(f"Time-based animation saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to create time-based animation: {str(e)}")
        sys.exit(1)
