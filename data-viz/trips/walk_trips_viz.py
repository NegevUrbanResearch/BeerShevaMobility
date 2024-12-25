import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
# Add parent directory to Python path to access data_loader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import logging
from config import BUILDINGS_FILE
from shapely.geometry import Point
from pyproj import Transformer
import re
import walk_html

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR

# Load attraction centers shapefile for POI polygons
attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
poi_polygons = attractions[attractions['ID'].isin([11, 7])]  # Only BGU and Soroka
poi_polygons_json = poi_polygons.to_json()
POI_RADIUS = 0.0018

# Update POI information with mapping
POI_INFO = {
    'BGU': {
        'color': [0, 255, 90, 200],
        'lat': 31.2614375,
        'lon': 34.7995625
    },
    'Soroka Hospital': {
        'color': [170, 0, 255, 200],
        'lat': 31.2579375,
        'lon': 34.8003125
    }
}

POI_ID_MAP = {
    7: 'BGU',
    11: 'Soroka Hospital'
}

def normalize_distribution(dist):
    """Normalize a probability distribution to sum to 1"""
    total = sum(dist.values())
    if total == 0:
        logger.error("Distribution sums to 0")
        return dist
    return {k: v/total for k, v in dist.items()}

def load_trip_data():
    """Load and process walking trip data for animation with time-based distribution"""
    file_path = os.path.join(OUTPUT_DIR, "walking_routes_inbound.geojson")
    logger.info(f"Loading walking trip data from: {file_path}")
    
    # Define name mappings
    DEST_MAPPING = {
        'BGU': 'Ben-Gurion-University',
        'Soroka Hospital': 'Soroka-Medical-Center',
        'Ben-Gurion-University': 'Ben-Gurion-University',
        'Soroka-Medical-Center': 'Soroka-Medical-Center'
    }
    
    try:
        trips_gdf = gpd.read_file(file_path)
        raw_trip_count = trips_gdf['num_trips'].sum()
        logger.info(f"Loaded {len(trips_gdf)} walking routes representing {raw_trip_count:,} total trips")
        
        # Calculate center coordinates
        total_bounds = trips_gdf.total_bounds
        center_lon = (total_bounds[0] + total_bounds[2]) / 2
        center_lat = (total_bounds[1] + total_bounds[3]) / 2
        
        # Time distribution by hour (6-22) for BGU and Soroka
        bgu_dist = {
            6: 0.000641, 7: 0.020829, 8: 0.148528, 9: 0.132706, 10: 0.181134,
            11: 0.091648, 12: 0.110234, 13: 0.067655, 14: 0.071941, 15: 0.036371,
            16: 0.044302, 17: 0.032646, 18: 0.029481, 19: 0.018466, 20: 0.007851,
            21: 0.004046, 22: 0.001522
        }
        
        soroka_dist = {
            6: 0.024975, 7: 0.080456, 8: 0.270533, 9: 0.110459, 10: 0.089172,
            11: 0.051793, 12: 0.052799, 13: 0.058666, 14: 0.103084, 15: 0.030003,
            16: 0.042910, 17: 0.027154, 18: 0.017264, 19: 0.022796, 20: 0.005699,
            21: 0.004023, 22: 0.008213
        }
        
        # Normalize distributions
        bgu_dist = normalize_distribution(bgu_dist)
        soroka_dist = normalize_distribution(soroka_dist)
        
        # Log normalized distributions
        logger.info("Normalized BGU distribution sum: %.6f", sum(bgu_dist.values()))
        logger.info("Normalized Soroka distribution sum: %.6f", sum(soroka_dist.values()))
        
        # Animation parameters
        total_animation_time = 240000  # 240 seconds (4 minutes) to match HTML template
        hours_in_day = 16  # 6am to 22pm = 16 hours
        ms_per_hour = total_animation_time / hours_in_day
        
        trips_data = []
        destination_counts = {'Ben-Gurion-University': 0, 'Soroka-Medical-Center': 0}
        
        # Pre-calculate hourly trip totals
        hourly_totals = {hour: {'Ben-Gurion-University': 0, 'Soroka-Medical-Center': 0} 
                         for hour in range(6, 23)}
        
        for idx, row in trips_gdf.iterrows():
            try:
                coords = list(row.geometry.coords)
                trip_duration = len(coords)
                num_trips = int(row['num_trips'])
                
                raw_destination = row['destination']
                if raw_destination not in DEST_MAPPING:
                    logger.warning(f"Unknown destination format: {raw_destination}")
                    continue
                    
                destination = DEST_MAPPING[raw_destination]
                dist = bgu_dist if destination == 'Ben-Gurion-University' else soroka_dist
                
                if trip_duration < 2:
                    logger.warning(f"Skipping trip with duration < 2: {trip_duration}")
                    continue
                
                # Generate one path per actual trip
                for _ in range(num_trips):
                    try:
                        hour = np.random.choice(list(dist.keys()), p=list(dist.values()))
                        # Add to hourly totals
                        hourly_totals[hour][destination] += 1
                        
                        # Calculate timestamps
                        hour_offset = hour - 6  # Hours since 6am
                        start_time = hour_offset * ms_per_hour
                        path_duration = min(ms_per_hour * 0.8, 15000)  # Cap duration at 15 seconds
                        
                        timestamps = []
                        for i in range(trip_duration):
                            progress = i / (trip_duration - 1)
                            time = start_time + (progress * path_duration)
                            timestamps.append([time])
                        
                        trips_data.append({
                            'path': [[float(x), float(y)] for x, y in coords],
                            'timestamps': timestamps,
                            'destination': destination,
                            'startTime': start_time,
                            'duration': path_duration
                        })
                        destination_counts[destination] += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing individual trip {idx}: {str(e)}")
                        continue
                
            except Exception as e:
                logger.error(f"Error processing trip group {idx}: {str(e)}")
                continue
        
        # Log final counts
        for dest, count in destination_counts.items():
            logger.info(f"{dest}: {count:,} trips")
        
        total_processed = sum(destination_counts.values())
        logger.info(f"Total processed trips: {total_processed:,} (Original: {raw_trip_count:,})")
        
        return trips_data, center_lat, center_lon, total_processed, hourly_totals
        
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise
    
