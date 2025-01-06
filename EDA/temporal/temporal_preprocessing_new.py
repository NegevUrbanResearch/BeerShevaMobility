import pandas as pd
import geopandas as gpd
import numpy as np
import os
import logging
from pathlib import Path
import sys
from datetime import time

sys.path.append(str(Path(__file__).parent.parent))
# Add parent directory to path for imports
from config import OUTPUT_DIR, DATA_DIR, RAW_TRIPS_FILE
from utils.data_standards import DataStandardizer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define main POIs with their raw data names
POI_MAPPING = {
    'Ben-Gurion-University': 'BGU',
    'Gav-Yam-High-Tech-Park': 'Gev Yam',
    'Soroka-Medical-Center': 'Soroka Hospital'
}

# Mode mapping
MODE_MAPPING = {
    'car': ['car'],
    'pedestrian': ['ped'],
    'public_transit': ['bus', 'train', 'link'],
    'bike': ['bike']
}

def load_raw_trip_data():
    """Load raw trip data with temporal information"""
    logger.info(f"Loading raw trip data from: {RAW_TRIPS_FILE}")
    
    try:
        df = pd.read_excel(RAW_TRIPS_FILE, sheet_name='StageB1')
        logger.info(f"Loaded {len(df)} trips")
        
        # Convert time_bin to hour
        df['hour'] = df['time_bin'].apply(lambda x: x.hour if isinstance(x, time) else 0)
        
        # Convert mode to lowercase
        df['mode'] = df['mode'].str.lower()
        
        # Print sample of data
        logger.info("\nSample of raw data:")
        logger.info(df[['mode', 'time_bin', 'hour', 'count']].head())
        
        return df
        
    except Exception as e:
        logger.error(f"Error loading raw trip data: {str(e)}")
        raise

def calculate_poi_temporal_distributions(df, poi_name, trip_type='inbound'):
    """Calculate hourly distribution of trips to/from a POI by mode"""
    temporal_dist = {}
    
    # Use raw POI name for filtering
    raw_poi_name = POI_MAPPING.get(poi_name)
    if not raw_poi_name:
        logger.error(f"No raw name mapping found for POI: {poi_name}")
        return {}
        
    name_col = 'to_name' if trip_type == 'inbound' else 'from_name'
    poi_trips = df[df[name_col] == raw_poi_name].copy()
    
    logger.info(f"Processing {trip_type} trips for POI {poi_name}")
    logger.info(f"Found {len(poi_trips)} total trips")
    
    for std_mode, raw_modes in MODE_MAPPING.items():
        # Filter trips for this mode
        mode_trips = poi_trips[poi_trips['mode'].isin(raw_modes)]
        
        # Group by hour and sum counts
        hourly_trips = mode_trips.groupby('hour')['count'].sum()
        total_trips = hourly_trips.sum()
        
        logger.info(f"Mode {std_mode}: {total_trips:.1f} total trips")
        
        # Calculate distribution and ensure it sums to 100%
        if total_trips > 0:
            dist = [float(hourly_trips.get(hour, 0)) / total_trips for hour in range(24)]
            # Normalize to ensure sum is exactly 1.0
            sum_dist = sum(dist)
            temporal_dist[std_mode] = [d/sum_dist for d in dist]
            
            # Verify sum is 1.0
            logger.info(f"Distribution sum for {std_mode}: {sum(temporal_dist[std_mode]):.6f}")
        else:
            temporal_dist[std_mode] = [0] * 24
            
        # Print sample of hourly distribution
        if total_trips > 0:
            logger.info(f"\nSample hourly distribution for {std_mode}:")
            sample_hours = sorted(hourly_trips.head().index)
            for hour in sample_hours:
                pct = temporal_dist[std_mode][hour] * 100
                logger.info(f"Hour {hour:02d}:00 - {pct:.1f}%")
            
    return temporal_dist

