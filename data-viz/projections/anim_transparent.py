"""
Consolidated mobility visualization module with integrated trip processing 
and unified speed control system
"""
import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
import json
import logging
import random
from shapely.geometry import Point
from typing import Dict, List, Tuple, Optional, Union

logger = logging.getLogger(__name__)
# Configure logging to display to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Output directory
OUTPUT_DIR = '/Users/noamgal/DSProjects/BeerShevaMobility/data-viz/output/dashboard_data'

#############################################
# Configuration and Settings
#############################################

def calculate_animation_duration():
    """
    Calculate animation duration and related timing parameters.
    Returns a complete configuration dictionary for all animation settings.
    """
    # Base timing configuration
    fps = 30
    seconds_per_hour = 30  # Each hour takes 30 seconds
    hours_per_day = 24
    frames_per_hour = fps * seconds_per_hour
    animation_duration = frames_per_hour * hours_per_day
    total_seconds = animation_duration / fps

    # Mode-specific settings - improved speed control
    mode_settings = {
        'car': {
            'speed_factor': 1.0,       # Base speed factor (higher = slower animation)
            'path_multiplier': 15,     # Keeps your path stretching
            'trail_length': 6,          
            'min_width': 3,            # Slightly thicker
            'max_width': 8,            # Allow more prominent paths
            'opacity': 0.6,              
            'animation_offset': 0,       
            'simultaneity_factor': 1.5,  # Keep simultaneous trip factor
        },
        'walk': {
            'speed_factor': 1.0,       # Base speed factor (higher = slower animation)
            'path_multiplier': 15,     # Keep path stretching
            'trail_length': 4,           
            'min_width': 2,            # Slightly thinner than cars
            'max_width': 6,            # Still prominent
            'opacity': 0.6,             
            'animation_offset': 0,       
            'simultaneity_factor': 1.5,  # Keep simultaneous trip factor
        }
    }

    # Direction-specific settings
    direction_settings = {
        'inbound': {
            'start_hour': 6,               # Morning rush hour start
            'peak_hours': [7, 8],          # Morning peak (7-8am)
            'flow_multiplier': 1.0,        # Base flow rate
            'reverse_coords': False,
            'poi_index': -1
        },
        'outbound': {
            'start_hour': 16,              # Afternoon rush hour start
            'peak_hours': [17, 18],        # Evening peak (5-6pm)
            'flow_multiplier': 1.0,        # Base flow rate
            'reverse_coords': True,
            'poi_index': 0
        }
    }

    # POI Colors (consistent across all visualizations)
    poi_colors = {
        'BGU': [0, 255, 90],              # Bright green
        'Gav Yam': [0, 191, 255],         # Bright blue
        'Soroka Hospital': [170, 0, 255]  # Purple
    }
    
    # Log configuration details
    logger.info("\nAnimation timing configuration:")
    logger.info(f"FPS: {fps}")
    logger.info(f"Seconds per hour: {seconds_per_hour}")
    logger.info(f"Frames per hour: {frames_per_hour}")
    logger.info(f"Total frames: {animation_duration}")
    logger.info(f"Total animation duration: {total_seconds:.1f} seconds")

    # Combined configuration dictionary
    return {
        # Timing parameters
        'fps': fps,
        'seconds_per_hour': seconds_per_hour,
        'hours_per_day': hours_per_day,
        'frames_per_hour': frames_per_hour,
        'animation_duration': animation_duration,
        'total_seconds': total_seconds,
        
        # Mode and direction settings
        'modes': mode_settings,
        'directions': direction_settings,
        'poi_colors': poi_colors,
        
        # Animation settings
        'frame_cache_size': 30,
        'cache_update_interval': 1000,
        
        # Recording settings
        'recording': {
            'inbound_hour': 7,            # 7:00 AM
            'outbound_hour': 17,          # 5:00 PM
            'viewport_padding': 0.05,     # 5% padding
        },
        
        # Performance settings
        'blend_mode': {
            'src_rgb': 'src alpha',
            'dst_rgb': 'one minus src alpha',
            'src_alpha': 'src alpha',
            'dst_alpha': 'one minus src alpha'
        },
        
        # Debug settings
        'debug_mode': False,
        'log_level': logging.INFO
    }

# Calculate configuration once at module import
ANIMATION_CONFIG = calculate_animation_duration()

def get_mode_settings(mode):
    """Helper function to get settings for a specific mode"""
    if mode not in ANIMATION_CONFIG['modes']:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {list(ANIMATION_CONFIG['modes'].keys())}")
    return ANIMATION_CONFIG['modes'][mode]

