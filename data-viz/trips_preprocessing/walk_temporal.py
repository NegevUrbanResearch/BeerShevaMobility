import pandas as pd
import geopandas as gpd
import numpy as np
import os
import logging
from datetime import datetime
import json
import sys
# Add parent directory to Python path to access data_loader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from config import OUTPUT_DIR

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_walking_routes(input_file):
    """Load walking routes from GeoJSON file"""
    logger.info(f"Loading walking routes from {input_file}")
    try:
        routes_gdf = gpd.read_file(input_file)
        logger.info(f"Loaded {len(routes_gdf)} walking routes")
        print(routes_gdf.head())
        print(routes_gdf.columns)
        # Group by origin zone and destination
        grouped_stats = routes_gdf.groupby(['origin_zone', 'destination']).agg({
            'num_trips': 'sum',
            'zone_total_trips': 'first',
            'zone_ped_trips': 'first'
        }).reset_index()
        
        logger.info("\nZone-level statistics:")
        for _, row in grouped_stats.iterrows():
            logger.info(f"Zone {row['origin_zone']} to {row['destination']}: "
                       f"{row['num_trips']:.1f} trips "
                       f"({row['num_trips']/row['zone_ped_trips']*100:.1f}% of pedestrian trips)")
        
        return routes_gdf
        
    except Exception as e:
        logger.error(f"Failed to load walking routes: {str(e)}")
        raise

def process_temporal_patterns(routes_gdf, temporal_data, output_file):
    """
    Process temporal patterns at zone level for each destination
    """
    logger.info("Processing temporal patterns at zone level...")
    
    # First, aggregate trips by origin zone and destination
    zone_aggregation = routes_gdf.groupby(['origin_zone', 'destination']).agg({
        'num_trips': 'sum',
        'zone_total_trips': 'first',
        'zone_ped_trips': 'first'
    }).reset_index()
    
    # Create base datetime for today
    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    temporal_routes = []
    
    # Process each zone-destination pair
    for _, zone_group in zone_aggregation.iterrows():
        zone_id = zone_group['origin_zone']
        destination = zone_group['destination']
        total_zone_trips = zone_group['num_trips']
        
        logger.info(f"Processing zone {zone_id} trips to {destination} ({total_zone_trips:.1f} trips)")
        
        # Get all routes for this zone-destination pair
        zone_routes = routes_gdf[
            (routes_gdf['origin_zone'] == zone_id) & 
            (routes_gdf['destination'] == destination)
        ].copy()
        
        # Convert to numpy arrays for calculations
        route_trips_original = zone_routes['num_trips'].values
        route_weights = route_trips_original / route_trips_original.sum()
        
        # Process each hour
        for hour in range(24):
            # Get temporal factor for this hour
            temporal_factor = temporal_data.loc[
                (temporal_data['hour'] == hour) & 
                (temporal_data['destination'] == destination),
                'pedestrian_dist'
            ].iloc[0]
            
            if temporal_factor == 0:
                continue
            
            # Calculate trips for this hour
            hour_trips = max(1, int(round(total_zone_trips * temporal_factor)))
            
            # Distribute hour_trips across routes based on weights
            route_trips = np.round(route_weights * hour_trips).astype(int)
            
            # Adjust for rounding errors
            if route_trips.sum() != hour_trips:
                diff = hour_trips - route_trips.sum()
                # Get indices of routes with highest weights
                indices = np.argsort(route_weights)[-abs(diff):]
                route_trips[indices] += np.sign(diff)
            
            # Create copies of routes with updated times
            for route_idx, num_trips in enumerate(route_trips):
                if num_trips == 0:
                    continue
                
                route = zone_routes.iloc[route_idx].copy()
                
                # Distribute trips across minutes
                minutes = np.linspace(0, 59, num_trips, dtype=int)
                
                for minute in minutes:
                    route_copy = route.copy()
                    departure_time = base_date + pd.Timedelta(hours=hour, minutes=minute)
                    route_copy['departure_time'] = departure_time
                    route_copy['arrival_time'] = departure_time
                    route_copy['num_trips'] = 1  # Each route now represents one trip
                    temporal_routes.append(route_copy)
    
    # Create new GeoDataFrame with temporal routes
    temporal_gdf = gpd.GeoDataFrame(temporal_routes, crs=routes_gdf.crs)
    logger.info(f"Generated {len(temporal_gdf)} temporal routes")
    
    # Save processed data
    temporal_gdf.to_file(output_file, driver="GeoJSON")
    logger.info(f"Saved processed routes to {output_file}")
    
    # Log temporal distribution statistics
    hour_dist = temporal_gdf.groupby([temporal_gdf['departure_time'].dt.hour, 'destination']).size().unstack(fill_value=0)
    logger.info("\nTemporal distribution of processed routes by destination:")
    logger.info(hour_dist)
    
    return temporal_gdf

def main():
    # Input files from config
    input_file = os.path.join(OUTPUT_DIR, "walk_routes_inbound.geojson")
    bgu_temporal_file = os.path.join(OUTPUT_DIR, "ben_gurion_university_inbound_temporal.csv")
    soroka_temporal_file = os.path.join(OUTPUT_DIR, "soroka_medical_center_inbound_temporal.csv")
    output_file = os.path.join(OUTPUT_DIR, "temporal_arcs.json")
    
    # Load walking routes
    routes_gdf = load_walking_routes(input_file)
    
    # Load and combine temporal distributions
    bgu_temporal = pd.read_csv(bgu_temporal_file)
    bgu_temporal['destination'] = 'Ben-Gurion-University'
    soroka_temporal = pd.read_csv(soroka_temporal_file)
    soroka_temporal['destination'] = 'Soroka-Medical-Center'
    
    temporal_data = pd.concat([bgu_temporal, soroka_temporal])
    
    # Process temporal patterns
    arc_data = process_temporal_patterns(routes_gdf, temporal_data, output_file)
    
    logger.info("Processing complete")

if __name__ == "__main__":
    main() 