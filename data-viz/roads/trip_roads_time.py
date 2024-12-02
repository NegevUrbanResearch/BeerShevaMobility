import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
import json
import logging
from pathlib import Path
import re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR, BUILDINGS_FILE
from animation_components.animation_helpers import (
    validate_animation_data, 
    load_temporal_distributions,
    apply_temporal_distribution,
    debug_file_paths,
    validate_js_template
)
from animation_components.js_modules import get_base_layers_js, get_animation_js
from trip_roads import load_trip_data, load_building_data
POI_RADIUS = 0.0018
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
                    background: rgba(0, 0, 0, 0.8);
                    padding: 12px;
                    border-radius: 5px;
                    color: #FFFFFF;
                    font-family: Arial;
                }
                .time-display {
                    position: absolute;
                    bottom: 20px;
                    left: 50%%;
                    transform: translateX(-50%%);
                    background: rgba(0, 0, 0, 0.8);
                    padding: 12px;
                    border-radius: 5px;
                    color: #FFFFFF;
                    font-family: Arial;
                }
                .methodology-container {
                    position: absolute;
                    bottom: 20px;
                    right: 20px;
                    background: rgba(0, 0, 0, 0.8);
                    padding: 12px;
                    border-radius: 5px;
                    color: #FFFFFF;
                    font-family: Arial;
                    max-width: 300px;
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
            <div class="time-display">
                <span id="time-display">00:00</span>
            </div>
            <div class="methodology-container">
                <h3>Methodology</h3>
                <p>Represents individual trips across Beer Sheva's road network to POIs in the Innovation District.<br>
                Total Daily Trips: %(total_trips)d</p>
            </div>
            <script>
                // Constants and Data
                const TRIPS_DATA = %(trips_data)s;
                const BUILDINGS_DATA = %(buildings_data)s;
                const POI_BORDERS = %(poi_borders)s;
                const POI_FILLS = %(poi_fills)s;
                const POI_RADIUS = %(poi_radius)f;
                const BGU_INFO = %(bgu_info)s;
                const GAV_YAM_INFO = %(gav_yam_info)s;
                const SOROKA_INFO = %(soroka_info)s;
                const ANIMATION_DURATION = %(animation_duration)d;
                const FRAMES_PER_HOUR = %(frames_per_hour)d;
                const TOTAL_FRAMES = %(loopLength)d;

                // Base layers and animation setup
                %(base_layers_js)s
                %(animation_js)s

                // Initialize variables
                let animation;
                let animationSpeed = 4;
                let trailLength = 2;
                let deckgl;

                // Initialize deck.gl
                deckgl = new deck.DeckGL({
                    container: 'container',
                    mapStyle: 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
                    initialViewState: {
                        longitude: %(center_lon)f,
                        latitude: %(center_lat)f,
                        zoom: 13,
                        pitch: 45,
                        bearing: 0
                    },
                    controller: true
                });

                function createLayers(currentTime) {
                    return [
                        // Buildings layer
                        new deck.PolygonLayer({
                            id: 'buildings',
                            data: BUILDINGS_DATA,
                            extruded: true,
                            wireframe: true,
                            opacity: 0.9,
                            getPolygon: d => d.polygon,
                            getElevation: d => d.height,
                            getFillColor: d => d.color,
                            getLineColor: [255, 255, 255, 30],
                            lineWidthMinPixels: 1,
                            material: {
                                ambient: 0.2,
                                diffuse: 0.8,
                                shininess: 32,
                                specularColor: [60, 64, 70]
                            }
                        }),

                        // POI fills
                        new deck.PolygonLayer({
                            id: 'poi-fills',
                            data: POI_FILLS,
                            getPolygon: d => d.polygon,
                            getFillColor: d => d.color,
                            extruded: false,
                            pickable: false,
                            opacity: 0.3
                        }),

                        // POI borders
                        new deck.PolygonLayer({
                            id: 'poi-borders',
                            data: POI_BORDERS,
                            getPolygon: d => d.polygon,
                            getLineColor: d => d.color,
                            lineWidthMinPixels: 2,
                            extruded: false,
                            pickable: false,
                            opacity: 1
                        }),

                        // Trips layer
                        new deck.TripsLayer({
                            id: 'trips',
                            data: TRIPS_DATA,
                            getPath: d => d.path,
                            getTimestamps: d => d.timestamps.flat(),
                            getColor: d => getPathColor(d.path),
                            opacity: 0.8,
                            widthMinPixels: 2,
                            jointRounded: true,
                            capRounded: true,
                            trailLength,
                            currentTime
                        })
                    ];
                }
                function animate() {
                    if (animation) {
                        animation.stop();
                    }
                    animation = popmotion.animate({
                        from: 0,
                        to: TOTAL_FRAMES,
                        duration: TOTAL_FRAMES * 1000 / animationSpeed,
                        repeat: Infinity,
                        onUpdate: time => {
                            const hour = Math.floor((time %% TOTAL_FRAMES) / FRAMES_PER_HOUR);
                            const minute = Math.floor(((time %% TOTAL_FRAMES) %% FRAMES_PER_HOUR) / (FRAMES_PER_HOUR/60));
                            document.getElementById('time-display').textContent = 
                                `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
                            
                            deckgl.setProps({
                                layers: createLayers(time)
                            });
                        }
                    });

                    return animation;
                }

                // Event handlers
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
                    animation = animate();
                };

                // Start animation
                animation = animate();
            </script>
        </body>
        </html>
        """
        
        # Calculate animation parameters
        frames_per_hour = 150
        total_frames = frames_per_hour * 24
        animation_duration = total_frames  # 3600 frames total
        
        # Format values for the template
        format_values = {
            'trips_data': json.dumps(trips_data),
            'buildings_data': json.dumps(buildings_data),
            'poi_borders': json.dumps(poi_borders),
            'poi_fills': json.dumps(poi_fills),
            'poi_radius': POI_RADIUS,
            'bgu_info': json.dumps(POI_INFO['BGU']),
            'gav_yam_info': json.dumps(POI_INFO['Gav Yam']),
            'soroka_info': json.dumps(POI_INFO['Soroka Hospital']),
            'animation_duration': animation_duration,
            'loopLength': total_frames,
            'center_lon': center_lon,
            'center_lat': center_lat,
            'base_layers_js': base_layers_js,
            'animation_js': animation_js,
            'frames_per_hour': frames_per_hour,
            'total_trips': total_trips
        }

        # Validate template and format values
        logger.info("Validating JavaScript template...")
        if not validate_js_template(html_template, format_values):
            raise ValueError("Template validation failed")

        try:
            # Debug format values
            logger.debug("\nFormat Values:")
            for key, value in format_values.items():
                if isinstance(value, str) and len(value) > 100:
                    logger.debug(f"{key}: <large string, length {len(value)}>")
                else:
                    logger.debug(f"{key}: {value}")

            # Format the HTML with error handling
            try:
                formatted_html = html_template % format_values
            except KeyError as e:
                logger.error(f"Missing format key: {e}")
                raise
            except ValueError as e:
                logger.error(f"Format value error: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected formatting error: {e}")
                raise

            # Write to file
            output_path = os.path.join(OUTPUT_DIR, "trip_animation_time.html")
            with open(output_path, 'w') as f:
                f.write(formatted_html)
            
            # Validate output file
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"Animation file created: {output_path} ({file_size/1024:.1f} KB)")
            else:
                raise FileNotFoundError("Output file was not created")

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