def get_direction_settings(direction):
    """Helper function to get settings for a specific direction"""
    if direction not in ANIMATION_CONFIG['directions']:
        raise ValueError(f"Invalid direction: {direction}. Must be one of {list(ANIMATION_CONFIG['directions'].keys())}")
    return ANIMATION_CONFIG['directions'][direction]

def get_poi_color(poi_name):
    """Helper function to get color for a specific POI"""
    return ANIMATION_CONFIG['poi_colors'].get(poi_name, [255, 255, 255])  # Default to white if POI not found

#############################################
# POI and Trip Processing Functions
#############################################

def standardize_poi_name(name: Union[str, None]) -> Optional[str]:
    """Enhanced POI name standardization with debugging"""
    if not name:
        return None
        
    original = str(name)
    name = original.lower().replace('-', ' ').replace('_', ' ').strip()
    
    # Map variants to standard names
    poi_mapping = {
        'ben gurion university': 'BGU',
        'bgu': 'BGU',
        'ben gurion': 'BGU',
        'university': 'BGU',
        'gav yam high tech park': 'Gav Yam',
        'gav yam': 'Gav Yam',
        'hightech park': 'Gav Yam',
        'soroka medical center': 'Soroka Hospital',
        'soroka': 'Soroka Hospital',
        'hospital': 'Soroka Hospital'
    }
    
    standardized = poi_mapping.get(name, name)
    if standardized != original:
        logger.debug(f"POI standardization: {original} -> {standardized}")
    
    return standardized

def determine_poi(coords, poi_polygons, poi_id_map):
    """Determine which POI a coordinate belongs to."""
    point = Point(coords)
    for _, poi in poi_polygons.iterrows():
        if poi.geometry.contains(point):
            poi_id = poi['ID']
            return poi_id_map.get(poi_id)
    return None

def get_poi_for_route(row: pd.Series, direction: str) -> Optional[str]:
    """
    Extract and standardize POI name from route data based on direction
    
    Args:
        row: DataFrame row containing route data
        direction: 'inbound' or 'outbound'
    
    Returns:
        Standardized POI name or None if invalid
    """
    try:
        # For inbound trips, destination is the POI
        # For outbound trips, origin_zone is the POI
        poi_field = 'destination' if direction == 'inbound' else 'origin_zone'
        raw_poi = row.get(poi_field)
        
        logger.debug(f"Raw POI value from {poi_field}: {raw_poi}")
        
        if pd.isna(raw_poi) or raw_poi is None:
            logger.debug(f"Missing {poi_field} in route data")
            return None
            
        standardized = standardize_poi_name(str(raw_poi))
        logger.debug(f"Standardized POI name: {raw_poi} -> {standardized}")
        
        return standardized
        
    except Exception as e:
        logger.error(f"Error extracting POI: {str(e)}")
        logger.error(f"Row data: {row}")
        return None

def get_trip_count(row: pd.Series, mode: str) -> float:
    """Get trip count with debug logging"""
    if mode == 'walk':
        trips = float(row.get('num_trips', 1))
        logger.debug(f"Walk trip count: {trips} (from num_trips)")
        return trips
    else:
        trips = float(row.get('num_trips', 1))
        logger.debug(f"Car trip count: {trips} (from num_trips)")
        return trips

