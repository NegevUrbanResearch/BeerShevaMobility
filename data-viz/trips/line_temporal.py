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


import re

HTML_TEMPLATE = """
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
            .time-display {
                position: absolute;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 12px 24px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 24px;
                z-index: 1000;
            }
            .trip-counters {
                margin-top: 10px;
                font-family: monospace;
            }
            .counter-row {
                margin: 5px 0;
                display: flex;
                align-items: center;
                gap: 8px;
            }
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div class="control-panel">
            <div>
                <label>Trail Length: <span id="trail-value">4</span></label>
                <input type="range" min="1" max="100" value="4" id="trail-length" style="width: 200px">
            </div>
            <div>
                <label>Animation Speed: <span id="speed-value">4</span></label>
                <input type="range" min="0.5" max="10" step="0.5" value="4" id="animation-speed" style="width: 200px">
            </div>
        </div>
        <div class="time-display">06:00</div>
        <div class="methodology-container">
            <h3 style="margin: 0 0 10px 0;">Methodology</h3>
            <p style="margin: 0; font-size: 0.9em;">
                Represents daily trips (6:00-22:00) across Beer Sheva's road network using temporal distributions.<br>
                Total Daily Trips: %(total_trips)d<br>
                Current simulation time: <span id="current-time">06:00</span><br>
                <div class="trip-counters">
                    Cumulative Trips:<br>
                    <div class="counter-row">
                        <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 255, 90); vertical-align: middle;"></span>
                        BGU: <span id="bgu-counter">0</span>
                    </div>
                    <div class="counter-row">
                        <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 191, 255); vertical-align: middle;"></span>
                        Gav Yam: <span id="gav-yam-counter">0</span>
                    </div>
                    <div class="counter-row">
                        <span style="display: inline-block; width: 20px; height: 10px; background: rgb(170, 0, 255); vertical-align: middle;"></span>
                        Soroka: <span id="soroka-counter">0</span>
                    </div>
                </div>
            </p>
        </div>
        <script>
            // Global constants
            const GL = {
                SRC_ALPHA: 0x0302,
                ONE_MINUS_SRC_ALPHA: 0x0303,
                FUNC_ADD: 0x8006
            };
            
            const TRIPS_DATA = %(trips_data)s;
            const BUILDINGS_DATA = %(buildings_data)s;
            const POI_BORDERS = %(poi_borders)s;
            const POI_FILLS = %(poi_fills)s;
            const POI_RADIUS = %(poi_radius)f;
            const BGU_INFO = %(bgu_info)s;
            const GAV_YAM_INFO = %(gav_yam_info)s;
            const SOROKA_INFO = %(soroka_info)s;
            const ANIMATION_DURATION = %(animation_duration)d;
            const LOOP_LENGTH = %(loopLength)d;
            
            // Animation constants
            const HOURS_PER_DAY = 17;
            const START_HOUR = 6;
            const END_HOUR = 22;
            const FRAMES_PER_HOUR = ANIMATION_DURATION / HOURS_PER_DAY;
            const OVERLAY_OPACITY = 0.5;
            
            // Animation state
            let trailLength = 4;
            let animationSpeed = 4;
            let animation;
            let cumulativeTrips = {
                'BGU': 0,
                'Gav Yam': 0,
                'Soroka Hospital': 0
            };
            
            // Lighting setup
            const ambientLight = new deck.AmbientLight({
                color: [255, 255, 255],
                intensity: 1.0
            });
            
            const pointLight = new deck.PointLight({
                color: [255, 255, 255],
                intensity: 2.0,
                position: [34.8, 31.25, 8000]
            });
            
            const lightingEffect = new deck.LightingEffect({ambientLight, pointLight});
            
            // Initial view setup
            const INITIAL_VIEW_STATE = {
                longitude: 34.8113,
                latitude: 31.2627,
                zoom: 13,
                pitch: 60,
                bearing: 0
            };
            
            const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json';
            
            // Initialize deck.gl
            const deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: MAP_STYLE,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true,
                effects: [lightingEffect],
                parameters: {
                    clearColor: [0, 0, 0, 1]
                }
            });
            
            // Utility functions
            function formatTimeString(frame) {
                const hoursElapsed = frame / FRAMES_PER_HOUR;
                const currentHour = Math.floor(START_HOUR + hoursElapsed);
                const minutes = Math.floor((hoursElapsed % 1) * 60);
                return `${currentHour.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            }
            
            function getPathColor(path) {
                const destination = path[path.length - 1];
                const [destLon, destLat] = destination;
                
                const distToBGU = Math.hypot(destLon - BGU_INFO.lon, destLat - BGU_INFO.lat);
                const distToGavYam = Math.hypot(destLon - GAV_YAM_INFO.lon, destLat - GAV_YAM_INFO.lat);
                const distToSoroka = Math.hypot(destLon - SOROKA_INFO.lon, destLat - SOROKA_INFO.lat);
                
                if (distToBGU < POI_RADIUS) return [0, 255, 90];
                if (distToGavYam < POI_RADIUS) return [0, 191, 255];
                if (distToSoroka < POI_RADIUS) return [170, 0, 255];
                
                return [253, 128, 93];
            }
            
            function animate() {
                cumulativeTrips = {
                    'BGU': 0,
                    'Gav Yam': 0,
                    'Soroka Hospital': 0
                };

                console.log('Animation Configuration:', {
                    totalFrames: LOOP_LENGTH,
                    baseSpeed: animationSpeed,
                    actualDurationSeconds: LOOP_LENGTH / animationSpeed,
                    trailLength,
                    hoursSimulated: HOURS_PER_DAY,
                    framesPerHour: FRAMES_PER_HOUR
                });

                let lastTime = 0;
                let lastHour = -1;
                
                animation = popmotion.animate({
                    from: 0,
                    to: LOOP_LENGTH,
                    duration: (LOOP_LENGTH * 60) / animationSpeed,
                    repeat: Infinity,
                    onUpdate: time => {
                        const currentFrame = time % ANIMATION_DURATION;
                        const hoursElapsed = currentFrame / FRAMES_PER_HOUR;
                        const currentTime = formatTimeString(currentFrame);
                        const currentHour = Math.floor(START_HOUR + hoursElapsed);
                        
                        // Update displays
                        document.querySelector('.time-display').textContent = currentTime;
                        document.getElementById('current-time').textContent = currentTime;

                        // Process trips and update counters every frame
                        if (Math.floor(time) !== lastTime) {
                            lastTime = Math.floor(time);
                            
                            // Reset counts at the start of each loop
                            if (currentFrame === 0) {
                                cumulativeTrips = {
                                    'BGU': 0,
                                    'Gav Yam': 0,
                                    'Soroka Hospital': 0
                                };
                            }

                            // Count both active and new trips
                            let activeTrips = {
                                'BGU': 0,
                                'Gav Yam': 0,
                                'Soroka Hospital': 0
                            };
                            
                            TRIPS_DATA.forEach(route => {
                                const poi = route.poi;
                                if (poi) {
                                    // Count new trips for cumulative total
                                    const newTrips = route.timestamps[0].filter(t => 
                                        t <= currentFrame && 
                                        t > currentFrame - 1
                                    ).length;
                                    cumulativeTrips[poi] += newTrips;
                                    
                                    // Count currently active trips
                                    const currentlyActive = route.timestamps[0].filter(t => 
                                        t <= currentFrame && 
                                        t > currentFrame - trailLength
                                    ).length;
                                    activeTrips[poi] += currentlyActive;
                                }
                            });

                            // Update counter displays every frame
                            document.getElementById('bgu-counter').textContent = 
                                cumulativeTrips['BGU'].toLocaleString();
                            document.getElementById('gav-yam-counter').textContent = 
                                cumulativeTrips['Gav Yam'].toLocaleString();
                            document.getElementById('soroka-counter').textContent = 
                                cumulativeTrips['Soroka Hospital'].toLocaleString();
                            
                            // Log detailed stats every second
                            if (Math.floor(time) % 60 === 0) {
                                console.log('Animation Status:', {
                                    frame: Math.floor(currentFrame),
                                    time: currentTime,
                                    hour: currentHour,
                                    cumulativeTrips: {...cumulativeTrips},
                                    activeTrips: {...activeTrips},
                                    speed: animationSpeed
                                });
                            }
                        }
                        
                        // Update layers with optimized timestamp handling
                        deckgl.setProps({
                            layers: [
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
                                    zIndex: 0
                                }),
                                new deck.PolygonLayer({
                                    id: 'poi-fills',
                                    data: POI_FILLS,
                                    getPolygon: d => d.polygon,
                                    getFillColor: d => d.color,
                                    getLineColor: [0, 0, 0, 0],
                                    extruded: false,
                                    pickable: false,
                                    opacity: 0.3,
                                    zIndex: 1
                                }),
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
                                new deck.TripsLayer({
                                    id: 'trips',
                                    data: TRIPS_DATA,
                                    getPath: d => d.path,
                                    getTimestamps: d => {
                                        const validTimes = d.timestamps[0].filter(t => 
                                            t <= currentFrame && 
                                            t > currentFrame - trailLength
                                        );
                                        return validTimes.length > 0 ? [validTimes[0]] : [null];
                                    },
                                    getColor: d => getPathColor(d.path),
                                    opacity: 0.8,
                                    widthMinPixels: 2,
                                    jointRounded: true,
                                    capRounded: true,
                                    trailLength,
                                    currentTime: currentFrame,
                                    updateTriggers: {
                                        getTimestamps: [currentFrame, trailLength]
                                    }
                                }),
                                new deck.PolygonLayer({
                                    id: 'poi-borders',
                                    data: POI_BORDERS,
                                    getPolygon: d => d.polygon,
                                    getLineColor: d => d.color,
                                    lineWidthMinPixels: 2,
                                    extruded: false,
                                    pickable: false,
                                    opacity: 1,
                                    zIndex: 2
                                })
                            ],
                            parameters: {
                                blend: true,
                                blendFunc: [GL.SRC_ALPHA, GL.ONE_MINUS_SRC_ALPHA],
                                blendEquation: GL.FUNC_ADD
                            }
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

# Fix JavaScript modulo operations
HTML_TEMPLATE = re.sub(
    r'(?<![%])%(?![(%sd])',  # Match single % not followed by formatting specifiers
    '%%',                     # Replace with %%
    HTML_TEMPLATE
)
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR

attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]  # POI polygons
poi_polygons_json = poi_polygons.to_json()
POI_RADIUS = 0.0018  # about 200 meters in decimal degrees

# Update POI_INFO with even more contrasting colors and darker base buildings
POI_INFO = {
    'BGU': {'color': [0, 255, 90, 200], 'lat': 31.2614375, 'lon': 34.7995625},         # Brighter neon green
    'Gav Yam': {'color': [0, 191, 255, 200], 'lat': 31.2641875, 'lon': 34.8128125},    # Deep sky blue
    'Soroka Hospital': {'color': [170, 0, 255, 200], 'lat': 31.2579375, 'lon': 34.8003125}  # Deep purple
}

# Define the mapping between shapefile IDs and POI names
POI_ID_MAP = {
    7: 'BGU',
    12: 'Gav Yam',
    11: 'Soroka Hospital'
}
def load_temporal_distributions():
    """Load temporal distribution data for each POI"""
    logger.info("Loading temporal distributions")
    
    distributions = {}
    file_patterns = {
        'BGU': 'ben_gurion_university_inbound_temporal.csv',
        'Gav Yam': 'gav_yam_high_tech_park_inbound_temporal.csv',
        'Soroka Hospital': 'soroka-medical-center_inbound_temporal.csv'
    }
    
    for poi_name, filename in file_patterns.items():
        file_path = os.path.join(OUTPUT_DIR, filename)
        try:
            df = pd.read_csv(file_path)
            # Extract car distribution for business hours (6-23)
            dist = df[(df['hour'] >= 6) & (df['hour'] <= 23)]['car_dist'].values
            # Normalize to ensure sum is 1.0
            dist = dist / dist.sum()
            distributions[poi_name] = dist
            logger.info(f"Loaded distribution for {poi_name}: sum={dist.sum():.3f}")
        except Exception as e:
            logger.error(f"Error loading distribution for {poi_name}: {str(e)}")
            raise
            
    return distributions

def load_trip_data():
    """Load and process trip data for animation with temporal distribution"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    logger.info(f"Loading trip data from: {file_path}")
    
    try:
        trips_gdf = gpd.read_file(file_path)
        raw_trip_count = trips_gdf['num_trips'].sum()
        logger.info(f"Loaded {len(trips_gdf)} routes representing {raw_trip_count:,} total trips")
        
        # Load temporal distributions
        temporal_dist = load_temporal_distributions()
        
        # Calculate center coordinates
        total_bounds = trips_gdf.total_bounds
        center_lon = (total_bounds[0] + total_bounds[2]) / 2
        center_lat = (total_bounds[1] + total_bounds[3]) / 2
        
        # Animation parameters
        frames_per_second = 60
        hours_per_day = 18  # Updated to 18 hours (6:00-23:00)
        minutes_per_simulated_hour = 10  # Each hour takes 10 seconds to simulate
        frames_per_hour = frames_per_second * minutes_per_simulated_hour
        animation_duration = frames_per_hour * hours_per_day
        route_start_offset_max = 20  # Reduced for denser traffic
        
        logger.info(f"Animation Configuration:")
        logger.info(f"  - Hours simulated: {hours_per_day} (6:00-23:00)")
        logger.info(f"  - Seconds per hour: {minutes_per_simulated_hour}")
        logger.info(f"  - Frames per hour: {frames_per_hour}")
        logger.info(f"  - Total frames: {animation_duration}")
        
        trips_data = []
        processed_trips = 0
        hourly_trip_counts = {i: 0 for i in range(6, 24)}  # Track trips per hour (6:00-23:00)
        
        for idx, row in trips_gdf.iterrows():
            try:
                coords = list(row.geometry.coords)
                trip_duration = len(coords)
                num_trips = int(row['num_trips'])
                
                if num_trips <= 0 or trip_duration < 2:
                    continue
                    
                # Determine POI for this route
                dest_point = Point(coords[-1])
                poi_name = None
                for poi_poly_idx, poi_polygon in poi_polygons.iterrows():
                    if dest_point.distance(poi_polygon.geometry) < POI_RADIUS:
                        poi_name = POI_ID_MAP[int(poi_polygon['ID'])]
                        break
                    
                if not poi_name:
                    continue
                    
                processed_trips += num_trips
                
                # Generate timestamps with temporal distribution
                timestamps = []
                for i in range(trip_duration):
                    point_times = []
                    # In load_trip_data(), update the timestamp generation:
                    for hour_idx, dist_value in enumerate(temporal_dist[poi_name]):
                        current_hour = hour_idx + 6  # Convert to actual hour (6:00-23:00)
                        
                        # Calculate exact number of trips for this hour based on distribution
                        hour_trips = int(round(num_trips * dist_value))
                        
                        if hour_trips > 0:
                            hour_start = hour_idx * frames_per_hour
                            # Spread trips more evenly across the hour
                            interval = frames_per_hour / hour_trips
                            
                            for trip_num in range(hour_trips):
                                # Base time at even intervals
                                base_time = hour_start + (trip_num * interval)
                                # Add small random offset for more natural look
                                jitter = np.random.randint(-30, 30)  # Half-second jitter
                                timestamp = int(base_time + jitter)
                                # Ensure timestamp stays within current hour
                                timestamp = max(hour_start, min(hour_start + frames_per_hour - 1, timestamp))
                                point_times.append(timestamp)
                                
                                # Only count trips at their starting point
                                if i == 0:
                                    hourly_trip_counts[current_hour] += 1
                                    
                    timestamps.append(point_times)
                
                trips_data.append({
                    'path': [[float(x), float(y)] for x, y in coords],
                    'timestamps': timestamps,
                    'num_trips': num_trips,
                    'poi': poi_name
                })
                
            except Exception as e:
                logger.error(f"Error processing trip {idx}: {str(e)}")
                continue
        
        # Log hourly trip statistics
        logger.info("\nHourly Trip Distribution:")
        logger.info("-" * 40)
        total_instances = 0
        for hour in range(6, 24):
            count = hourly_trip_counts[hour]
            total_instances += count
            percentage = (count / sum(hourly_trip_counts.values()) * 100) if count > 0 else 0
            logger.info(f"{hour:02d}:00 - {count:5d} trips ({percentage:5.1f}%)")
        logger.info("-" * 40)
        logger.info(f"Total trip instances: {total_instances:,}")
        logger.info(f"Original trips processed: {processed_trips:,}")
        logger.info(f"Average instances per original trip: {total_instances/processed_trips:.1f}")
        
        return trips_data, center_lat, center_lon, processed_trips, animation_duration
        
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise


