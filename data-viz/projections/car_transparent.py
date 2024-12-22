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
from animation_config import ANIMATION_CONFIG, calculate_animation_duration

# Configure logging
logging.basicConfig(level=logging.INFO)
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

def load_temporal_distributions(mode):
    """Load temporal distribution data for each POI"""
    distributions = {}
    
    # Map file names to POI keys
    file_mapping = {
        'ben_gurion_university': 'BGU',
        'gav_yam_high_tech_park': 'Gav Yam',
        'soroka_medical_center': 'Soroka Hospital'
    }
    
    for file_prefix, poi_key in file_mapping.items():
        # Load only inbound distributions
        inbound_file = os.path.join(OUTPUT_DIR, f"{file_prefix}_inbound_temporal.csv")
        
        try:
            inbound_df = pd.read_csv(inbound_file)
            
            # Use only inbound distribution for cars
            dist = inbound_df['car_dist'].values
            
            # Verify we have 24 hours of data
            if len(dist) != 24:
                logger.warning(f"Expected 24 hours of data for {poi_key}, got {len(dist)}")
                dist = np.zeros(24)  # Fallback to uniform distribution
            
            # Normalize to ensure sum is 1.0
            dist = dist / dist.sum() if dist.sum() > 0 else np.ones(24)/24
            
            # Log the distribution for verification
            logger.info(f"\nTemporal distribution for {poi_key}:")
            for hour, pct in enumerate(dist):
                logger.info(f"Hour {hour:02d}:00 - {pct*100:5.1f}%")
            
            distributions[poi_key] = dist
            
        except Exception as e:
            logger.error(f"Error loading temporal data for {poi_key}: {str(e)}")
            # Fallback to uniform distribution
            distributions[poi_key] = np.ones(24)/24
    
    return distributions

def load_trip_data(mode='car', direction='inbound'):
    """Load and process trip data with POI-based coloring and temporal distribution"""
    # Determine file path based on mode and direction
    file_path = os.path.join(OUTPUT_DIR, f"{mode}_routes_{direction}.geojson")
    
    # Define POIs and their colors
    POI_COLORS = {
        'BGU': [0, 255, 90],
        'Gav Yam': [0, 191, 255],
        'Soroka Hospital': [170, 0, 255]
    }
    # POI ID mapping
    POI_ID_MAP = {
        7: 'BGU',
        12: 'Gav Yam',
        11: 'Soroka Hospital'
    }
    
    try:
        
        # Animation timing constants from config
        animation_config = calculate_animation_duration()
        fps = animation_config['fps']
        seconds_per_hour = animation_config['seconds_per_hour']
        frames_per_hour = animation_config['frames_per_hour']
        animation_duration = animation_config['animation_duration']
        
        # Add logging for animation timing
        logger.info(f"\nAnimation timing configuration:")
        logger.info(f"FPS: {fps}")
        logger.info(f"Seconds per hour: {seconds_per_hour}")
        logger.info(f"Frames per hour: {frames_per_hour}")
        logger.info(f"Total frames: {animation_duration}")
        logger.info(f"Total animation duration: {animation_duration/fps:.1f} seconds")
        
        # Load temporal distributions for the specific mode
        temporal_dist = load_temporal_distributions(mode)
        
        # Load POI polygons
        attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
        poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]
        
        # Load trips
        trips_gdf = gpd.read_file(file_path)
        raw_trip_count = trips_gdf['num_trips'].sum()
        
        routes_data = []
        processed_trips = 0
        skipped_trips = 0
        hourly_trip_counts = {i: {'planned': 0, 'actual': 0} for i in range(24)}
        
        for idx, row in trips_gdf.iterrows():
            try:
                coords = list(row.geometry.coords)
                num_trips = float(row['num_trips'])
                
                if num_trips <= 0 or len(coords) < 2:
                    continue
                
                # Determine POI for this route
                poi_name = determine_poi(coords[-1], poi_polygons, POI_ID_MAP)
                if not poi_name:
                    continue
                
                path = [[float(x), float(y)] for x, y in coords]
                poi_dist = temporal_dist.get(poi_name, [1/24] * 24)
                
                # Process all 24 hours
                for hour in range(24):
                    trips_this_hour = num_trips * poi_dist[hour]
                    hourly_trip_counts[hour]['planned'] += trips_this_hour
                    
                    if trips_this_hour > 0.1:
                        # Don't round down small numbers of trips
                        trips_this_hour = max(1, trips_this_hour)
                        start_time = hour * frames_per_hour
                        
                        routes_data.append({
                            'path': path,
                            'startTime': start_time,
                            'duration': min(frames_per_hour * animation_config['trip_duration_multiplier'][mode], 
                                           len(coords) * animation_config['path_length_multiplier'][mode]),
                            'numTrips': trips_this_hour,
                            'poi': poi_name,
                            'mode': mode,
                            'direction': direction,
                            'debug': True
                        })
                        
                        processed_trips += trips_this_hour
                        hourly_trip_counts[hour]['actual'] += trips_this_hour
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
            if planned > 0:
                ratio = (actual / planned) * 100
                logger.info(f"{hour:02d}:00 - Planned: {planned:6.1f}, Actual: {actual:6.1f} ({ratio:5.1f}%)")
        
        return routes_data, animation_duration, POI_COLORS
        
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
    zoom = min(lat_zoom, lon_zoom) - 0.5  # Slight padding
    
    return {
        'longitude': center_lon,
        'latitude': center_lat,
        'zoom': zoom,
        'pitch': 45,
        'bearing': 0
    }