def load_building_data():
    """Load building data for 3D visualization"""
    try:
        buildings_gdf = gpd.read_file(BUILDINGS_FILE)
        
        # Convert to format needed for deck.gl
        buildings_data = []
        entrance_features = []  # For entrance icons
        
        # Debug logging for POI polygons
        logger.info(f"POI polygons IDs: {[p['ID'] for idx, p in poi_polygons.iterrows()]}")
        
        # Process buildings
        for idx, building in buildings_gdf.iterrows():
            building_color = [80, 90, 100, 160]  # Default color
            try:
                height = float(building.get('height', 20))
                building_height = height * 1.5
                
                # Check if building intersects with any POI polygon
                for poi_idx, poi_polygon in poi_polygons.iterrows():
                    if building.geometry.intersects(poi_polygon.geometry):
                        numeric_id = int(poi_polygon['ID'])
                        poi_name = POI_ID_MAP.get(numeric_id)
                        
                        if poi_name:
                            logger.debug(f"Building intersects with POI {numeric_id} ({poi_name})")
                            building_height = min(40, height * 1000)
                            building_color = POI_INFO[poi_name]['color']
                
                buildings_data.append({
                    "polygon": list(building.geometry.exterior.coords),
                    "height": building_height,
                    "color": building_color
                })
            except Exception as e:
                logger.error(f"Skipping building due to error: {e}")
                continue
        
        # Load entrances and create icon features
        entrances_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                    "data/filtered-entrances/filtered_entrances.shp")
        entrances_gdf = gpd.read_file(entrances_path)
        
        for idx, entrance in entrances_gdf.iterrows():
            icon_type = 'hospital' if entrance['Name'].startswith('Hospital') else 'university'
            entrance_features.append({
                "position": [entrance.geometry.x, entrance.geometry.y],
                "icon": icon_type,
                "name": entrance['Name']
            })
        
        # Prepare POI polygon borders and fills
        poi_borders = []
        poi_fills = []
        
        for poi_idx, poi_polygon in poi_polygons.iterrows():
            numeric_id = int(poi_polygon['ID'])
            poi_name = POI_ID_MAP.get(numeric_id)
            
            if poi_name:
                logger.info(f"Processing POI polygon: ID={numeric_id}, Name={poi_name}")
                color = POI_INFO[poi_name]['color'][:3]
                
                poi_borders.append({
                    "polygon": list(poi_polygon.geometry.exterior.coords),
                    "color": color + [255]
                })
                
                poi_fills.append({
                    "polygon": list(poi_polygon.geometry.exterior.coords),
                    "color": color + [100]
                })
            else:
                logger.warning(f"Unknown POI ID: {numeric_id}")
        
        logger.info(f"Loaded {len(buildings_data)} buildings")
        logger.info(f"Created {len(poi_fills)} POI fill areas")
        logger.info(f"Added {len(entrance_features)} entrance icons")
        return buildings_data, entrance_features, poi_borders, poi_fills
        
    except Exception as e:
        logger.error(f"Error loading building data: {str(e)}")
        raise