def load_building_data():
    """Load building data for 3D visualization"""
    file_path = os.path.join(OUTPUT_DIR, "buildings.geojson")
    logger.info(f"Loading building data from: {file_path}")
    
    try:
        buildings_gdf = gpd.read_file(BUILDINGS_FILE)
        
        # Convert to format needed for deck.gl
        buildings_data = []
        text_features = []
        
        # Debug logging for POI polygons
        logger.info(f"POI polygons IDs: {[p['ID'] for idx, p in poi_polygons.iterrows()]}")
        
        for idx, building in buildings_gdf.iterrows():
            building_color = [80, 90, 100, 160]  # Default color
            try:
                # Get actual height from building data, default to 20 if not found
                height = float(building.get('height', 20))
                building_height = height * 1.5  # Scale height to match line_roads.py
                
                # Check if building intersects with any POI polygon
                for poi_idx, poi_polygon in poi_polygons.iterrows():
                    if building.geometry.intersects(poi_polygon.geometry):
                        numeric_id = int(poi_polygon['ID'])  # Ensure numeric ID is int
                        poi_name = POI_ID_MAP.get(numeric_id)
                        
                        if poi_name:
                            logger.debug(f"Building intersects with POI {numeric_id} ({poi_name})")
                            building_height = min(40, height * 1000)
                            building_color = POI_INFO[poi_name]['color']
                            
                            # Add text label for POI
                            text_features.append({
                                "position": list(building.geometry.centroid.coords)[0] + (building_height + 10,),
                                "text": poi_name,
                                "color": [255, 255, 255, 255]
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
        
        # Prepare POI polygon borders and fills
        poi_borders = []
        poi_fills = []
        
        for poi_idx, poi_polygon in poi_polygons.iterrows():
            numeric_id = int(poi_polygon['ID'])  # Ensure numeric ID is int
            poi_name = POI_ID_MAP.get(numeric_id)
            
            if poi_name:
                logger.info(f"Processing POI polygon: ID={numeric_id}, Name={poi_name}")
                color = POI_INFO[poi_name]['color'][:3]  # Get RGB values
                
                poi_borders.append({
                    "polygon": list(poi_polygon.geometry.exterior.coords),
                    "color": color + [255]  # Full opacity for borders
                })
                
                poi_fills.append({
                    "polygon": list(poi_polygon.geometry.exterior.coords),
                    "color": color + [100]  # Medium opacity for fills
                })
            else:
                logger.warning(f"Unknown POI ID: {numeric_id}")
        
        logger.info(f"Loaded {len(buildings_data)} buildings")
        logger.info(f"Created {len(poi_fills)} POI fill areas")
        return buildings_data, text_features, poi_borders, poi_fills
    except Exception as e:
        logger.error(f"Error loading building data: {str(e)}")
        raise

# Update the create_animation function to handle the new return values
def create_animation(html_template):
    trips_data, center_lat, center_lon, total_trips, animation_duration = load_trip_data()
    buildings_data, text_features, poi_borders, poi_fills = load_building_data()
    
    format_values = {
        'total_trips': total_trips,
        'trips_data': json.dumps(trips_data),
        'buildings_data': json.dumps(buildings_data),
        'poi_borders': json.dumps(poi_borders),
        'poi_fills': json.dumps(poi_fills),
        'poi_radius': POI_RADIUS,
        'bgu_info': json.dumps(POI_INFO['BGU']),
        'gav_yam_info': json.dumps(POI_INFO['Gav Yam']),
        'soroka_info': json.dumps(POI_INFO['Soroka Hospital']),
        'animation_duration': animation_duration,
        'loopLength': animation_duration,
        'mapbox_api_key': MAPBOX_API_KEY,
        'start_hour': 6,
        'end_hour': 23,  # Updated end hour to 23
        'frames_per_hour': int(animation_duration / 18)  # 18 hours from 6:00-23:00
    }
    
    try:
        # Format the HTML
        formatted_html = html_template % format_values
        
        # Write to file
        output_path = os.path.join(OUTPUT_DIR, "trip_line_animation.html")
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
        output_file = create_animation(HTML_TEMPLATE)
        print(f"Animation saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to create animation: {str(e)}")
        sys.exit(1) 