def load_temporal_distributions(mode: str, direction: str, output_dir: str) -> Dict[str, np.ndarray]:
    """
    Load temporal distribution data for each POI with enhanced validation
    
    Args:
        mode: 'car' or 'walk'
        direction: 'inbound' or 'outbound'
        output_dir: Directory containing temporal distribution files
    
    Returns:
        Dictionary mapping POI names to hourly distributions
    """
    distributions = {}
    
    # Map file names to POI keys
    file_mapping = {
        'ben_gurion_university': 'BGU',
        'gav_yam_high_tech_park': 'Gav Yam',
        'soroka_medical_center': 'Soroka Hospital'
    }
    
    # Map mode to distribution column name
    mode_column = 'pedestrian_dist' if mode == 'walk' else 'car_dist'
    
    logger.info(f"\nLoading temporal distributions for {mode} {direction}")
    
    for file_prefix, poi_key in file_mapping.items():
        distribution_file = os.path.join(output_dir, f"{file_prefix}_{direction}_temporal.csv")
        
        try:
            if not os.path.exists(distribution_file):
                logger.warning(f"Distribution file not found: {distribution_file}")
                continue
                
            logger.info(f"\nProcessing distribution file: {distribution_file}")
            df = pd.read_csv(distribution_file)
            
            # Debug column names
            logger.debug(f"Available columns: {df.columns.tolist()}")
            
            if mode_column in df.columns:
                dist = df[mode_column].values
                logger.info(f"Using {mode_column} distribution for {poi_key}")
            else:
                logger.warning(f"No {mode_column} distribution found for {poi_key}, using car_dist")
                dist = df['car_dist'].values
            
            if len(dist) != 24:
                logger.warning(f"Expected 24 hours of data for {poi_key}, got {len(dist)}")
                dist = np.zeros(24)
            
            # Validate and normalize distribution
            dist = np.array(dist, dtype=float)
            if np.any(np.isnan(dist)):
                logger.warning(f"Found NaN values in distribution for {poi_key}")
                dist = np.nan_to_num(dist)
            
            if dist.sum() > 0:
                dist = dist / dist.sum()
            else:
                logger.warning(f"Zero sum distribution for {poi_key}, using uniform distribution")
                dist = np.ones(24)/24
            
            # Log the distribution
            logger.info(f"\nTemporal distribution for {poi_key} ({direction}, {mode}):")
            for hour, pct in enumerate(dist):
                logger.info(f"Hour {hour:02d}:00 - {pct*100:5.1f}%")
            
            distributions[poi_key] = dist
            
        except Exception as e:
            logger.error(f"Error loading {direction} temporal data for {poi_key}: {str(e)}")
            logger.error(f"File: {distribution_file}")
            distributions[poi_key] = np.ones(24)/24
    
    return distributions

def get_original_trip_counts(trips_gdf: gpd.GeoDataFrame, direction: str, mode: str) -> Dict[str, float]:
    """
    Extract original trip counts by POI from the GeoDataFrame with validation
    """
    original_counts = {}
    
    logger.info(f"\nExtracting original trip counts for {mode} {direction}")
    
    for idx, row in trips_gdf.iterrows():
        try:
            poi_name = get_poi_for_route(row, direction)
            if poi_name:
                num_trips = get_trip_count(row, mode)
                if num_trips > 0:
                    original_counts[poi_name] = original_counts.get(poi_name, 0) + num_trips
        except Exception as e:
            logger.error(f"Error processing row {idx}: {str(e)}")
            continue
    
    logger.info("\nOriginal trip counts by POI:")
    for poi, count in original_counts.items():
        logger.info(f"  {poi}: {count:.1f}")
    
    return original_counts

