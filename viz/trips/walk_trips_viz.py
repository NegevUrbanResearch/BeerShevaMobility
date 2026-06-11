import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import json
import logging
import os
import re
import sys
from pathlib import Path

import walk_html
from pyproj import Transformer
from shapely.geometry import Point

from mobility.config import (
    ATTRACTION_CENTERS_SHP,
    BUILDINGS_FILE,
    FILTERED_ENTRANCES_SHP,
    MAPBOX_API_KEY,
    OUTPUT_DIR,
)
from mobility.utils.walk_work_trips import (
    DEFAULT_BGU_DIST,
    DEFAULT_SOROKA_DIST,
    build_work_share_lookup,
    compute_work_hourly_distributions,
    get_work_share,
    normalize_distribution,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

attractions = gpd.read_file(ATTRACTION_CENTERS_SHP)
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

def load_trip_data(work_trips_only=False):
    """Load and process walking trip data for animation with time-based distribution"""
    file_path = OUTPUT_DIR / "walk_routes_inbound.geojson"
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
        work_share_lookup = build_work_share_lookup() if work_trips_only else None
        raw_trip_count = trips_gdf['num_trips'].sum()
        logger.info(f"Loaded {len(trips_gdf)} walking routes representing {raw_trip_count:,} total trips")
        
        # Calculate center coordinates
        total_bounds = trips_gdf.total_bounds
        center_lon = (total_bounds[0] + total_bounds[2]) / 2
        center_lat = (total_bounds[1] + total_bounds[3]) / 2
        
        if work_trips_only:
            work_dists = compute_work_hourly_distributions()
            bgu_dist = normalize_distribution(work_dists['Ben-Gurion-University'])
            soroka_dist = normalize_distribution(work_dists['Soroka-Medical-Center'])
        else:
            bgu_dist = normalize_distribution(DEFAULT_BGU_DIST)
            soroka_dist = normalize_distribution(DEFAULT_SOROKA_DIST)
        
        # Log normalized distributions
        logger.info("Normalized BGU distribution sum: %.6f", sum(bgu_dist.values()))
        logger.info("Normalized Soroka distribution sum: %.6f", sum(soroka_dist.values()))
        
        # Animation parameters
        total_animation_time = 240000  # 240 seconds (4 minutes) to match HTML template
        hours_in_day = 12  # 7am to 7pm = 12 hours
        ms_per_hour = total_animation_time / hours_in_day
        
        trips_data = []
        destination_counts = {'Ben-Gurion-University': 0, 'Soroka-Medical-Center': 0}
        
        # Pre-calculate hourly trip totals
        hourly_totals = {hour: {'Ben-Gurion-University': 0, 'Soroka-Medical-Center': 0} 
                         for hour in range(7, 20)}
        
        for idx, row in trips_gdf.iterrows():
            try:
                coords = list(row.geometry.coords)
                trip_duration = len(coords)
                num_trips = float(row['num_trips'])
                if work_trips_only:
                    num_trips *= get_work_share(row, work_share_lookup)
                num_trips = int(round(num_trips))
                if num_trips <= 0:
                    continue
                
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
                        hour_offset = hour - 7  # Hours since 7am
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
            try:
                # Check if building intersects with any POI polygon
                intersects_poi = False
                building_color = None
                building_height = None
                
                for poi_idx, poi_polygon in poi_polygons.iterrows():
                    if building.geometry.intersects(poi_polygon.geometry):
                        intersects_poi = True
                        numeric_id = int(poi_polygon['ID'])
                        poi_name = POI_ID_MAP.get(numeric_id)
                        
                        if poi_name:
                            logger.debug(f"Building intersects with POI {numeric_id} ({poi_name})")
                            height = float(building.get('height', 20))
                            building_height = min(40, height * 1000)
                            building_color = POI_INFO[poi_name]['color']
                            break
                
                # Only add building if it intersects with a POI
                if intersects_poi and building_color and building_height:
                    buildings_data.append({
                        "polygon": list(building.geometry.exterior.coords),
                        "height": building_height,
                        "color": building_color
                    })
            except Exception as e:
                logger.error(f"Skipping building due to error: {e}")
                continue
        
        # Load entrances and create icon features
        entrances_gdf = gpd.read_file(FILTERED_ENTRANCES_SHP)
        
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

def create_animation(output_path=None, work_trips_only=False):
    trips_data, center_lat, center_lon, total_trips, hourly_totals = load_trip_data(
        work_trips_only=work_trips_only
    )
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
        if output_path is None:
            output_path = OUTPUT_DIR / "walking_trip_animation.html"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
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