def create_deck_html(routes_data, animation_duration, poi_colors, viewport, mode, direction):
    """Create HTML with transparent background and POI-colored trips"""
    routes_json = json.dumps(routes_data)
    poi_colors_json = json.dumps(poi_colors)
    viewport_json = json.dumps(viewport)
    
    animation_js = """
            let cachedActiveTrips = null;
            let lastFrame = -1;
            let lastHour = -1;
            
            function processTrips(currentFrame) {
                const currentHour = Math.floor((currentFrame / ANIMATION_DURATION) * 24);
                
                // Only process trips every 30 frames (1 second) or when hour changes
                if (currentFrame === lastFrame && cachedActiveTrips && currentHour === lastHour) {
                    return cachedActiveTrips;
                }
                
                lastFrame = currentFrame;
                lastHour = currentHour;
                
                // Filter active trips more efficiently
                const activeTrips = ROUTES_DATA.filter(route => {
                    const elapsedTime = (currentFrame - route.startTime) % ANIMATION_DURATION;
                    return elapsedTime >= 0 && elapsedTime <= route.duration;
                });
                
                cachedActiveTrips = activeTrips;
                return activeTrips;
            }
            
            function animate() {
                const currentTime = performance.now();
                const frame = Math.floor((currentTime / 1000 * 30) % ANIMATION_DURATION);
                const hour = Math.floor((frame / ANIMATION_DURATION) * 24);
                
                if (hour !== lastHour) {
                    console.log(`Hour ${hour}:00`);
                }
                
                const trips = new deck.TripsLayer({
                    id: 'trips',
                    data: processTrips(frame),
                    getPath: d => d.path,
                    getTimestamps: d => d.path.map((_, i) => d.startTime + (i * d.duration / d.path.length)),
                    getColor: d => getPathColor(d.path, d.poi),
                    getWidth: d => getPathWidth(d),
                    opacity: 0.8,
                    widthMinPixels: d => d.mode === 'walk' ? 1 : 2,
                    widthMaxPixels: d => d.mode === 'walk' ? 1 : 2,
                    jointRounded: true,
                    capRounded: true,
                    trailLength: d => d.mode === 'walk' ? 3 : 5,
                    currentTime: frame,
                    updateTriggers: {
                        getColor: [frame],
                        getWidth: [frame]
                    }
                });
                
                deckgl.setProps({
                    layers: [trips]
                });
                
                requestAnimationFrame(animate);
            }
            
            let totalTripsDisplayed = 0;
            let lastLogTime = 0;
            
            function logTripStatistics(currentFrame, activeTrips) {
                const currentTime = performance.now();
                if (currentTime - lastLogTime > 1000) {  // Log once per second
                    const currentHour = Math.floor((currentFrame / ANIMATION_DURATION) * 24);
                    const tripsByPOI = {
                        'BGU': 0,
                        'Gav Yam': 0,
                        'Soroka Hospital': 0
                    };
                    
                    let totalTrips = 0;
                    activeTrips.forEach(trip => {
                        if (trip.poi) {
                            tripsByPOI[trip.poi] += trip.numTrips;
                            totalTrips += trip.numTrips;
                        }
                    });
                    
                    console.log(`Hour ${currentHour}:00 - Active trips: ${totalTrips.toFixed(0)}`);
                    console.log('Trips by POI:', tripsByPOI);
                    
                    totalTripsDisplayed += totalTrips;
                    lastLogTime = currentTime;
                }
            }
            
            function processTrips(currentFrame) {
                const activeTrips = ROUTES_DATA.filter(route => {
                    const elapsedTime = (currentFrame - route.startTime) % ANIMATION_DURATION;
                    return elapsedTime >= 0 && elapsedTime <= route.duration;
                });
                
                logTripStatistics(currentFrame, activeTrips);
                return activeTrips;
            }
            
            function getPathWidth(d) {
                const baseWidth = Math.sqrt(d.numTrips);
                return d.mode === 'walk' ? baseWidth * 0.7 : baseWidth;  // Thinner lines for walking
            }
    """
    
    # Update HTML template to include timing logs
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
        <style>
            body, html {{ 
                margin: 0; 
                padding: 0;
                background-image: 
                    linear-gradient(45deg, #808080 25%, transparent 25%),
                    linear-gradient(-45deg, #808080 25%, transparent 25%),
                    linear-gradient(45deg, transparent 75%, #808080 75%),
                    linear-gradient(-45deg, transparent 75%, #808080 75%);
                background-size: 20px 20px;
                background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
                background-color: #666666;
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
            const ANIMATION_DURATION = {animation_duration};
            const ROUTES_DATA = {routes_json};
            const POI_COLORS = {poi_colors_json};
            const HOURS_PER_DAY = 24;
            const START_HOUR = 6;
            let isInitialized = false;
            
            const ambientLight = new deck.AmbientLight({{
                color: [255, 255, 255],
                intensity: 1.0
            }});

            const pointLight = new deck.PointLight({{
                color: [255, 255, 255],
                intensity: 2.0,
                position: [34.8, 31.25, 8000]
            }});

            const lightingEffect = new deck.LightingEffect({{ambientLight, pointLight}});
            
            const INITIAL_VIEW_STATE = {viewport_json};
            
            const deckgl = new deck.DeckGL({{
                container: 'container',
                initialViewState: INITIAL_VIEW_STATE,
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
                    isInitialized = true;
                    document.getElementById('loading').style.display = 'none';
                    window.deckglLoaded = true;
                }}
            }});
            
            let frame = 0;
            let lastLoggedHour = -1;
            let trailLength = 5;
            
            function getPathColor(path, poi) {{
                if (poi && POI_COLORS[poi]) {{
                    return POI_COLORS[poi];
                }}
                return [253, 128, 93];
            }}
            
            {animation_js}
            
            setTimeout(() => {{
                animate();
                window.animationStarted = true;
            }}, 2000);
        </script>
    </body>
    </html>
    """

def main():
    # Process all combinations
    modes = ['car', 'walk']
    directions = ['inbound', 'outbound']
    models = ['big', 'small']
    
    for mode in modes:
        for direction in directions:
            # Load trip data for this combination
            routes_data, animation_duration, poi_colors = load_trip_data(mode, direction)
            
            for model_size in models:
                # Load appropriate model outline
                model_outline, bounds = load_model_outline(
                    f'data-viz/data/model_outline/{model_size} model.shp'
                )
                
                # Create viewport for this model
                viewport = get_optimal_viewport(bounds)
                
                # Generate HTML
                html_path = os.path.join(
                    OUTPUT_DIR, 
                    f"projection_animation_{model_size}_{mode}_{direction}.html"
                )
                html_content = create_deck_html(
                    routes_data, 
                    animation_duration, 
                    poi_colors, 
                    viewport,
                    mode,
                    direction
                )
                
                with open(html_path, "w") as f:
                    f.write(html_content)
                
                logger.info(f"Created HTML: {html_path}")

if __name__ == "__main__":
    main()