def process_trips(trips_gdf: gpd.GeoDataFrame, 
                 temporal_dist: Dict[str, pd.DataFrame],
                 mode_settings: Dict,
                 direction: str,
                 mode: str,
                 animation_config: Dict,
                 poi_polygons: Optional[gpd.GeoDataFrame] = None,
                 poi_id_map: Optional[Dict] = None) -> Tuple[List[Dict], Dict]:
    """Process trips with proper temporal distribution accounting for mode differences"""
    
    routes_data = []
    animation_duration = animation_config['animation_duration']
    frames_per_hour = animation_duration / 24
    
    debug = {
        'original_total': 0,
        'distributed_total': 0,
        'skipped_pois': set(),
        'filtered_by_distance': 0
    }

    # Get the POI name based on direction
    def get_poi_name(row):
        try:
            if direction == 'inbound':
                return standardize_poi_name(row['destination'])
            else:  # outbound
                return standardize_poi_name(row['origin_zone'])
        except KeyError as e:
            logger.error(f"Missing column when getting POI name: {e}")
            logger.debug(f"Available columns: {row.index.tolist()}")
            return None

    # Function to calculate route distance in kilometers
    def calculate_route_distance(geometry):
        # Calculate total distance of the route in kilometers
        total_distance = 0
        coords = list(geometry.coords)
        
        for i in range(1, len(coords)):
            # Calculate Haversine distance between consecutive points
            lon1, lat1 = coords[i-1]
            lon2, lat2 = coords[i]
            
            # Convert to radians
            lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
            
            # Haversine formula
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
            c = 2 * np.arcsin(np.sqrt(a))
            r = 6371  # Radius of earth in kilometers
            distance = c * r
            
            total_distance += distance
            
        return total_distance

    # Convert temporal_dist values from DataFrame to array if needed
    processed_temporal_dist = {}
    for poi, dist_data in temporal_dist.items():
        if isinstance(dist_data, pd.DataFrame):
            mode_col = 'pedestrian_dist' if mode == 'walk' else 'car_dist'
            processed_temporal_dist[poi] = dist_data[mode_col].values
        else:
            processed_temporal_dist[poi] = dist_data
    
    for idx, row in trips_gdf.iterrows():
        try:
            # Filter out trips longer than 30 km
            route_distance = calculate_route_distance(row.geometry)
            if route_distance > 30:
                debug['filtered_by_distance'] += 1
                continue
                
            # 1. Get base trip count
            base_trips = float(row['num_trips'])
            debug['original_total'] += base_trips
            
            # 2. Get temporal distribution
            poi_name = get_poi_name(row)
            if not poi_name:
                continue
                
            if poi_name not in processed_temporal_dist:
                debug['skipped_pois'].add(poi_name)
                logger.warning(f"POI {poi_name} not found in temporal distribution")
                continue
            
            hourly_dist = processed_temporal_dist[poi_name]
            
            # 3. Handle mode-specific route generation
            if mode == 'walk':
                # For walking, each route represents exactly one trip
                # Find the most likely hour based on distribution
                hour = np.random.choice(24, p=hourly_dist)
                
                # UPDATED: Use speed_factor instead of speed_multiplier
                speed_factor = mode_settings.get('speed_factor', 1.0)
                
                route = {
                    'path': [[float(p[0]), float(p[1])] for p in row.geometry.coords],
                    'startTime': int(hour * frames_per_hour),
                    'duration': int(frames_per_hour * speed_factor),
                    'numTrips': 1,  # Always 1 for walking
                    'mode': mode,
                    'poi': poi_name
                }
                routes_data.append(route)
                debug['distributed_total'] += 1
                
            else:  # car mode
                # For cars, distribute the base trips across hours
                for hour in range(24):
                    trips_in_hour = base_trips * hourly_dist[hour]
                    if trips_in_hour > 0:
                        # UPDATED: Use speed_factor instead of speed_multiplier
                        speed_factor = mode_settings.get('speed_factor', 1.0)
                        
                        route = {
                            'path': [[float(p[0]), float(p[1])] for p in row.geometry.coords],
                            'startTime': int(hour * frames_per_hour),
                            'duration': int(frames_per_hour * speed_factor),
                            'numTrips': float(trips_in_hour),
                            'mode': mode,
                            'poi': poi_name
                        }
                        routes_data.append(route)
                        debug['distributed_total'] += trips_in_hour
                    
        except Exception as e:
            logger.error(f"Error processing row {idx}: {str(e)}")
            continue

    # Log validation info
    logger.info(f"\nValidation for {mode} {direction}:")
    logger.info(f"Original total trips: {debug['original_total']:.2f}")
    logger.info(f"Distributed total trips: {debug['distributed_total']:.2f}")
    logger.info(f"Difference: {(debug['distributed_total'] - debug['original_total']):.2f}")
    logger.info(f"Trips filtered by distance (>30km): {debug['filtered_by_distance']}")
    if debug['skipped_pois']:
        logger.warning(f"Skipped POIs: {', '.join(debug['skipped_pois'])}")

    return routes_data, debug

def validate_generated_trips(routes_data: List[Dict], original_counts: Dict[str, float],
                           debug_info: Dict, max_increase: float = 1.2):
    """
    Validate generated trips against original counts with detailed reporting
    """
    logger.info("\nValidating generated trips against original counts")
    
    generated_counts = {}
    for route in routes_data:
        poi = route['poi']
        trips = route.get('numTrips', 1)  # Default to 1 if not specified
        generated_counts[poi] = generated_counts.get(poi, 0) + trips
    
    validation_results = []
    for poi in set(list(original_counts.keys()) + list(generated_counts.keys())):
        original = original_counts.get(poi, 0)
        generated = generated_counts.get(poi, 0)
        
        if original > 0:
            increase = generated / original
            status = (
                "OK" if increase <= max_increase
                else "WARNING: High increase"
            )
        else:
            increase = float('inf')
            status = "WARNING: No original trips"
            
        validation_results.append({
            'poi': poi,
            'original': original,
            'generated': generated,
            'increase': increase,
            'status': status
        })
    
    # Sort by status (warnings first) then by POI name
    validation_results.sort(key=lambda x: (not x['status'].startswith("WARNING"), x['poi']))
    
    logger.info("\nValidation Results:")
    for result in validation_results:
        logger.info(f"\n{result['poi']}:")
        logger.info(f"  Original:  {result['original']:,.1f}")
        logger.info(f"  Generated: {result['generated']:,.1f}")
        logger.info(f"  Change:    {(result['increase']-1)*100:+.1f}%")
        logger.info(f"  Status:    {result['status']}")

