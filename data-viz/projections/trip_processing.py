import logging
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import Point
from typing import Dict, List, Tuple, Optional, Union
import os


logger = logging.getLogger(__name__)

def analyze_input_data(trips_gdf: gpd.GeoDataFrame, mode: str, direction: str):
    """Analyze input data structure and contents"""
    logger.info(f"\n{'='*80}")
    logger.info(f"INPUT DATA ANALYSIS: {mode.upper()} {direction.upper()}")
    logger.info(f"{'='*80}")
    
    # Basic dataset info
    logger.info(f"\nDataset Overview:")
    logger.info(f"Total rows: {len(trips_gdf)}")
    logger.info(f"Columns: {trips_gdf.columns.tolist()}")
    
    # Sample first few rows (excluding geometry)
    logger.info("\nFirst 5 rows sample:")
    for idx, row in trips_gdf.head().iterrows():
        logger.info(f"\nRow {idx}:")
        for col in trips_gdf.columns:
            if col != 'geometry':  # Skip geometry column
                logger.info(f"  {col}: {row[col]}")
    
    # Analyze key fields
    key_fields = {
        'car': ['num_trips', 'origin_zone', 'destination'],
        'walk': ['num_trips', 'origin_zone', 'destination', 'entrance', 'zone_total_trips', 'zone_ped_trips']
    }
    
    logger.info(f"\nKey Fields Analysis for {mode}:")
    for field in key_fields[mode]:
        if field in trips_gdf.columns:
            if pd.api.types.is_numeric_dtype(trips_gdf[field]):
                logger.info(f"\n{field}:")
                logger.info(f"  Min: {trips_gdf[field].min()}")
                logger.info(f"  Max: {trips_gdf[field].max()}")
                logger.info(f"  Mean: {trips_gdf[field].mean():.2f}")
                logger.info(f"  Sum: {trips_gdf[field].sum():.2f}")
            else:
                unique_vals = trips_gdf[field].unique()
                logger.info(f"\n{field} unique values ({len(unique_vals)}):")
                for val in unique_vals[:10]:  # Show first 10
                    logger.info(f"  {val}")
                if len(unique_vals) > 10:
                    logger.info("  ...")
        else:
            logger.warning(f"Missing expected field: {field}")

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

