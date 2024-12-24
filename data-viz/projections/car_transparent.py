import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import logging
from config import OUTPUT_DIR
from shapely.geometry import Point
from animation_config import ANIMATION_CONFIG, get_mode_settings, get_direction_settings, get_poi_color

# Configure logging
logging.basicConfig(level=ANIMATION_CONFIG['log_level'])
logger = logging.getLogger(__name__)

def determine_poi(coords, poi_polygons, poi_id_map):
    """
    Determine which POI a coordinate belongs to.
    
    Args:
        coords: Tuple of (longitude, latitude)
        poi_polygons: GeoDataFrame containing POI polygons
        poi_id_map: Dictionary mapping POI IDs to names
    
    Returns:
        String: POI name if within a POI area, None otherwise
    """
    point = Point(coords)
    for _, poi in poi_polygons.iterrows():
        if poi.geometry.contains(point):
            poi_id = poi['ID']
            return poi_id_map.get(poi_id)
    return None
def create_deck_html(routes_data, animation_duration, poi_colors, viewport, mode, direction):
    """
    Create HTML visualization with transparent background and POI-colored trips.
    Uses animation settings from ANIMATION_CONFIG.
    """
    # Prepare JSON data
    routes_json = json.dumps(routes_data)
    poi_colors_json = json.dumps(poi_colors)
    viewport_json = json.dumps(viewport)
    
    # Get mode and direction specific settings
    mode_settings = get_mode_settings(mode)
    direction_settings = get_direction_settings(direction)
    
    # Define animation JavaScript with dynamic configuration
    animation_js = f"""
            // Animation settings from config
            const MODE_SETTINGS = {json.dumps(mode_settings)};
            const DIRECTION_SETTINGS = {json.dumps(direction_settings)};
            
            // Cache management
            const CACHE_UPDATE_INTERVAL = {ANIMATION_CONFIG['cache_update_interval']};
            let cachedActiveTrips = null;
            let lastFrame = -1;
            let lastHour = -1;
            let lastCacheUpdate = 0;
            
            function validateNumericData(route) {{
                return (
                    typeof route.startTime === 'number' &&
                    typeof route.duration === 'number' &&
                    Array.isArray(route.path) &&
                    route.path.length >= 2 &&
                    typeof route.numTrips === 'number'
                );
            }}
            
            function processTrips(currentFrame) {{
                const currentTime = performance.now();
                const currentHour = Math.floor((currentFrame / ANIMATION_DURATION) * 24);
                
                // Use cache if possible
                if (
                    currentFrame === lastFrame && 
                    cachedActiveTrips && 
                    currentHour === lastHour &&
                    (currentTime - lastCacheUpdate) < CACHE_UPDATE_INTERVAL
                ) {{
                    return cachedActiveTrips;
                }}
                
                lastFrame = currentFrame;
                lastHour = currentHour;
                lastCacheUpdate = currentTime;
                
                // Filter active trips with validation
                const activeTrips = ROUTES_DATA.filter(route => {{
                    if (!validateNumericData(route)) return false;
                    
                    const elapsedTime = (currentFrame - route.startTime) % ANIMATION_DURATION;
                    return elapsedTime >= 0 && elapsedTime <= route.duration;
                }});
                
                if ({str(ANIMATION_CONFIG['debug_mode']).lower()}) {{
                    logTripStatistics(currentFrame, activeTrips);
                }}
                
                cachedActiveTrips = activeTrips;
                return activeTrips;
            }}
            
            function animate() {{
                const currentTime = performance.now();
                const frame = Math.floor((currentTime / 1000 * {ANIMATION_CONFIG['fps']}) % ANIMATION_DURATION);
                const hour = Math.floor((frame / ANIMATION_DURATION) * 24);
                
                if (hour !== lastHour) {{
                    console.log(`Hour ${{hour}}:00`);
                }}
                
                const trips = new deck.TripsLayer({{
                    id: 'trips',
                    data: processTrips(frame),
                    getPath: d => d.path,
                    getTimestamps: d => {{
                        try {{
                            return d.path.map((_, i) => {{
                                const timestamp = d.startTime + (i * d.duration / d.path.length);
                                return Number.isFinite(timestamp) ? timestamp : 0;
                            }});
                        }} catch (e) {{
                            console.error('Error generating timestamps:', e);
                            return new Array(d.path.length).fill(0);
                        }}
                    }},
                    getColor: d => POI_COLORS[d.poi] || [253, 128, 93],
                    getWidth: d => {{
                        const baseWidth = Math.sqrt(d.numTrips || 1);
                        return d.mode === 'walk' ? 
                            baseWidth * MODE_SETTINGS.min_width : 
                            baseWidth * MODE_SETTINGS.min_width * 2;
                    }},
                    opacity: MODE_SETTINGS.opacity,
                    widthMinPixels: MODE_SETTINGS.min_width,
                    widthMaxPixels: MODE_SETTINGS.max_width,
                    jointRounded: true,
                    capRounded: true,
                    trailLength: MODE_SETTINGS.trail_length,
                    currentTime: frame,
                    shadowEnabled: false,
                    updateTriggers: {{
                        getColor: [frame],
                        getWidth: [frame]
                    }}
                }});
                
                deckgl.setProps({{
                    layers: [trips]
                }});
                
                requestAnimationFrame(animate);
            }}
            
            function logTripStatistics(currentFrame, activeTrips) {{
                const currentTime = performance.now();
                if (currentTime - lastLogTime > 1000) {{
                    const currentHour = Math.floor((currentFrame / ANIMATION_DURATION) * 24);
                    const tripsByPOI = {{}};
                    
                    Object.keys(POI_COLORS).forEach(poi => {{
                        tripsByPOI[poi] = 0;
                    }});
                    
                    let totalTrips = 0;
                    activeTrips.forEach(trip => {{
                        if (trip.poi && typeof trip.numTrips === 'number') {{
                            tripsByPOI[trip.poi] = (tripsByPOI[trip.poi] || 0) + trip.numTrips;
                            totalTrips += trip.numTrips;
                        }}
                    }});
                    
                    console.log(`Hour ${{currentHour}}:00 - Active trips: ${{totalTrips.toFixed(0)}}`);
                    console.log('Trips by POI:', tripsByPOI);
                    
                    lastLogTime = currentTime;
                }}
            }}
    """
    
    # Generate HTML with all settings
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
        <style>
            body, html {{ 
                margin: 0; 
                padding: 0;
                background-color: #666666;
                background-image: 
                    linear-gradient(45deg, #808080 25%, transparent 25%),
                    linear-gradient(-45deg, #808080 25%, transparent 25%),
                    linear-gradient(45deg, transparent 75%, #808080 75%),
                    linear-gradient(-45deg, transparent 75%, #808080 75%);
                background-size: 20px 20px;
                background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
            }}
            #container {{ 
                width: 100vw; 
                height: 100vh; 
                position: relative;
            }}
            canvas {{
                background: transparent !important;
            }}
            #loading {{
                position: fixed;
                top: 10px;
                left: 10px;
                background: rgba(0,0,0,0.7);
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-family: monospace;
            }}
            .progress-bar {{
                position: fixed;
                bottom: 0;
                left: 0;
                width: 100%;
                height: 4px;
                background: #333;
            }}
            .progress {{
                height: 100%;
                width: 0;
                background: #00ff00;
                transition: width 0.3s ease;
            }}
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div id="loading">Initializing...</div>
        <div class="progress-bar"><div class="progress"></div></div>
        
        <script>
            // Constants from backend
            const ANIMATION_DURATION = {animation_duration};
            const ROUTES_DATA = {routes_json};
            const POI_COLORS = {poi_colors_json};
            const HOURS_PER_DAY = 24;
            let lastLogTime = 0;
            
            // Lighting configuration
            const ambientLight = new deck.AmbientLight({{
                color: [255, 255, 255],
                intensity: 1.0
            }});

            const pointLight = new deck.PointLight({{
                color: [255, 255, 255],
                intensity: 2.0,
                position: [34.8, 31.25, 8000]
            }});

            const lightingEffect = new deck.LightingEffect({{
                ambientLight, 
                pointLight
            }});
            
            // Initialize deck.gl
            const deckgl = new deck.DeckGL({{
                container: 'container',
                initialViewState: {viewport_json},
                controller: false,
                effects: [lightingEffect],
                parameters: {{
                    clearColor: [0, 0, 0, 0],
                    blend: true,
                    blendFunc: [
                        WebGLRenderingContext.SRC_ALPHA,
                        WebGLRenderingContext.ONE_MINUS_SRC_ALPHA
                    ],
                    depthTest: true,
                    depthFunc: WebGLRenderingContext.LEQUAL
                }},
                glOptions: {{
                    webgl2: true,
                    webgl1: true,
                    preserveDrawingBuffer: true
                }},
                onWebGLInitialized: (gl) => {{
                    console.log('WebGL initialized');
                    gl.enable(gl.BLEND);
                    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
                }},
                onLoad: () => {{
                    console.log('deck.gl loaded');
                    document.getElementById('loading').style.display = 'none';
                    window.deckglLoaded = true;
                }}
            }});
            
            {animation_js}
            
            // Start animation with a delay
            setTimeout(() => {{
                animate();
                window.animationStarted = true;
            }}, 2000);
        </script>
    </body>
    </html>
    """
def load_temporal_distributions(mode, direction):
    """
    Load temporal distribution data for each POI based on direction.
    Handles both inbound and outbound distributions.
    """
    distributions = {}
    
    # Map file names to POI keys
    file_mapping = {
        'ben_gurion_university': 'BGU',
        'gav_yam_high_tech_park': 'Gav Yam',
        'soroka_medical_center': 'Soroka Hospital'
    }
    
    # Map mode to distribution column name
    mode_column_mapping = {
        'car': 'car_dist',
        'walk': 'pedestrian_dist'
    }
    mode_column = mode_column_mapping.get(mode, 'car_dist')
    
    for file_prefix, poi_key in file_mapping.items():
        # Load the appropriate directional distribution file
        distribution_file = os.path.join(OUTPUT_DIR, f"{file_prefix}_{direction}_temporal.csv")
        
        try:
            df = pd.read_csv(distribution_file)
            
            # Use mode-specific distribution if available, else fallback to car_dist
            if mode_column in df.columns:
                dist = df[mode_column].values
            else:
                logger.warning(f"No {mode_column} distribution found for {poi_key}, using car distribution")
                dist = df['car_dist'].values
            
            # Verify we have 24 hours of data
            if len(dist) != 24:
                logger.warning(f"Expected 24 hours of data for {poi_key}, got {len(dist)}")
                dist = np.zeros(24)  # Fallback to uniform distribution
            
            # Normalize to ensure sum is 1.0
            dist = dist / dist.sum() if dist.sum() > 0 else np.ones(24)/24
            
            # Log the distribution for verification
            logger.info(f"\nTemporal distribution for {poi_key} ({direction}, {mode}):")
            for hour, pct in enumerate(dist):
                logger.info(f"Hour {hour:02d}:00 - {pct*100:5.1f}%")
            
            distributions[poi_key] = dist
            
        except Exception as e:
            logger.error(f"Error loading {direction} temporal data for {poi_key}: {str(e)}")
            logger.error(f"File: {distribution_file}")
            logger.error(f"Mode column: {mode_column}")
            # Fallback to uniform distribution
            distributions[poi_key] = np.ones(24)/24
    
    return distributions

def load_trip_data(mode, direction):
    """Load and process trip data for visualization with improved temporal distribution"""
    file_path = os.path.join(OUTPUT_DIR, f"{mode}_routes_{direction}.geojson")
    
    try:
        # Load base data
        trips_gdf = gpd.read_file(file_path)
        logger.info(f"Loaded {len(trips_gdf)} trips from {file_path}")
        
        # Get settings
        mode_settings = get_mode_settings(mode)
        direction_settings = get_direction_settings(direction)
        
        # Animation timing constants
        fps = ANIMATION_CONFIG['fps']
        frames_per_hour = ANIMATION_CONFIG['frames_per_hour']
        animation_duration = ANIMATION_CONFIG['animation_duration']
        
        # Load distributions and POI data
        temporal_dist = load_temporal_distributions(mode, direction)
        poi_polygons = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
        poi_polygons = poi_polygons[poi_polygons['ID'].isin([11, 12, 7])]
        POI_ID_MAP = {7: 'BGU', 12: 'Gav Yam', 11: 'Soroka Hospital'}
        
        # Initialize tracking
        routes_data = []
        processed_trips = 0
        skipped_trips = 0
        hourly_trip_counts = {i: {'planned': 0, 'actual': 0, 'routes': 0} for i in range(24)}
        
        def calculate_start_times(hour, num_trips):
            """Calculate evenly distributed start times within an hour"""
            base_time = hour * frames_per_hour
            if num_trips == 1:
                return [base_time]
            
            # Distribute trips across 80% of the hour to avoid bunching at boundaries
            usable_frames = int(frames_per_hour * 0.8)
            spacing = usable_frames / (num_trips - 1)
            
            return [base_time + (i * spacing) for i in range(num_trips)]
        
        def calculate_duration(coords, mode_settings):
            """Calculate appropriate duration for a route based on mode"""
            base_duration = min(
                frames_per_hour * mode_settings['speed_multiplier'],
                len(coords) * mode_settings['path_multiplier']
            )
            
            # Limit duration to prevent excessive overlap
            max_duration = frames_per_hour * (1.5 if mode == 'car' else 0.8)
            return min(base_duration, max_duration)
        
        # Process routes
        for idx, row in trips_gdf.iterrows():
            try:
                coords = list(row.geometry.coords)
                num_trips = float(row['num_trips'])
                
                if num_trips <= 0 or len(coords) < 2:
                    continue
                
                # Determine POI 
                poi_coord = coords[-1] if direction == 'inbound' else coords[0]
                poi_name = determine_poi(poi_coord, poi_polygons, POI_ID_MAP)
                if not poi_name:
                    logger.debug(f"No POI found for route {idx}")
                    continue
                
                path = [[float(x), float(y)] for x, y in coords]
                poi_dist = temporal_dist.get(poi_name, [1/24] * 24)
                
                # Debug route info
                logger.debug(f"\nProcessing route {idx}:")
                logger.debug(f"POI: {poi_name}")
                logger.debug(f"Total trips: {num_trips}")
                
                # Calculate base duration once for this route
                base_duration = calculate_duration(coords, mode_settings)
                logger.debug(f"Base duration: {base_duration} frames")
                
                # Process each hour
                for hour in range(24):
                    trips_this_hour = num_trips * poi_dist[hour]
                    hourly_trip_counts[hour]['planned'] += trips_this_hour
                    
                    if trips_this_hour > 0.1:  # Minimum threshold
                        # Round to nearest whole number
                        actual_trips = max(1, round(trips_this_hour))
                        hourly_trip_counts[hour]['actual'] += actual_trips
                        
                        # Calculate staggered start times
                        start_times = calculate_start_times(hour, actual_trips)
                        logger.debug(f"Hour {hour}: {actual_trips} trips, {len(start_times)} start times")
                        
                        for start_time in start_times:
                            route_data = {
                                'path': path,
                                'startTime': float(start_time),
                                'duration': float(base_duration),
                                'numTrips': 1.0,  # One trip per entry
                                'poi': poi_name,
                                'mode': mode,
                                'direction': direction,
                                'trailLength': mode_settings['trail_length'],
                                'minWidth': mode_settings['min_width'],
                                'maxWidth': mode_settings['max_width'],
                                'opacity': mode_settings['opacity']
                            }
                            
                            routes_data.append(route_data)
                            hourly_trip_counts[hour]['routes'] += 1
                            processed_trips += 1
                    else:
                        skipped_trips += trips_this_hour
                
            except Exception as e:
                logger.error(f"Error processing route {idx}: {str(e)}")
                continue
        
        # Log detailed statistics
        logger.info("\nTrip Processing Statistics:")
        logger.info(f"Total planned trips: {processed_trips + skipped_trips:,.0f}")
        logger.info(f"Actually processed trips: {processed_trips:,.0f}")
        logger.info(f"Skipped trips: {skipped_trips:,.0f}")
        logger.info(f"Processing ratio: {(processed_trips/(processed_trips + skipped_trips))*100:.1f}%")
        
        logger.info("\nHourly Trip Distribution:")
        for hour in range(24):
            planned = hourly_trip_counts[hour]['planned']
            actual = hourly_trip_counts[hour]['actual']
            routes = hourly_trip_counts[hour]['routes']
            if planned > 0:
                ratio = (actual / planned) * 100 if planned > 0 else 0
                logger.info(f"{hour:02d}:00 - Planned: {planned:6.1f}, Actual: {actual:6.1f}, Routes: {routes:4d} ({ratio:5.1f}%)")
        
        return routes_data, animation_duration, ANIMATION_CONFIG['poi_colors']
        
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise

def load_model_outline(shapefile_path):
    """Load model outline and convert to web mercator projection"""
    model = gpd.read_file(shapefile_path)
    if model.crs != 'EPSG:4326':
        model = model.to_crs('EPSG:4326')
    bounds = model.geometry.iloc[0].bounds
    return model.geometry.iloc[0], bounds

def get_optimal_viewport(bounds):
    """Calculate optimal viewport settings based on geometry bounds"""
    minx, miny, maxx, maxy = bounds
    center_lon = (minx + maxx) / 2
    center_lat = (miny + maxy) / 2
    
    # Calculate zoom level to fit bounds
    lat_zoom = np.log2(360 / (maxy - miny)) + 1
    lon_zoom = np.log2(360 / (maxx - minx)) + 1
    zoom = min(lat_zoom, lon_zoom) - 0.5
    
    return {
        'longitude': center_lon,
        'latitude': center_lat,
        'zoom': zoom,
        'pitch': 45,
        'bearing': 0
    }

def main():
    """Process all combinations of modes, directions, and models"""
    modes = ['car', 'walk']
    directions = ['inbound', 'outbound']
    models = ['big', 'small']
    
    for mode in modes:
        for direction in directions:
            try:
                # Load trip data
                routes_data, animation_duration, poi_colors = load_trip_data(mode, direction)
                
                for model_size in models:
                    # Load model outline and create viewport
                    model_outline, bounds = load_model_outline(
                        f'data-viz/data/model_outline/{model_size} model.shp'
                    )
                    viewport = get_optimal_viewport(bounds)
                    
                    # Generate output filename
                    html_path = os.path.join(
                        OUTPUT_DIR,
                        f"projection_animation_{model_size}_{mode}_{direction}.html"
                    )
                    
                    # Create HTML content
                    html_content = create_deck_html(
                        routes_data,
                        animation_duration,
                        poi_colors,
                        viewport,
                        mode,
                        direction
                    )
                    
                    # Save HTML file
                    with open(html_path, "w") as f:
                        f.write(html_content)
                    
                    logger.info(f"Created HTML: {html_path}")
                    
            except Exception as e:
                logger.error(f"Error processing {mode}-{direction}: {str(e)}")
                continue

if __name__ == "__main__":
    main()