def randomize_trip_timing(routes_data, animation_config):
    """
    Randomize trip timing without duplicating routes or increasing trip counts.
    This makes traffic patterns more natural without inflating file size.
    """
    frames_per_hour = animation_config['frames_per_hour']
    
    for route in routes_data:
        # Get the hour segment this trip belongs to
        hour = int(route['startTime'] / frames_per_hour)
        
        # Add random offset within the hour (±20% of hour)
        offset_range = frames_per_hour * 0.4
        offset = (random.random() - 0.5) * offset_range
        
        # Apply offset but keep within valid range
        route['startTime'] = max(0, min(
            animation_config['animation_duration'] - 1,
            route['startTime'] + offset
        ))
        
        # Slightly extend duration to increase visual simultaneity
        # without duplicating trips
        route['duration'] = route['duration'] * 1.2
    
    return routes_data

#############################################
# HTML Generation
#############################################

def create_deck_html(routes_data, animation_duration, poi_colors, viewport, mode, direction, model_outline):
    """Create HTML visualization with natural trip distribution and unified speed control."""
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
    
    # Get mode and direction specific settings
    mode_settings = get_mode_settings(mode)
    direction_settings = get_direction_settings(direction)
    
    # Define animation JavaScript with improved speed control and smooth movement
    animation_js = f"""
            // Animation control variables
            let isRecording = false, controlledFrame = 0, renderComplete = false, frameCounter = 0;
            let lastFrameTime = performance.now(), lastFrame = -1, lastHour = -1, lastCacheUpdate = 0;
            const MODE_SETTINGS = {json.dumps(mode_settings)};
            let animationSpeed = 1.0;  // Default animation speed (1.0 = normal speed)
            let cachedActiveTrips = null;
            const BASE_FPS = 30;
            const FADE_IN_FRAMES = 15;  // Number of frames for fade-in effect
            const FADE_OUT_FRAMES = 20; // Number of frames for fade-out effect
            
            // Frame control API for recorder
            window.setAnimationFrame = function(frame) {{
                controlledFrame = frame;
                isRecording = true;
                renderComplete = false;
                return true;
            }};
            
            window.isFrameRendered = function() {{
                return renderComplete;
            }};
            
            window.setNormalPlayback = function() {{
                isRecording = false;
            }};
            
            // Unified speed control - applies to both recording and normal playback
            window.setAnimationSpeed = function(speed) {{
                // Higher value = faster animation (multiplier)
                animationSpeed = parseFloat(speed);
                console.log(`Animation speed set to: ${{animationSpeed}}`);
                return animationSpeed;
            }};
            
            window.getCurrentFrame = function() {{
                return isRecording ? controlledFrame : frameCounter;
            }};
            
            // Pre-process route paths for more uniform movement
            if (!window.pathsProcessed) {{
                // Create a distance array for each path
                ROUTES_DATA.forEach(route => {{
                    if (!route.path || route.path.length < 2) return;
                    
                    // Calculate cumulative distance for each point in path
                    const distances = [0]; // First point has distance 0
                    let totalDistance = 0;
                    
                    for (let i = 1; i < route.path.length; i++) {{
                        const prevPoint = route.path[i-1];
                        const currPoint = route.path[i];
                        
                        // Calculate distance between points using Haversine formula
                        const dx = currPoint[0] - prevPoint[0];
                        const dy = currPoint[1] - prevPoint[1];
                        const distance = Math.sqrt(dx*dx + dy*dy);
                        
                        totalDistance += distance;
                        distances.push(totalDistance);
                    }}
                    
                    // Store distance information with the route
                    route.pathDistances = distances;
                    route.totalDistance = totalDistance;
                    
                    // Pre-calculate uniform timestamps for smoother movement
                    route.uniformTimestamps = route.path.map((_, i) => {{
                        // Calculate timestamp based on proportional distance
                        // This ensures uniform speed along the route
                        const progress = distances[i] / totalDistance;
                        return route.startTime + (progress * route.duration);
                    }});
                }});
                
                window.pathsProcessed = true;
            }}
            
            // Process trips with consistent window and smooth transitions
            function processTrips(currentFrame) {{
                const currentTime = performance.now();
                const currentHour = Math.floor((currentFrame / ANIMATION_DURATION) * 24);
                
                // Use cache if available
                if (currentFrame === lastFrame && cachedActiveTrips && currentHour === lastHour && 
                    (currentTime - lastCacheUpdate) < 1000) {{
                    return cachedActiveTrips;
                }}
                
                lastFrame = currentFrame;
                lastHour = currentHour;
                lastCacheUpdate = currentTime;
                
                // Apply natural time distribution once at initialization
                if (!window.tripsRandomized) {{
                    ROUTES_DATA.forEach(r => {{
                        if (!r.originalStartTime) {{
                            // Store original start time
                            r.originalStartTime = r.startTime;
                            
                            // Get the hour segment this trip belongs to
                            const hour = Math.floor(r.startTime / (ANIMATION_DURATION / 24));
                            const hourRange = ANIMATION_DURATION / 24;
                            
                            // Simple random offset (±30% of an hour)
                            const offset = (Math.random() - 0.5) * 0.6 * hourRange;
                            r.startTime = Math.max(0, Math.min(ANIMATION_DURATION - 1, r.startTime + offset));
                            
                            // Extended duration to make transitions smoother
                            // This doesn't affect trip counts, just visual duration
                            r.duration = r.duration * 1.5;
                            
                            // Update uniform timestamps with new start time
                            if (r.uniformTimestamps && r.totalDistance > 0) {{
                                r.uniformTimestamps = r.path.map((_, i) => {{
                                    const progress = r.pathDistances[i] / r.totalDistance;
                                    return r.startTime + (progress * r.duration);
                                }});
                            }}
                        }}
                    }});
                    window.tripsRandomized = true;
                }}
                
                // Find active trips with consistent window for simultaneity and add opacity transitions
                const simultaneityFactor = MODE_SETTINGS.simultaneity_factor || 1.5;
                const activeTrips = [];
                
                ROUTES_DATA.forEach(r => {{
                    if (!(typeof r.startTime === 'number' && typeof r.duration === 'number' && 
                          Array.isArray(r.path) && r.path.length >= 2)) {{
                        return;
                    }}
                    
                    const elapsedTime = (currentFrame - r.startTime) % ANIMATION_DURATION;
                    // Use simultaneity factor for visibility window but avoid duplicating trips
                    const extendedDuration = r.duration * simultaneityFactor;
                    
                    // Basic visibility check
                    if (elapsedTime >= 0 && elapsedTime <= extendedDuration) {{
                        // Calculate opacity for smooth transitions
                        let opacity = MODE_SETTINGS.opacity;
                        
                        // Fade in effect
                        if (elapsedTime < FADE_IN_FRAMES) {{
                            opacity = (elapsedTime / FADE_IN_FRAMES) * opacity;
                        }}
                        
                        // Fade out effect
                        if (elapsedTime > extendedDuration - FADE_OUT_FRAMES) {{
                            const fadeOutProgress = (extendedDuration - elapsedTime) / FADE_OUT_FRAMES;
                            opacity = Math.max(0, fadeOutProgress * opacity);
                        }}
                        
                        // Clone the trip data and add opacity
                        const tripWithOpacity = {{ 
                            ...r, 
                            calculatedOpacity: opacity
                        }};
                        activeTrips.push(tripWithOpacity);
                    }}
                }});
                
                cachedActiveTrips = activeTrips;
                return activeTrips;
            }}
            
            // Animation loop with consistent speed model
            function animate() {{
                const now = performance.now();
                const deltaTime = now - lastFrameTime;
                lastFrameTime = now;
                
                // Determine current frame with unified speed control
                let frame;
                if (isRecording) {{
                    // In recording mode, just use the controlled frame
                    frame = controlledFrame;
                }} else {{
                    // In normal playback, advance frames based on deltaTime and animationSpeed
                    // Multiply by animationSpeed to speed up when value is higher
                    const frameAdvancement = (deltaTime / 1000) * BASE_FPS * animationSpeed;
                    frameCounter = (frameCounter + frameAdvancement) % ANIMATION_DURATION;
                    frame = Math.floor(frameCounter);
                }}
                
                // Create layers
                const modelOutline = new deck.GeoJsonLayer({{
                    id: 'model-outline',
                    data: {json.dumps(model_geojson)},
                    stroked: true,
                    filled: false,
                    lineWidthMinPixels: 1,
                    getLineColor: [255, 255, 255, 128],
                    getLineWidth: 1
                }});

                // TripsLayer with consistent speed and smooth transitions
                const trips = new deck.TripsLayer({{
                    id: 'trips',
                    data: processTrips(frame),
                    getPath: d => d.path,
                    getTimestamps: d => {{
                        try {{
                            // Use pre-calculated uniform timestamps for smooth motion
                            if (d.uniformTimestamps && d.uniformTimestamps.length === d.path.length) {{
                                return d.uniformTimestamps;
                            }}
                            
                            // Fall back to dynamic calculation if needed
                            // Using distance-based timestamps for uniform movement
                            if (d.pathDistances && d.totalDistance > 0) {{
                                return d.path.map((_, i) => {{
                                    const progress = d.pathDistances[i] / d.totalDistance;
                                    return d.startTime + (progress * d.duration);
                                }});
                            }}
                            
                            // Last resort: linear timestamps (less smooth on uneven paths)
                            return d.path.map((_, i) => {{
                                const progress = i / (d.path.length - 1);
                                return d.startTime + (progress * d.duration);
                            }});
                        }} catch (e) {{
                            console.error('Error in getTimestamps:', e);
                            return new Array(d.path.length).fill(0);
                        }}
                    }},
                    getColor: d => {{
                        const baseColor = POI_COLORS[d.poi] || [253, 128, 93];
                        return baseColor;
                    }},
                    getWidth: d => d.mode === 'walk' ? MODE_SETTINGS.min_width : MODE_SETTINGS.min_width * 2,
                    opacity: d => d.calculatedOpacity !== undefined ? d.calculatedOpacity : MODE_SETTINGS.opacity,
                    widthMinPixels: MODE_SETTINGS.min_width,
                    widthMaxPixels: MODE_SETTINGS.max_width,
                    jointRounded: true,
                    capRounded: true,
                    trailLength: MODE_SETTINGS.trail_length * 1.5, // Longer trail for smoother appearance
                    currentTime: frame,
                    shadowEnabled: false
                }});
                
                // Update deck.gl and signal completion
                deckgl.setProps({{
                    layers: [modelOutline, trips],
                    onAfterRender: () => {{ renderComplete = true; }}
                }});
                
                // Update progress indicator
                const progress = (frame / ANIMATION_DURATION) * 100;
                document.querySelector('.progress').style.width = progress + '%';
                
                // Continue animation
                requestAnimationFrame(animate);
            }}
    """
    
    # Generate HTML with speed control UI
    return f"""<!DOCTYPE html>
<html>
<head>
<script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
<style>
body,html{{margin:0;padding:0;background:#000}}
#container{{width:100vw;height:100vh}}
canvas{{background:#000!important}}
#loading{{position:fixed;top:10px;left:10px;background:rgba(0,0,0,0.7);color:white;padding:10px;border-radius:5px;font-family:monospace;}}
.progress-bar{{position:fixed;bottom:0;left:0;width:100%;height:4px;background:#333}}
.progress{{height:100%;width:0;background:#0f0}}
.speed-controls{{position:fixed;top:10px;right:10px;background:rgba(0,0,0,0.7);color:white;padding:10px;border-radius:5px;z-index:1000;font-family:sans-serif;}}
</style>
</head>
<body>
<div id="container"></div>
<div id="loading">Initializing...</div>
<div class="progress-bar"><div class="progress"></div></div>
<div class="speed-controls">
    <div style="margin-bottom:10px;font-size:14px;">Animation Speed</div>
    <div style="display:flex;align-items:center;">
        <span style="margin-right:5px;font-size:12px;">Slower</span>
        <input type="range" id="speedSlider" min="0.1" max="5" step="0.1" value="1" style="width:120px;">
        <span style="margin-left:5px;font-size:12px;">Faster</span>
    </div>
    <div style="text-align:center;margin-top:5px;font-family:monospace;" id="speedValue">1.0x</div>
</div>

<script>
const ANIMATION_DURATION={animation_duration};
const ROUTES_DATA={routes_json};
const POI_COLORS={poi_colors_json};

// Set up lighting
const ambientLight=new deck.AmbientLight({{color:[255,255,255],intensity:1.0}});
const pointLight=new deck.PointLight({{color:[255,255,255],intensity:2.0,position:[34.8,31.25,8000]}});
const lightingEffect=new deck.LightingEffect({{ambientLight,pointLight}});

// Initialize deck.gl
const deckgl=new deck.DeckGL({{
    container:'container',
    initialViewState:{viewport_json},
    controller:true,
    effects:[lightingEffect],
    parameters:{{
        clearColor:[0,0,0,0],
        blend:true,
        blendFunc:[WebGLRenderingContext.SRC_ALPHA,WebGLRenderingContext.ONE_MINUS_SRC_ALPHA],
        depthTest:true,
        depthFunc:WebGLRenderingContext.LEQUAL
    }},
    glOptions:{{webgl2:true,webgl1:true,preserveDrawingBuffer:true}},
    onWebGLInitialized:gl=>{{gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA)}},
    onLoad:()=>{{document.getElementById('loading').style.display='none';window.deckglLoaded=true}}
}});

// Add animation code
{animation_js}

// Start animation
setTimeout(()=>{{animate();window.animationStarted=true}},1000);

// Setup speed control
document.addEventListener('DOMContentLoaded', function() {{
    const speedSlider = document.getElementById('speedSlider');
    const speedValue = document.getElementById('speedValue');
    
    speedSlider.addEventListener('input', function() {{
        const speed = parseFloat(this.value);
        speedValue.textContent = speed.toFixed(1) + 'x';
        window.setAnimationSpeed(speed);
    }});
}});
</script>
</body>
</html>"""

