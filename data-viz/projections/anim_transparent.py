"""
Main script for generating mobility visualizations
"""
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
from trip_processing import (
    load_temporal_distributions,
    process_trips,
    validate_generated_trips,
    standardize_poi_name,
    get_original_trip_counts
)
import glob

# Configure logging
logging.basicConfig(level=ANIMATION_CONFIG['log_level'])
logger = logging.getLogger(__name__)

def determine_poi(coords, poi_polygons, poi_id_map):
    """
    Determine which POI a coordinate belongs to.
    """
    point = Point(coords)
    for _, poi in poi_polygons.iterrows():
        if poi.geometry.contains(point):
            poi_id = poi['ID']
            return poi_id_map.get(poi_id)
    return None

def create_deck_html(routes_data, animation_duration, poi_colors, viewport, mode, direction, model_outline):
    """
    Create HTML visualization with transparent background and POI-colored trips.
    Uses animation settings from ANIMATION_CONFIG.
    """
    # Convert model outline to GeoJSON format
    model_geojson = {
        'type': 'Feature',
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[list(coord) for coord in model_outline.exterior.coords]]
        },
        'properties': {}
    }

    # Prepare JSON data
    routes_json = json.dumps(routes_data)
    poi_colors_json = json.dumps(poi_colors)
    viewport_json = json.dumps(viewport)
    animation_config_json = json.dumps(ANIMATION_CONFIG)
    
    # Get mode and direction specific settings
    mode_settings = get_mode_settings(mode)
    direction_settings = get_direction_settings(direction)
    
    # Define animation JavaScript
    animation_js = f"""
            // Animation settings from config
            const ANIMATION_CONFIG = {animation_config_json};
            const MODE_SETTINGS = {json.dumps(mode_settings)};
            const DIRECTION_SETTINGS = {json.dumps(direction_settings)};
            
            // Cache management
            const CACHE_UPDATE_INTERVAL = {ANIMATION_CONFIG['cache_update_interval']};
            let cachedActiveTrips = null;
            let lastFrame = -1;
            let lastHour = -1;
            let lastCacheUpdate = 0;
            let lastLoggedMinute = -1;
            let lastLogTime = 0;
            
            function validateNumericData(route) {{
                return (
                    typeof route.startTime === 'number' &&
                    typeof route.duration === 'number' &&
                    Array.isArray(route.path) &&
                    route.path.length >= 2 &&
                    typeof route.numTrips === 'number'
                );
            }}
            
            function calculateSegmentSpeed(segment, modeSettings) {{
                const settings = modeSettings.segment_speed_adjustment;
                const length = Math.sqrt(
                    Math.pow(segment[1][0] - segment[0][0], 2) +
                    Math.pow(segment[1][1] - segment[0][1], 2)
                );
                
                // Normalize length between min and max
                const normalizedLength = Math.min(
                    Math.max(
                        (length - settings.min_segment_length) / 
                        (settings.max_segment_length - settings.min_segment_length),
                        0
                    ),
                    1
                );
                
                // Calculate speed factor based on length
                let speedFactor = settings.min_speed_factor + 
                       (settings.max_speed_factor - settings.min_speed_factor) * normalizedLength;
                
                // Apply minimum speed threshold
                speedFactor = Math.max(speedFactor, settings.min_speed_threshold);
                
                return speedFactor;
            }}
            
            function smoothSegmentSpeeds(segments, modeSettings) {{
                const window = modeSettings.segment_speed_adjustment.smoothing_window;
                const smoothed = [];
                
                for (let i = 0; i < segments.length; i++) {{
                    let sum = 0;
                    let count = 0;
                    
                    for (let j = Math.max(0, i - window); j <= Math.min(segments.length - 1, i + window); j++) {{
                        sum += calculateSegmentSpeed(segments[j], modeSettings);
                        count++;
                    }}
                    
                    smoothed.push(sum / count);
                }}
                
                return smoothed;
            }}
            
            function processTrips(currentFrame) {{
                const currentTime = performance.now();
                const currentHour = Math.floor((currentFrame / ANIMATION_DURATION) * 24);
                const currentMinute = Math.floor(((currentFrame / ANIMATION_DURATION) * 24 * 60) % 60);
                
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
                
                const activeTrips = ROUTES_DATA.filter(route => {{
                    if (!validateNumericData(route)) return false;
                    
                    const elapsedTime = (currentFrame - route.startTime) % ANIMATION_DURATION;
                    return elapsedTime >= 0 && elapsedTime <= route.duration;
                }});
                
                // Log statistics every 30 minutes
                if (currentMinute % 30 === 0 && currentMinute !== lastLoggedMinute) {{
                    logTripStatistics(currentFrame, activeTrips);
                    lastLoggedMinute = currentMinute;
                }}
                
                // Apply segment-based speed adjustment
                activeTrips.forEach(trip => {{
                    if (trip.path && trip.path.length > 1) {{
                        const segments = [];
                        for (let i = 0; i < trip.path.length - 1; i++) {{
                            segments.push([trip.path[i], trip.path[i + 1]]);
                        }}
                        
                        const speedFactors = smoothSegmentSpeeds(segments, MODE_SETTINGS);
                        trip.segmentSpeeds = speedFactors;
                    }}
                }});
                
                cachedActiveTrips = activeTrips;
                return activeTrips;
            }}
            
            function animate() {{
                const currentTime = performance.now();
                const frame = Math.floor((currentTime / 1000 * {ANIMATION_CONFIG['fps']}) % ANIMATION_DURATION);
                
                const modelOutline = new deck.GeoJsonLayer({{
                    id: 'model-outline',
                    data: {json.dumps(model_geojson)},
                    stroked: true,
                    filled: false,
                    lineWidthMinPixels: 1,
                    getLineColor: [255, 255, 255, 128],  // Semi-transparent white
                    getLineWidth: 1
                }});

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
                    layers: [modelOutline, trips]  // Add outline layer
                }});
                
                requestAnimationFrame(animate);
            }}
            
            function logTripStatistics(currentFrame, activeTrips) {{
                const currentTime = performance.now();
                const currentHour = Math.floor((currentFrame / ANIMATION_DURATION) * 24);
                const currentMinute = Math.floor(((currentFrame / ANIMATION_DURATION) * 24 * 60) % 60);
                
                const tripsByPOI = {{}};
                const speedStats = {{
                    min: Infinity,
                    max: -Infinity,
                    total: 0,
                    count: 0
                }};
                
                Object.keys(POI_COLORS).forEach(poi => {{
                    tripsByPOI[poi] = 0;
                }});
                
                let totalTrips = 0;
                activeTrips.forEach(trip => {{
                    if (trip.poi && typeof trip.numTrips === 'number') {{
                        tripsByPOI[trip.poi] = (tripsByPOI[trip.poi] || 0) + trip.numTrips;
                        totalTrips += trip.numTrips;
                        
                        // Calculate speed statistics
                        if (trip.path && trip.path.length > 1 && trip.segmentSpeeds) {{
                            const duration = trip.duration / ANIMATION_CONFIG['fps'];
                            const distance = trip.path.reduce((total, point, i) => {{
                                if (i === 0) return 0;
                                const prev = trip.path[i-1];
                                const dx = point[0] - prev[0];
                                const dy = point[1] - prev[1];
                                return total + Math.sqrt(dx*dx + dy*dy);
                            }}, 0);
                            
                            const baseSpeed = distance / duration;
                            const adjustedSpeed = baseSpeed * trip.segmentSpeeds.reduce((a, b) => a + b, 0) / trip.segmentSpeeds.length;
                            
                            speedStats.min = Math.min(speedStats.min, adjustedSpeed);
                            speedStats.max = Math.max(speedStats.max, adjustedSpeed);
                            speedStats.total += adjustedSpeed;
                            speedStats.count++;
                        }}
                    }}
                }});
                
                const avgSpeed = speedStats.count > 0 ? speedStats.total / speedStats.count : 0;
                
                console.log(`\\n=== Time: ${{currentHour}}:${{currentMinute.toString().padStart(2, '0')}} ===`);
                console.log(`Active trips: ${{totalTrips.toFixed(0)}}`);
                console.log('Trips by POI:', tripsByPOI);
                console.log('Speed Statistics:', {{
                    min: speedStats.min.toFixed(2),
                    max: speedStats.max.toFixed(2),
                    average: avgSpeed.toFixed(2),
                    'total trips': speedStats.count
                }});
                
                // Add performance metrics
                const fps = 1000 / (currentTime - lastLogTime);
                console.log('Performance:', {{
                    fps: fps.toFixed(1),
                    'active trips': activeTrips.length,
                    'memory usage': (performance.memory?.usedJSHeapSize / 1024 / 1024).toFixed(1) + 'MB'
                }});
                
                lastLogTime = currentTime;
            }}
    """
    
    # Generate complete HTML
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
        <style>
            body, html {{ 
                margin: 0; 
                padding: 0;
                background-color: #000000;
            }}
            #container {{ 
                width: 100vw; 
                height: 100vh; 
                position: relative;
            }}
            canvas {{
                background: #000000 !important;
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
            
            setTimeout(() => {{
                animate();
                window.animationStarted = true;
            }}, 2000);
        </script>
    </body>
    </html>
    """

def load_model_outline(shapefile_path):
    """Load model outline and convert to web mercator projection"""
    try:
        model = gpd.read_file(shapefile_path)
        if model.crs != 'EPSG:4326':
            model = model.to_crs('EPSG:4326')
        
        # Get the first geometry and its bounds
        geometry = model.geometry.iloc[0]
        bounds = geometry.bounds  # This returns (minx, miny, maxx, maxy)
        
        return geometry, bounds
    except Exception as e:
        logger.error(f"Error loading model outline: {str(e)}")
        raise

def get_optimal_viewport(bounds, model_size='big'):
    """Calculate optimal viewport settings based on geometry bounds"""
    minx, miny, maxx, maxy = bounds
    center_lon = (minx + maxx) / 2
    center_lat = (miny + maxy) / 2
    
    lat_zoom = np.log2(360 / (maxy - miny)) + 1
    lon_zoom = np.log2(360 / (maxx - minx)) + 1
    base_zoom = min(lat_zoom, lon_zoom) - 0.5
    
    # Add extra zoom for small model
    if model_size == 'small':
        base_zoom += 0.75  # Increase zoom level by 0.5 for small model
    
    return {
        'longitude': center_lon,
        'latitude': center_lat,
        'zoom': base_zoom,
        'pitch': 0,
        'bearing': 0
    }

def load_trip_data(mode, direction):
    """Load and process trip data for visualization"""
    file_path = os.path.join(OUTPUT_DIR, f"{mode}_routes_{direction}.geojson")
    
    try:
        # Load base data
        trips_gdf = gpd.read_file(file_path)
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing {mode} {direction} trips")
        logger.info(f"Loaded {len(trips_gdf)} trips from {file_path}")
        
        # Debug raw data structure
        logger.info("\nData Structure Check:")
        logger.info(f"Columns: {trips_gdf.columns.tolist()}")
        logger.info(f"Sample trip counts: {trips_gdf['num_trips'].head().tolist()}")
        
        # Get settings
        mode_settings = get_mode_settings(mode)
        logger.info("\nMode Settings:")
        logger.info(f"{json.dumps(mode_settings, indent=2)}")
        
        # Load temporal distributions
        temporal_dist = load_temporal_distributions(mode, direction, OUTPUT_DIR)
        
        # Get original trip counts for validation
        original_counts = get_original_trip_counts(trips_gdf, direction, mode)
        
        # Process trips based on mode
        if mode == 'walk':
            routes_data, debug_info = process_trips(
                trips_gdf=trips_gdf,
                temporal_dist=temporal_dist,
                mode_settings=mode_settings,
                direction=direction,
                mode=mode,
                animation_config=ANIMATION_CONFIG
            )
        else:
            # Load POI data for car trips
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            workspace_root = os.path.join(base_dir, 'BeerShevaMobility')
            search_path = os.path.join(workspace_root, 'shapes', 'data', 'maps', '*Attraction*Centers*.shp')
            poi_files = glob.glob(search_path)
            if not poi_files:
                # Try alternative search pattern
                search_path = os.path.join(workspace_root, 'shapes', 'data', 'maps', '*.shp')
                poi_files = glob.glob(search_path)
                if not poi_files:
                    raise FileNotFoundError(f"Could not find POI shapefile in {os.path.dirname(search_path)}")
            poi_polygons = gpd.read_file(poi_files[0])  # Use the first matching file
            poi_polygons = poi_polygons[poi_polygons['ID'].isin([11, 12, 7])]
            POI_ID_MAP = {7: 'BGU', 12: 'Gav Yam', 11: 'Soroka Hospital'}

            routes_data, debug_info = process_trips(
                trips_gdf=trips_gdf,
                temporal_dist=temporal_dist,
                mode_settings=mode_settings,
                direction=direction,
                mode=mode,
                animation_config=ANIMATION_CONFIG,
                poi_polygons=poi_polygons,  # Only for cars
                poi_id_map=POI_ID_MAP      # Only for cars
            )

        # Validate generated trips
        validate_generated_trips(routes_data, original_counts, debug_info)
        
        return routes_data, ANIMATION_CONFIG['animation_duration'], ANIMATION_CONFIG['poi_colors']
        
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise

def main():
    """Process all combinations of modes, directions, and models"""
    modes = ['car', 'walk']
    directions = ['inbound', 'outbound']
    models = ['big', 'small']
    
    for mode in modes:
        for direction in directions:
            try:
                # Load trip data
                logger.info(f"Loading trip data for {mode}-{direction}")
                trip_data = load_trip_data(mode, direction)
                logger.info(f"Trip data loaded, got {len(trip_data)} values")
                routes_data, animation_duration, poi_colors = trip_data
                
                for model_size in models:
                    # Load model outline and create viewport
                    logger.info(f"Loading model outline for {model_size}")
                    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                            'data-viz', 'data', 'model_outline', f'{model_size} model.shp')
                    outline_data = load_model_outline(model_path)
                    logger.info(f"Model outline loaded, got {len(outline_data)} values")
                    model_outline, bounds = outline_data
                    
                    logger.info("Creating viewport")
                    viewport = get_optimal_viewport(bounds, model_size)
                    
                    # Generate output filename
                    html_path = os.path.join(
                        OUTPUT_DIR,
                        f"projection_animation_{model_size}_{mode}_{direction}.html"
                    )
                    
                    logger.info(f"Creating HTML content for {html_path}")
                    # Create HTML content
                    html_content = create_deck_html(
                        routes_data,
                        animation_duration,
                        poi_colors,
                        viewport,
                        mode,
                        direction,
                        model_outline
                    )
                    
                    # Save HTML file
                    with open(html_path, "w") as f:
                        f.write(html_content)
                    
                    logger.info(f"Created HTML: {html_path}")
                    
            except Exception as e:
                logger.error(f"Error processing {mode}-{direction}: {str(e)}")
                logger.error(f"Error details:", exc_info=True)  # This will print the full traceback
                continue

if __name__ == "__main__":
    main()