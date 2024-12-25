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
    
    # Define animation JavaScript
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
            const ANIMATION_DURATION = {animation_duration};
            const ROUTES_DATA = {routes_json};
            const POI_COLORS = {poi_colors_json};
            const HOURS_PER_DAY = 24;
            let lastLogTime = 0;
            
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
            poi_polygons = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
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