#############################################
# Utility Functions
#############################################

def load_model_outline(shapefile_path):
    """Load model outline and convert to web mercator projection"""
    try:
        model = gpd.read_file(shapefile_path)
        if model.crs != 'EPSG:4326':
            model = model.to_crs('EPSG:4326')
        
        # Get the first geometry and its bounds
        geometry = model.geometry.iloc[0]
        bounds = geometry.bounds
        
        return geometry, bounds
    except Exception as e:
        logger.error(f"Error loading model outline: {str(e)}")
        raise

def get_optimal_viewport(bounds, model_size='big'):
    """Calculate optimal viewport settings based on geometry bounds with proper padding"""
    minx, miny, maxx, maxy = bounds
    
    # Calculate center point
    center_lon = (minx + maxx) / 2
    center_lat = (miny + maxy) / 2
    
    # Add padding - increased for large model
    padding = 0.15 if model_size == 'big' else 0.05  # 15% padding for big model, 5% for small
    width = maxx - minx
    height = maxy - miny
    padded_minx = minx - (width * padding)
    padded_miny = miny - (height * padding)
    padded_maxx = maxx + (width * padding)
    padded_maxy = maxy + (height * padding)
    
    # Calculate optimal zoom - adjusted for large model
    lat_zoom = np.log2(360 / (padded_maxy - padded_miny)) + 1
    lon_zoom = np.log2(360 / (padded_maxx - padded_minx)) + 1
    base_zoom = min(lat_zoom, lon_zoom)
    
    # Add extra zoom for small model, reduce for large model
    if model_size == 'small':
        base_zoom += 0.5
    else:
        base_zoom -= 0.35 # Zoom out more for large model
    
    return {
        'longitude': center_lon,
        'latitude': center_lat,
        'zoom': base_zoom,
        'pitch': 0,
        'bearing': 0
    }

