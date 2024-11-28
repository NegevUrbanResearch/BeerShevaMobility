import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
import json
import logging
from datetime import datetime, time
from pathlib import Path
import re

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BUILDINGS_FILE, MAPBOX_API_KEY, OUTPUT_DIR
from animation_components.animation_helpers import (
    get_debug_panel_html, 
    get_debug_js, 
    validate_animation_data, 
    format_html_safely
)
from animation_components.animation_styles import get_base_styles, get_animation_constants
from animation_components.template_manager import AnimationTemplate

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Keep existing POI configurations
POI_INFO = {
    'BGU': {'color': [0, 255, 90, 200], 'lat': 31.2614375, 'lon': 34.7995625},
    'Gav Yam': {'color': [0, 191, 255, 200], 'lat': 31.2641875, 'lon': 34.8128125},
    'Soroka Hospital': {'color': [170, 0, 255, 200], 'lat': 31.2579375, 'lon': 34.8003125}
}

attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]  # POI polygons
poi_polygons_json = poi_polygons.to_json()

POI_RADIUS = 0.0018  # about 200 meters in decimal degrees

# Define the mapping between shapefile IDs and POI names
POI_ID_MAP = {
    7: 'BGU',
    12: 'Gav Yam',
    11: 'Soroka Hospital'
}

def load_temporal_distributions():
    """Load temporal distribution data for each POI"""
    temporal_data = {}
    dashboard_dir = os.path.join(OUTPUT_DIR, "dashboard_data")
    
    poi_file_prefixes = {
        'BGU': 'ben_gurion_university',
        'Gav Yam': 'gav_yam_high_tech_park',
        'Soroka Hospital': 'soroka_medical_center'
    }
    
    for poi_name, file_prefix in poi_file_prefixes.items():
        # Load inbound and outbound distributions
        inbound_file = os.path.join(dashboard_dir, f"{file_prefix}_inbound_temporal.csv")
        outbound_file = os.path.join(dashboard_dir, f"{file_prefix}_outbound_temporal.csv")
        
        temporal_data[poi_name] = {
            'inbound': pd.read_csv(inbound_file),
            'outbound': pd.read_csv(outbound_file)
        }
        
    return temporal_data

def get_temporal_weight(hour, poi_name, direction, temporal_data):
    """Get the temporal weight for a specific hour and POI"""
    try:
        df = temporal_data[poi_name][direction]
        # Use car distribution as default
        return float(df[df['hour'] == hour]['car_dist'].iloc[0])
    except Exception as e:
        logger.warning(f"Error getting temporal weight for {poi_name} at hour {hour}: {e}")
        return 1.0 / 24  # Uniform distribution fallback



def load_trip_data(temporal_data):
    """Load and process trip data for animation with temporal distribution"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    logger.info(f"Loading trip data from: {file_path}")
    
    try:
        trips_gdf = gpd.read_file(file_path)
        raw_trip_count = trips_gdf['num_trips'].sum()
        logger.info(f"Loaded {len(trips_gdf)} routes representing {raw_trip_count:,} total trips")
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise
    
    # Calculate center coordinates
    total_bounds = trips_gdf.total_bounds
    center_lon = (total_bounds[0] + total_bounds[2]) / 2
    center_lat = (total_bounds[1] + total_bounds[3]) / 2
    
    trips_data = []
    processed_trips = 0
    
    # Animation parameters for 24-hour cycle
    frames_per_hour = 60
    total_hours = 24
    animation_duration = frames_per_hour * total_hours  # 1440 frames for 24 hours
    
    logger.info(f"Animation Configuration:")
    logger.info(f"  - Frames per hour: {frames_per_hour}")
    logger.info(f"  - Total hours: {total_hours}")
    logger.info(f"  - Total frames: {animation_duration}")
    
    for idx, row in trips_gdf.iterrows():
        try:
            coords = list(row.geometry.coords)
            trip_duration = len(coords)
            num_trips = int(row['num_trips'])
            
            if num_trips <= 0 or trip_duration < 2:
                logger.warning(f"Skipping route {idx} with {num_trips} trips and {trip_duration} points")
                continue
            
            # Determine POI and direction
            end_point = coords[-1]
            poi_name = None
            min_dist = float('inf')
            
            for name, info in POI_INFO.items():
                end_dist = np.hypot(end_point[0] - info['lon'], end_point[1] - info['lat'])
                if end_dist < min_dist:
                    min_dist = end_dist
                    poi_name = name
            
            if not poi_name:
                logger.warning(f"Could not determine POI for route {idx}")
                continue
                
            processed_trips += num_trips
            
            # Distribute trips across hours
            hourly_trips = []
            for hour in range(24):
                weight = get_temporal_weight(hour, poi_name, 'inbound', temporal_data)
                num_hour_trips = max(1, int(num_trips * weight))
                
                # Calculate base frame for this hour
                base_frame = hour * frames_per_hour
                
                # Spread trips within the hour
                for trip_num in range(num_hour_trips):
                    # Distribute evenly within the hour
                    frame_offset = (trip_num * frames_per_hour) // max(num_hour_trips, 1)
                    start_frame = (base_frame + frame_offset) % animation_duration
                    
                    # Create timestamps for each point in the path
                    timestamps = [(start_frame + i) % animation_duration for i in range(trip_duration)]
                    hourly_trips.append(timestamps)
            
            if hourly_trips:
                trips_data.append({
                    'path': [[float(x), float(y)] for x, y in coords],
                    'timestamps': list(zip(*hourly_trips)),
                    'num_trips': num_trips
                })
            
        except Exception as e:
            logger.error(f"Error processing trip {idx}: {str(e)}")
            continue
    
    # Add detailed logging
    total_instances = sum(len(trip['timestamps'][0]) for trip in trips_data)
    logger.info(f"Animation Statistics:")
    logger.info(f"  - Animation duration: {animation_duration} frames")
    logger.info(f"  - Total trip instances being animated: {total_instances:,}")
    logger.info(f"  - Total processed trips: {processed_trips:,}")
    
    return trips_data, center_lat, center_lon, processed_trips

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

        


def create_animation():
    """Create the temporal animation"""
    try:
        temporal_data = load_temporal_distributions()
        trips_data, center_lat, center_lon, total_trips = load_trip_data(temporal_data)
        buildings_data, text_features, poi_borders, poi_fills = load_building_data()
        
        validate_animation_data(trips_data, buildings_data, poi_borders, poi_fills)
        
        template = AnimationTemplate()
        html_template = template.get_html_template()
        
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
            'animation_duration': 1440,
            'loopLength': 1440
        }
        
        formatted_html = format_html_safely(html_template, format_values)
        
        output_path = os.path.join(OUTPUT_DIR, "trip_animation_hours.html")
        with open(output_path, 'w') as f:
            f.write(formatted_html)
            
        logger.info(f"Animation saved to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error creating animation: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        output_file = create_animation()
        print(f"Animation saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to create animation: {str(e)}")
        sys.exit(1) 