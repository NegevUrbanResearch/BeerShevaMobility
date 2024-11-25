import pandas as pd
import geopandas as gpd
import numpy as np
import os
import logging
from pathlib import Path
import sys
from datetime import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    """Process temporal distributions for main POIs"""
    raw_trips = load_raw_trip_data()
    
    # Create dashboard_data directory if it doesn't exist
    dashboard_dir = os.path.join(OUTPUT_DIR)
    os.makedirs(dashboard_dir, exist_ok=True)
    
    # Process only main POIs
    for poi_name in POI_MAPPING.keys():
        logger.info(f"Processing temporal distributions for {poi_name}")
        
        for trip_type in ['inbound', 'outbound']:
            temporal_dist = calculate_poi_temporal_distributions(
                raw_trips, poi_name, trip_type
            )
            
            output_file = os.path.join(
                dashboard_dir,
                f"{poi_name.lower().replace('-', '_')}_{trip_type}_temporal.csv"
            )
            
            temporal_df = pd.DataFrame({
                'hour': range(24),
                **{f'{mode}_dist': dist for mode, dist in temporal_dist.items()}
            })
            
            temporal_df.to_csv(output_file, index=False)
            logger.info(f"Saved {trip_type} temporal distribution to: {output_file}")
    
    return "Processing complete"

if __name__ == "__main__":
    try:
        result = process_temporal_data()
        print(result)
    except Exception as e:
        logger.error(f"Failed to process temporal data: {str(e)}")
        sys.exit(1)