def validate_zone_info(trips_gdf: gpd.GeoDataFrame, direction: str):
    """Validate statistical zone information"""
    logger.info("\nValidating Zone Information:")
    
    # Analyze origin zones
    if 'origin_zone' in trips_gdf.columns:
        unique_origins = trips_gdf['origin_zone'].unique()
        logger.info(f"\nUnique origin zones ({len(unique_origins)}):")
        logger.info(f"Sample: {unique_origins[:5]}")
        
    # Analyze destinations
    if 'destination' in trips_gdf.columns:
        unique_dests = trips_gdf['destination'].unique()
        logger.info(f"\nUnique destinations ({len(unique_dests)}):")
        logger.info(f"Sample: {unique_dests[:5]}")
    
    # Check for potential zone format issues
    for col in ['origin_zone', 'destination']:
        if col in trips_gdf.columns:
            non_standard = trips_gdf[col].apply(
                lambda x: not (isinstance(x, (int, str)) or pd.isna(x))
            ).sum()
            if non_standard > 0:
                logger.warning(f"Found {non_standard} non-standard values in {col}")

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
        'skipped_pois': set()
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
                route = {
                    'path': [[float(p[0]), float(p[1])] for p in row.geometry.coords],
                    'startTime': int(hour * frames_per_hour),
                    'duration': int(frames_per_hour * mode_settings['speed_multiplier']),
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
                        route = {
                            'path': [[float(p[0]), float(p[1])] for p in row.geometry.coords],
                            'startTime': int(hour * frames_per_hour),
                            'duration': int(frames_per_hour * mode_settings['speed_multiplier']),
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
    if debug['skipped_pois']:
        logger.warning(f"Skipped POIs: {', '.join(debug['skipped_pois'])}")

    return routes_data, debug

def distribute_trips_to_hours(num_trips: float, temporal_dist: np.ndarray, 
                            min_threshold: float) -> Dict[int, float]:
    """
    Distribute trips across hours while preserving temporal distribution pattern
    """
    distributed_trips = {}
    remaining_trips = num_trips
    
    # First pass - allocate main distribution
    for hour in range(24):
        hour_fraction = temporal_dist[hour]
        if hour_fraction > min_threshold:
            hour_trips = round(num_trips * hour_fraction)
            if hour_trips > 0:
                distributed_trips[hour] = hour_trips
                remaining_trips -= hour_trips
    
    # Second pass - distribute remaining trips to peak hours
    if remaining_trips > 0:
        peak_hours = sorted(
            range(24),
            key=lambda x: temporal_dist[x],
            reverse=True
        )[:3]  # Use top 3 peak hours
        
        for hour in peak_hours:
            if remaining_trips > 0:
                if hour not in distributed_trips:
                    distributed_trips[hour] = 0
                additional = min(remaining_trips, round(remaining_trips / len(peak_hours)))
                distributed_trips[hour] += additional
                remaining_trips -= additional
    
    return distributed_trips

def log_processing_summary(debug_info: Dict, total_trips: float, total_routes: int):
    """Focused logging of processing summary"""
    logger.info("\n" + "="*80)
    logger.info("PROCESSING SUMMARY")
    logger.info("="*80)
    
    logger.info(f"\nTotal routes: {total_routes}")
    logger.info(f"Total trips: {total_trips:,.0f}")
    
    # Only log non-zero dropped trips
    dropped = {k: v for k, v in debug_info['dropped_trips'].items() if v > 0}
    if dropped:
        logger.info("\nDropped Trips:")
        for reason, count in dropped.items():
            logger.info(f"  {reason}: {count}")
    
    logger.info("\nTrips by POI:")
    for poi, count in debug_info['trips_by_poi'].items():
        logger.info(f"  {poi}: {count:,.0f}")
    
    # Only log hours with activity
    active_hours = {h: c for h, c in debug_info['hourly_counts'].items() 
                   if c['actual'] > 0}
    if active_hours:
        logger.info("\nActive Hours:")
        for hour, counts in active_hours.items():
            logger.info(f"\nHour {hour:02d}:00: {counts['actual']:,.0f} trips")
            for poi, count in counts['by_poi'].items():
                if count > 0:
                    logger.info(f"  {poi}: {count:,.0f}")

def determine_poi(coords: tuple, 
                 poi_polygons: gpd.GeoDataFrame,
                 poi_id_map: Dict[int, str]) -> Optional[str]:
    """Determine POI from coordinates with validation"""
    try:
        point = Point(coords)
        for _, poi in poi_polygons.iterrows():
            if poi.geometry.contains(point):
                poi_id = poi['ID']
                poi_name = poi_id_map.get(poi_id)
                logger.debug(f"POI determination: {coords} -> {poi_name} (ID: {poi_id})")
                return poi_name
        logger.debug(f"No POI found for coordinates: {coords}")
        return None
    except Exception as e:
        logger.error(f"Error determining POI: {str(e)}")
        return None


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

def get_mode_settings(mode: str) -> Dict:
    """
    Get mode-specific animation settings with validation
    
    Args:
        mode: 'car' or 'walk'
    
    Returns:
        Dictionary of mode settings
    """
    if mode not in ['car', 'walk']:
        logger.warning(f"Invalid mode: {mode}, defaulting to walk settings")
        mode = 'walk'
        
    if mode == 'car':
        return {
            "speed_multiplier": 2.0,
            "path_multiplier": 30,
            "trail_length": 5,
            "min_width": 2,
            "max_width": 4,
            "opacity": 0.8,
            "animation_offset": 0
        }
    else:  # walk
        return {
            "speed_multiplier": 1.0,
            "path_multiplier": 45,
            "trail_length": 3,
            "min_width": 1,
            "max_width": 2,
            "opacity": 0.7,
            "animation_offset": 0
        }

def get_direction_settings(direction: str) -> Dict:
    """
    Get direction-specific settings
    
    Args:
        direction: 'inbound' or 'outbound'
    
    Returns:
        Dictionary of direction settings
    """
    if direction not in ['inbound', 'outbound']:
        logger.warning(f"Invalid direction: {direction}, defaulting to inbound settings")
        direction = 'inbound'
        
    return {
        "inbound": {
            "reverse_coords": False,
            "poi_index": -1
        },
        "outbound": {
            "reverse_coords": True,
            "poi_index": 0
        }
    }.get(direction, {})

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

def validate_generated_trips(routes_data: List[Dict], original_counts: Dict[str, float],
                           debug_info: Dict, max_increase: float = 1.2):
    """
    Validate generated trips against original counts with detailed reporting
    """
    logger.info("\nValidating generated trips against original counts")
    
    generated_counts = {}
    for route in routes_data:
        poi = route['poi']
        trips = route['numTrips']
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