def process_temporal_data():
    """Process temporal distributions for all POIs"""
    raw_trips = load_raw_trip_data()
    
    # Create dashboard_data directory if it doesn't exist
    dashboard_dir = os.path.join(OUTPUT_DIR)
    os.makedirs(dashboard_dir, exist_ok=True)
    
    # Get all standard POI names from DataStandardizer
    all_poi_names = set(DataStandardizer.POI_NAME_MAPPING.values())
    logger.info(f"\nProcessing temporal distributions for {len(all_poi_names)} POIs:")
    logger.info(', '.join(sorted(all_poi_names)))
    
    # Track city-wide averages
    city_averages = [0] * 24
    valid_poi_count = 0
    
    # Process each POI
    for std_poi_name in sorted(all_poi_names):
        # Skip focus POIs as they're handled separately
        if std_poi_name in POI_MAPPING.keys():
            continue
            
        # Find the raw name(s) for this POI
        raw_names = [k for k, v in DataStandardizer.POI_NAME_MAPPING.items() 
                    if v == std_poi_name]
        
        if not raw_names:
            logger.error(f"No raw name found for POI: {std_poi_name}")
            continue
            
        logger.info(f"\nProcessing temporal distributions for POI: {std_poi_name}")
        logger.info(f"Raw names: {', '.join(raw_names)}")
        
        for trip_type in ['inbound', 'outbound']:
            try:
                # Combine data for all raw names of this POI
                all_temporal_dist = {}
                valid_distributions = 0
                
                for raw_name in raw_names:
                    temporal_dist = calculate_poi_temporal_distributions_raw(
                        raw_trips, raw_name, trip_type
                    )
                    
                    # Only include distributions that have actual trips
                    if temporal_dist and any(sum(dist) > 0 for dist in temporal_dist.values()):
                        valid_distributions += 1
                        # Combine distributions
                        for mode, dist in temporal_dist.items():
                            if mode not in all_temporal_dist:
                                all_temporal_dist[mode] = dist
                            else:
                                # Average the distributions
                                all_temporal_dist[mode] = [
                                    (a + b) / 2 for a, b in zip(all_temporal_dist[mode], dist)
                                ]
                
                # Only save if we have valid distributions
                if all_temporal_dist and valid_distributions > 0:
                    # Normalize the final distributions
                    for mode in all_temporal_dist:
                        total = sum(all_temporal_dist[mode])
                        if total > 0:
                            all_temporal_dist[mode] = [d/total for d in all_temporal_dist[mode]]
                            
                            # Additional validation for midnight values
                            if all_temporal_dist[mode][0] > 0.05:
                                logger.warning(f"High midnight value ({all_temporal_dist[mode][0]:.1%}) "
                                             f"for {std_poi_name} {mode}")
                    
                    # Add to city average if this is inbound and midnight value is reasonable
                    if trip_type == 'inbound' and all_temporal_dist['all'][0] <= 0.05:
                        valid_poi_count += 1
                        for hour in range(24):
                            city_averages[hour] += all_temporal_dist['all'][hour]
                    
                    output_file = os.path.join(
                        dashboard_dir,
                        f"{std_poi_name.lower().replace('-', '_')}_{trip_type}_temporal.csv"
                    )
                    
                    temporal_df = pd.DataFrame({
                        'hour': range(24),
                        **{f'{mode}_dist': dist for mode, dist in all_temporal_dist.items()}
                    })
                    
                    temporal_df.to_csv(output_file, index=False)
                    logger.info(f"Saved {trip_type} temporal distribution to: {output_file} "
                              f"(from {valid_distributions} valid distributions)")
                else:
                    logger.warning(f"Skipping {std_poi_name} {trip_type} - no valid trips found")
                
            except Exception as e:
                logger.error(f"Error processing POI {std_poi_name}: {str(e)}")
    
    # Normalize and validate city averages
    if valid_poi_count > 0:
        # Normalize by number of valid POIs
        city_averages = [x / valid_poi_count for x in city_averages]
        
        # Log the number of POIs used in the average
        logger.info(f"\nCity-wide average calculated from {valid_poi_count} valid POIs")
        
        # Validate sum and midnight values
        total_avg = sum(city_averages)
        logger.info(f"City-wide average distribution sum: {total_avg:.6f}")
        if not (0.99 <= total_avg <= 1.01):
            logger.error(f"City average distribution does not sum to 1.0 ({total_avg:.6f})")
        
        midnight_value = city_averages[0]
        if midnight_value > 0.05:
            logger.warning(f"Suspicious midnight value in city average: {midnight_value:.1%}")
    
    return "Processing complete"