#############################################
# Main Processing Function
#############################################

def load_trip_data(mode, direction):
    """Load and process trip data for visualization without trip inflation"""
    file_path = os.path.join(OUTPUT_DIR, f"{mode}_routes_{direction}.geojson")
    
    try:
        # Load base data
        trips_gdf = gpd.read_file(file_path)
        logger.info(f"Processing {mode} {direction} trips")
        logger.info(f"Loaded {len(trips_gdf)} trips from {file_path}")
        
        # Get settings
        mode_settings = get_mode_settings(mode)
        
        # Load temporal distributions
        temporal_dist = load_temporal_distributions(mode, direction, OUTPUT_DIR)
        
        # Get original trip counts for validation
        original_counts = get_original_trip_counts(trips_gdf, direction, mode)
        
        # Process trips based on mode WITHOUT enhanced simultaneity
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
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(script_dir))
            poi_path = os.path.join(project_root, 'shapes', 'data', 'maps', "Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
            poi_polygons = gpd.read_file(poi_path)
            poi_polygons = poi_polygons[poi_polygons['ID'].isin([11, 12, 7])]
            POI_ID_MAP = {7: 'BGU', 12: 'Gav Yam', 11: 'Soroka Hospital'}

            routes_data, debug_info = process_trips(
                trips_gdf=trips_gdf,
                temporal_dist=temporal_dist,
                mode_settings=mode_settings,
                direction=direction,
                mode=mode,
                animation_config=ANIMATION_CONFIG,
                poi_polygons=poi_polygons,
                poi_id_map=POI_ID_MAP
            )

        # Randomize timing without duplicating trips
        routes_data = randomize_trip_timing(routes_data, ANIMATION_CONFIG)
        
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
                logger.info(f"Trip data loaded successfully")
                routes_data, animation_duration, poi_colors = trip_data
                
                for model_size in models:
                    # Load model outline and create viewport
                    logger.info(f"Loading model outline for {model_size}")
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    project_root = os.path.dirname(os.path.dirname(script_dir))
                    model_path = os.path.join(project_root, 'data-viz', 'data', 'model_outline', f'{model_size} model.shp')
                    outline_data = load_model_outline(model_path)
                    model_outline, bounds = outline_data
                    
                    logger.info("Creating viewport with proper zoom level")
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
                logger.error(f"Error details:", exc_info=True)
                continue

if __name__ == "__main__":
    main()