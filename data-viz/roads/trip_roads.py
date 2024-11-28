import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import logging
from config import BUILDINGS_FILE
from shapely.geometry import Point
from pyproj import Transformer
import re
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR

POI_RADIUS = 0.0018  # about 200 meters in decimal degrees

# Update POI_INFO with even more contrasting colors and darker base buildings
POI_INFO = {
    'BGU': {'color': [0, 255, 90, 200], 'lat': 31.2614375, 'lon': 34.7995625},         # Brighter neon green
    'Gav Yam': {'color': [0, 191, 255, 200], 'lat': 31.2641875, 'lon': 34.8128125},    # Deep sky blue
    'Soroka Hospital': {'color': [170, 0, 255, 200], 'lat': 31.2579375, 'lon': 34.8003125}  # Deep purple
}

def load_trip_data():
    """Load and process trip data for animation"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    logger.info(f"Loading trip data from: {file_path}")
    
    try:
        trips_gdf = gpd.read_file(file_path)
        raw_trip_count = trips_gdf['num_trips'].sum()
        logger.info(f"Loaded {len(trips_gdf)} routes representing {raw_trip_count:,} total trips")
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise
    
    # Calculate center coordinates
    total_bounds = trips_gdf.total_bounds
    center_lon = (total_bounds[0] + total_bounds[2]) / 2
    center_lat = (total_bounds[1] + total_bounds[3]) / 2
    
    # Convert to format needed for animation
    trips_data = []
    processed_trips = 0
    
    # Animation parameters
    frames_per_second = 60
    desired_duration_seconds = 60  # one minute
    animation_duration = frames_per_second * desired_duration_seconds  # 3600 frames
    route_start_offset_max = 100  # Smaller offset for more density
    
    logger.info(f"Animation Configuration:")
    logger.info(f"  - Frames per second: {frames_per_second}")
    logger.info(f"  - Desired duration: {desired_duration_seconds} seconds")
    logger.info(f"  - Total frames: {animation_duration}")
    
    for idx, row in trips_gdf.iterrows():
        try:
            coords = list(row.geometry.coords)
            trip_duration = len(coords)
            num_trips = int(row['num_trips'])
            
            if num_trips <= 0 or trip_duration < 2:
                logger.warning(f"Skipping route {idx} with {num_trips} trips and {trip_duration} points")
                continue
                
            processed_trips += num_trips
            route_offset = np.random.randint(0, route_start_offset_max)
            
            # Ensure we can fit all trips within the animation duration
            interval = max(1, min(20, (animation_duration - trip_duration) // max(num_trips, 1)))
            
            # Generate individual timestamps for each trip instance
            timestamps = []
            for i in range(trip_duration):
                point_times = []
                for trip_num in range(num_trips):
                    # Calculate base timestamp for this point in this trip instance
                    timestamp = (trip_num * interval + i + route_offset) % animation_duration
                    point_times.append(timestamp)
                timestamps.append(point_times)
            
            trips_data.append({
                'path': [[float(x), float(y)] for x, y in coords],
                'timestamps': timestamps,
                'num_trips': num_trips
            })
            
        except Exception as e:
            logger.error(f"Error processing trip {idx}: {str(e)}")
            continue
    
    # Add detailed logging
    total_instances = sum(len(trip['timestamps'][0]) for trip in trips_data)
    logger.info(f"Animation Statistics:")
    logger.info(f"  - Animation duration: {animation_duration} frames")
    logger.info(f"  - Average interval between trips: {animation_duration / max(total_instances, 1):.1f}")
    logger.info(f"  - Total trip instances being animated: {total_instances:,}")
    
    return trips_data, center_lat, center_lon, processed_trips

def load_building_data():
    """Load building data for 3D visualization"""
    file_path = os.path.join(OUTPUT_DIR, "buildings.geojson")
    logger.info(f"Loading building data from: {file_path}")
    
    try:
        buildings_gdf = gpd.read_file(BUILDINGS_FILE)
        
        # Convert to format needed for deck.gl
        buildings_data = []
        text_features = []
        
        # Create a transformer for POI coordinates
        transformer = Transformer.from_crs("EPSG:4326", buildings_gdf.crs, always_xy=True)
        
        for idx, building in buildings_gdf.iterrows():
            building_color = [80, 90, 100, 160]  # Default color
            try:
                # Get actual height from building data, default to 20 if not found
                height = float(building.get('height', 20))
                building_height = height * 1.5  # Scale height to match line_roads.py
                
                # Check if building is within radius of main POIs
                for poi_name, info in POI_INFO.items():
                    poi_x, poi_y = transformer.transform(info['lon'], info['lat'])
                    poi_point = Point(poi_x, poi_y)
                    
                    if building.geometry.centroid.distance(poi_point) <= POI_RADIUS:
                        building_height = min(40, height * 1000)  # Match line_roads.py height scaling
                        building_color = info['color']
                        
                        # Add text label for POI
                        text_features.append({
                            "position": [poi_x, poi_y, building_height + 10],
                            "text": poi_name,
                            "color": [255, 255, 255, 255]  # Bright white text
                        })
                        break
                
                buildings_data.append({
                    "polygon": list(building.geometry.exterior.coords),
                    "height": building_height,
                    "color": building_color
                })
            except Exception as e:
                logger.error(f"Skipping building due to error: {e}")
                continue
        
        logger.info(f"Loaded {len(buildings_data)} buildings")
        return buildings_data, text_features
    except Exception as e:
        logger.error(f"Error loading building data: {str(e)}")
        raise

def create_animation():
    trips_data, center_lat, center_lon, total_trips = load_trip_data()
    buildings_data, text_features = load_building_data()
    
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
                background: #000000;
                padding: 12px;
                border-radius: 5px;
                color: #FFFFFF;
                font-family: Arial;
            }
            .methodology-container {
                position: fixed;
                top: 20px;
                right: 20px;
                background: #000000;
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
        <div class="methodology-container">
            <h3 style="margin: 0 0 10px 0;">Methodology</h3>
            <p style="margin: 0; font-size: 0.9em;">
                Represents individual trips across Beer Sheva's road network to POI in the Innovation District using approximate origin locations.<br>
                Total Daily Trips Visualized: %(total_trips)d<br><br>
                Colors indicate destinations:<br>
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 255, 90); vertical-align: middle;"></span> BGU <br>
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 191, 255); vertical-align: middle;"></span> Gav Yam <br>
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(170, 0, 255); vertical-align: middle;"></span> Soroka Hospital<br><br>
                Note: The base map darkness can be adjusted by modifying the OVERLAY_OPACITY constant in the code.
            </p>
        </div>
        <script>
            // Define WebGL constants
            const GL = {
                SRC_ALPHA: 0x0302,
                ONE_MINUS_SRC_ALPHA: 0x0303,
                FUNC_ADD: 0x8006
            };
            
            const TRIPS_DATA = %(trips_data)s;
            const BUILDINGS_DATA = %(buildings_data)s;
            const POI_RADIUS = %(poi_radius)f;
            const BGU_INFO = %(bgu_info)s;
            const GAV_YAM_INFO = %(gav_yam_info)s;
            const SOROKA_INFO = %(soroka_info)s;
            const ANIMATION_DURATION = %(animation_duration)d;
            const LOOP_LENGTH = %(loopLength)d;
            
            const ambientLight = new deck.AmbientLight({
                color: [255, 255, 255],
                intensity: 1.0
            });

            const pointLight = new deck.PointLight({
                color: [255, 255, 255],
                intensity: 2.0,
                position: [34.8, 31.25, 8000]  // Adjusted for Beer Sheva coordinates
            });

            const lightingEffect = new deck.LightingEffect({ambientLight, pointLight});
            
            const INITIAL_VIEW_STATE = {
                longitude: 34.8113,  // Ben Gurion University
                latitude: 31.2627,   // Ben Gurion University
                zoom: 13,
                pitch: 60,          // Increased pitch for better 3D view
                bearing: 0
            };
            
            // Update map style to CARTO dark matter (no labels)
            const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json';
            
            let trailLength = 2;
            let animationSpeed = 4;
            let animation;
            
            // Add a new constant for the overlay opacity
            const OVERLAY_OPACITY = 0.5; // Adjust this value to control darkness (0 to 1)
            
            const deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: MAP_STYLE,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true,
                effects: [lightingEffect],
                parameters: {
                    clearColor: [0, 0, 0, 1]  // Black background
                }
            });
            
            // Update color function for higher contrast
            const getPathColor = (path) => {
                const destination = path[path.length - 1];
                const [destLon, destLat] = destination;
                
                const distToBGU = Math.hypot(destLon - BGU_INFO.lon, destLat - BGU_INFO.lat);
                const distToGavYam = Math.hypot(destLon - GAV_YAM_INFO.lon, destLat - GAV_YAM_INFO.lat);
                const distToSoroka = Math.hypot(destLon - SOROKA_INFO.lon, destLat - SOROKA_INFO.lat);
                
                if (distToBGU < POI_RADIUS) return [0, 255, 90];      // Brighter neon green
                if (distToGavYam < POI_RADIUS) return [0, 191, 255];  // Deep sky blue
                if (distToSoroka < POI_RADIUS) return [170, 0, 255];  // Deep purple
                
                return [253, 128, 93];  // Default color
            };
            
            // Update TripsLayer configuration
            const tripsLayer = new deck.TripsLayer({
                id: 'trips',
                data: TRIPS_DATA,
                getPath: d => d.path,
                getTimestamps: d => d.timestamps.flat(),
                getColor: getPathColor,
                opacity: 0.8,
                widthMinPixels: 2,
                rounded: true,
                trailLength,
                currentTime: 0
            });
            function animate() {
                console.log('Animation Configuration:', {
                    totalFrames: LOOP_LENGTH,
                    baseSpeed: animationSpeed,
                    actualDurationSeconds: (LOOP_LENGTH * 60) / animationSpeed / 60,
                    trailLength
                });

                let lastTime = 0;
                let activeTripsCount = 0;
                
                animation = popmotion.animate({
                    from: 0,
                    to: LOOP_LENGTH,
                    duration: (LOOP_LENGTH * 60) / animationSpeed,
                    repeat: Infinity,
                    onUpdate: time => {
                        if (Math.floor(time) % 60 === 0 && lastTime !== Math.floor(time)) {
                            lastTime = Math.floor(time);
                            activeTripsCount = TRIPS_DATA.reduce((sum, route) => {
                                return sum + route.timestamps[0].filter(t => 
                                    t <= time % ANIMATION_DURATION && 
                                    t > (time % ANIMATION_DURATION) - trailLength
                                ).length;
                            }, 0);
                            
                            console.log('Animation Status:', {
                                frame: Math.floor(time),
                                activeTrips: activeTripsCount,
                                currentTrailLength: trailLength,
                                currentSpeed: animationSpeed,
                                totalTripsLoaded: TRIPS_DATA.reduce((sum, route) => sum + route.num_trips, 0)
                            });
                        }
                        
                        const layers = [
                            // Add a new PolygonLayer for the dark overlay
                            new deck.PolygonLayer({
                                id: 'dark-overlay',
                                data: [{
                                    contour: [
                                        [INITIAL_VIEW_STATE.longitude - 1, INITIAL_VIEW_STATE.latitude - 1],
                                        [INITIAL_VIEW_STATE.longitude + 1, INITIAL_VIEW_STATE.latitude - 1],
                                        [INITIAL_VIEW_STATE.longitude + 1, INITIAL_VIEW_STATE.latitude + 1],
                                        [INITIAL_VIEW_STATE.longitude - 1, INITIAL_VIEW_STATE.latitude + 1]
                                    ]
                                }],
                                getPolygon: d => d.contour,
                                getFillColor: [0, 0, 0, 255 * OVERLAY_OPACITY],
                                getLineColor: [0, 0, 0, 0],
                                extruded: false,
                                pickable: false,
                                opacity: 1,
                                zIndex: 0 // Ensure this layer is below others
                            }),
                            new deck.PolygonLayer({
                                id: 'buildings',
                                data: BUILDINGS_DATA,
                                extruded: true,
                                wireframe: true,
                                opacity: 0.8,
                                getPolygon: d => d.polygon,
                                getElevation: d => d.height,
                                getFillColor: d => d.color[3] === 200 ? d.color : [20, 20, 25, 160],  // Much darker for non-POI buildings
                                getLineColor: [255, 255, 255, 30],  // Dimmer wireframe
                                lineWidthMinPixels: 1,
                                material: {
                                    ambient: 0.2,
                                    diffuse: 0.8,
                                    shininess: 32,
                                    specularColor: [60, 64, 70]
                                }
                            }),
                            new deck.TripsLayer({
                                id: 'trips',
                                data: TRIPS_DATA,
                                getPath: d => d.path,
                                getTimestamps: d => {
                                    const currentTime = time % ANIMATION_DURATION;
                                    return d.timestamps.map(times => {
                                        const validTimes = times.filter(t => 
                                            t <= currentTime && 
                                            t > currentTime - trailLength
                                        );
                                        return validTimes.length > 0 ? validTimes[0] : null;
                                    });
                                },
                                getColor: d => getPathColor(d.path),
                                opacity: 0.8,
                                widthMinPixels: 2,
                                jointRounded: true,
                                capRounded: true,
                                trailLength,
                                currentTime: time % ANIMATION_DURATION,
                                updateTriggers: {
                                    getTimestamps: [time, trailLength]
                                }
                            })
                        ];
                        
                        deckgl.setProps({
                            layers
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
    
    # First, let's fix the JavaScript modulo operations by replacing % with %%
    html_template = re.sub(
        r'(?<![%])%(?![(%sd])',  # Match single % not followed by formatting specifiers
        '%%',                     # Replace with %%
        html_template
    )
    
    # Create a dictionary of all the values we need to format
    format_values = {
        'total_trips': total_trips,
        'trips_data': json.dumps(trips_data),
        'buildings_data': json.dumps(buildings_data),
        'poi_radius': POI_RADIUS,
        'bgu_info': json.dumps(POI_INFO['BGU']),
        'gav_yam_info': json.dumps(POI_INFO['Gav Yam']),
        'soroka_info': json.dumps(POI_INFO['Soroka Hospital']),
        'animation_duration': 3600,
        'loopLength': 3600,
        'mapbox_api_key': MAPBOX_API_KEY
    }
    
    try:
        # Format the HTML
        formatted_html = html_template % format_values
        
        # Write to file
        output_path = os.path.join(OUTPUT_DIR, "trip_animation.html")
        with open(output_path, 'w') as f:
            f.write(formatted_html)
            
        logger.info(f"Animation saved to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error writing HTML file: {str(e)}")
        # Show a small section of the template around each format specifier
        for match in re.finditer(r'%\([^)]+\)[sdfg]', html_template):
            start = max(0, match.start() - 20)
            end = min(len(html_template), match.end() + 20)
            logger.error(f"Context around format specifier: ...{html_template[start:end]}...")
        raise
        
if __name__ == "__main__":
    try:
        output_file = create_animation()
        print(f"Animation saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to create animation: {str(e)}")
        sys.exit(1) 