def calculate_poi_temporal_distributions_raw(df, raw_poi_name, trip_type='inbound'):
    """Calculate hourly distribution for POIs using raw names directly"""
    temporal_dist = {}
    
    name_col = 'to_name' if trip_type == 'inbound' else 'from_name'
    poi_trips = df[df[name_col] == raw_poi_name].copy()
    
    # Skip problematic POIs
    if raw_poi_name in ['Ramat Hovav Industry', 'Ramat Hovav']:
        logger.warning(f"Skipping known problematic POI: {raw_poi_name}")
        return {}
    
    # Validate midnight trips
    midnight_trips = poi_trips[poi_trips['hour'] == 0]
    if len(midnight_trips) > 0:
        total_trips = poi_trips['count'].sum()
        midnight_total = midnight_trips['count'].sum()
        midnight_pct = midnight_total / total_trips if total_trips > 0 else 0
        if midnight_pct > 0.05:  # Flag if midnight has more than 5% of POI's trips
            logger.warning(f"High midnight traffic for {raw_poi_name}: {midnight_pct:.1%}")
            logger.warning("Sample of midnight trips:")
            logger.warning(midnight_trips[['mode', 'count', 'time_bin']].head())
            
            # If midnight traffic is extremely high (over 20%), skip this POI
            if midnight_pct > 0.20:
                logger.error(f"Skipping {raw_poi_name} due to abnormal midnight traffic distribution")
                return {}
    
    logger.info(f"Processing {trip_type} trips for POI {raw_poi_name}")
    logger.info(f"Found {len(poi_trips)} total trips")
    
    # Skip if no trips found
    if len(poi_trips) == 0:
        logger.warning(f"No {trip_type} trips found for {raw_poi_name}")
        return {}
    
    # First calculate total distribution across all modes
    hourly_total = poi_trips.groupby('hour')['count'].sum()
    total_trips = hourly_total.sum()
    
    if total_trips > 0:
        # Calculate raw distribution
        total_dist = [float(hourly_total.get(hour, 0)) / total_trips for hour in range(24)]
        # Normalize to ensure sum is exactly 1.0
        sum_dist = sum(total_dist)
        temporal_dist['all'] = [d/sum_dist for d in total_dist] if sum_dist > 0 else [0] * 24
        logger.info(f"Total trips: {total_trips:.1f}")
        logger.info(f"Distribution sum for all modes: {sum(temporal_dist['all']):.6f}")
    else:
        return {}  # Return empty if no trips
    
    # Then calculate per-mode distributions
    for std_mode, raw_modes in MODE_MAPPING.items():
        # Filter trips for this mode
        mode_trips = poi_trips[poi_trips['mode'].isin(raw_modes)]
        
        # Group by hour and sum counts
        hourly_trips = mode_trips.groupby('hour')['count'].sum()
        mode_total = hourly_trips.sum()
        
        logger.info(f"Mode {std_mode}: {mode_total:.1f} total trips")
        
        # Calculate distribution
        if mode_total > 0:
            dist = [float(hourly_trips.get(hour, 0)) / mode_total for hour in range(24)]
            temporal_dist[std_mode] = dist
        else:
            temporal_dist[std_mode] = [0] * 24
            
    return temporal_dist

if __name__ == "__main__":
    try:
        result = process_temporal_data()
        print(result)
    except Exception as e:
        logger.error(f"Failed to process temporal data: {str(e)}")
        sys.exit(1)