def create_animation():
    trips_data, center_lat, center_lon, total_trips, hourly_totals = load_trip_data()
    buildings_data, entrance_features, poi_borders, poi_fills = load_building_data()
    
    # Update the HTML template to include icon handling
    html_template = walk_html.HTML_TEMPLATE 

    # First, transform the trips data to match the expected POI names
    for trip in trips_data:
        # Map the destination names to match POI_INFO keys
        if trip['destination'] == 'BGU':
            trip['destination'] = 'Ben-Gurion-University'
        elif trip['destination'] == 'Soroka Hospital':
            trip['destination'] = 'Soroka-Medical-Center'
    
    # Find all placeholders in the template
    placeholders = set(re.findall(r'%\(([^)]+)\)[sdfg]', html_template))
    logger.info(f"All template placeholders: {sorted(placeholders)}")
    
    # Create format_values with all required placeholders
    format_values = {
        'total_trips': total_trips,
        'trips_data': json.dumps(trips_data),
        'buildings_data': json.dumps(buildings_data),
        'entrance_features': json.dumps(entrance_features),
        'poi_borders': json.dumps(poi_borders),
        'poi_fills': json.dumps(poi_fills),
        'poi_radius': POI_RADIUS,
        'animation_duration': 240000,  # 4 minutes
        'loopLength': 240000,
        'hourly_totals': json.dumps(hourly_totals),
        # Fix these values using single pass substitution
        'center_lon': center_lon,
        'center_lat': center_lat,
        'mapbox_api_key': MAPBOX_API_KEY if 'MAPBOX_API_KEY' in globals() else ''
    }
    
    # Check for missing placeholders
    missing = placeholders - set(format_values.keys())
    if missing:
        logger.error(f"Missing placeholders: {missing}")
        # Add missing placeholders with default values
        for placeholder in missing:
            format_values[placeholder] = ''
            logger.info(f"Added empty placeholder for: {placeholder}")
    
    try:
        # Debug logging
        logger.info("Format values being used:")
        for key, value in format_values.items():
            if isinstance(value, str) and len(value) > 100:
                logger.info(f"  - {key}: [long string]")
            else:
                logger.info(f"  - {key}: {value}")
        
        formatted_html = html_template % format_values
        output_path = os.path.join(OUTPUT_DIR, "walking_trip_animation.html")
        with open(output_path, 'w') as f:
            f.write(formatted_html)
            
        logger.info(f"Animation saved to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error writing HTML file: {str(e)}")
        # Show snippet of template around each placeholder
        for match in re.finditer(r'%\(([^)]+)\)[sdfg]', html_template):
            start = max(0, match.start() - 50)
            end = min(len(html_template), match.end() + 50)
            context = html_template[start:end].replace('\n', ' ')
            logger.error(f"Context for {match.group(1)}: ...{context}...")
        raise

if __name__ == "__main__":
    try:
        output_file = create_animation()
        print(f"Animation saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to create animation: {str(e)}")
        sys.exit(1)