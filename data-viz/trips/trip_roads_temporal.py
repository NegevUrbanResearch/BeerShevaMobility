import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import logging
from config import BUILDINGS_FILE
from shapely.geometry import Point
from pyproj import Transformer
import re
import trip_html_template
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR

attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]  # POI polygons
poi_polygons_json = poi_polygons.to_json()
POI_RADIUS = 0.0018  # about 200 meters in decimal degrees

# Update POI_INFO with even more contrasting colors and darker base buildings
POI_INFO = {
    'BGU': {'color': [0, 255, 90, 200], 'lat': 31.2614375, 'lon': 34.7995625},         # Brighter neon green
    'Gav Yam': {'color': [0, 191, 255, 200], 'lat': 31.2641875, 'lon': 34.8128125},    # Deep sky blue
    'Soroka Hospital': {'color': [170, 0, 255, 200], 'lat': 31.2579375, 'lon': 34.8003125}  # Deep purple
}

# Define the mapping between shapefile IDs and POI names
POI_ID_MAP = {
    7: 'BGU',
    12: 'Gav Yam',
    11: 'Soroka Hospital'
}
def load_temporal_distributions():
    """Load temporal distribution data for each POI"""
    logger.info("Loading temporal distributions")
    
    distributions = {}
    file_patterns = {
        'BGU': 'ben_gurion_university_inbound_temporal.csv',
        'Gav Yam': 'gav_yam_high_tech_park_inbound_temporal.csv',
        'Soroka Hospital': 'soroka-medical-center_inbound_temporal.csv'
    }
    
    for poi_name, filename in file_patterns.items():
        file_path = os.path.join(OUTPUT_DIR, filename)
        try:
            df = pd.read_csv(file_path)
            # Extract car distribution for business hours (7-19)
            dist = df[(df['hour'] >= 7) & (df['hour'] <= 19)]['car_dist'].values
            # Normalize to ensure sum is 1.0
            dist = dist / dist.sum()
            distributions[poi_name] = dist
            logger.info(f"Loaded distribution for {poi_name}: sum={dist.sum():.3f}")
        except Exception as e:
            logger.error(f"Error loading distribution for {poi_name}: {str(e)}")
            raise
            
    return distributions
        


def load_trip_data():
    """Load and process trip data with optimized timing distribution"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    logger.info(f"Loading trip data from: {file_path}")
    
    try:
        trips_gdf = gpd.read_file(file_path)
        raw_trip_count = trips_gdf['num_trips'].sum()
        logger.info(f"Loaded {len(trips_gdf)} routes representing {raw_trip_count:,} total trips")
        
        # Load temporal distributions
        temporal_dist = load_temporal_distributions()
        
        # Calculate center coordinates
        total_bounds = trips_gdf.total_bounds
        center_lon = (total_bounds[0] + total_bounds[2]) / 2
        center_lat = (total_bounds[1] + total_bounds[3]) / 2
        
        # Animation parameters
        frames_per_second = 30
        minutes_per_simulated_hour = 60
        hours_per_day = 12  # Changed from 16 to 12 (7:00-19:00)
        frames_per_hour = frames_per_second * minutes_per_simulated_hour
        animation_duration = frames_per_hour * hours_per_day
        
        logger.info(f"Animation Configuration:")
        logger.info(f"  - Hours simulated: {hours_per_day} (7:00-19:00)")  # Updated log message
        logger.info(f"  - Frames per hour: {frames_per_hour}")
        logger.info(f"  - Total frames: {animation_duration}")
        
        routes_data = []
        processed_trips = 0
        
        for idx, row in trips_gdf.iterrows():
            try:
                coords = list(row.geometry.coords)
                num_trips = int(row['num_trips'])
                
                if num_trips <= 0 or len(coords) < 2:
                    continue
                
                # Determine POI for this route
                dest_point = Point(coords[-1])
                poi_name = None
                for poi_poly_idx, poi_polygon in poi_polygons.iterrows():
                    if dest_point.distance(poi_polygon.geometry) < POI_RADIUS:
                        poi_name = POI_ID_MAP[int(poi_polygon['ID'])]
                        break
                
                if not poi_name:
                    continue
                
                processed_trips += num_trips
                path = [[float(x), float(y)] for x, y in coords]
                
                # Instead of creating individual trips, create route patterns
                for hour_idx, hour_fraction in enumerate(temporal_dist[poi_name]):
                    hour_trips = round(num_trips * hour_fraction)
                    if hour_trips <= 0:
                        continue
                    
                    # Create a few staggered patterns per hour instead of individual trips
                    num_patterns = min(5, max(1, hour_trips // 100))  # Scale patterns based on volume
                    trips_per_pattern = hour_trips / num_patterns
                    
                    for pattern in range(num_patterns):
                        # Add some randomness to start time within the hour
                        start_offset = (pattern / num_patterns) * frames_per_hour + np.random.randint(-30, 30)
                        start_time = hour_idx * frames_per_hour + start_offset
                        
                        routes_data.append({
                            'path': path,
                            'startTime': int(start_time),
                            'numTrips': trips_per_pattern,
                            'duration': len(coords) * 2,  # Base duration on path length
                            'poi': poi_name
                        })
                
            except Exception as e:
                logger.error(f"Error processing route {idx}: {str(e)}")
                continue
        
        logger.info(f"Created {len(routes_data)} route patterns")
        logger.info(f"Original trips processed: {processed_trips:,}")
        
        return routes_data, center_lat, center_lon, raw_trip_count, animation_duration
        
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise
        
    


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
            try:
                # Check if building intersects with any POI polygon
                for poi_idx, poi_polygon in poi_polygons.iterrows():
                    if building.geometry.intersects(poi_polygon.geometry):
                        numeric_id = int(poi_polygon['ID'])
                        poi_name = POI_ID_MAP.get(numeric_id)
                        
                        if poi_name:
                            # Get actual height from building data, default to 20 if not found
                            height = float(building.get('height', 20))
                            building_height = min(40, height * 1000)
                            building_color = POI_INFO[poi_name]['color']
                            
                            buildings_data.append({
                                "polygon": list(building.geometry.exterior.coords),
                                "height": building_height,
                                "color": building_color
                            })
                            
                            # Add text label for POI
                            text_features.append({
                                "position": list(building.geometry.centroid.coords)[0] + (building_height + 10,),
                                "text": poi_name,
                                "color": [255, 255, 255, 255]
                            })
                            break
                            
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






# Update the create_animation function to match parameter names
def create_animation(html_template, map_style, output_suffix):
    trips_data, center_lat, center_lon, total_trips, animation_duration = load_trip_data()
    buildings_data, text_features, poi_borders, poi_fills = load_building_data()
    
    hours_simulated = 12
    frames_per_hour = animation_duration // hours_simulated
    
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
        'animation_duration': animation_duration,
        'loopLength': animation_duration,
        'mapbox_api_key': MAPBOX_API_KEY,
        'start_hour': 7,  # Changed from 6 to 7
        'end_hour': 19,   # Changed from 22 to 19
        'frames_per_hour': frames_per_hour,
        'map_style': map_style
    }
    
    try:
        formatted_html = html_template % format_values
        output_path = os.path.join(OUTPUT_DIR, f"trip_animation_time_{output_suffix}.html")
        with open(output_path, 'w') as f:
            f.write(formatted_html)
        logger.info(f"Animation saved to: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error writing HTML file: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        # Updated map styles with CORS support and place names
        MAP_STYLES = {
            'dark_matter': 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
            'dark_nolabels': 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
            'positron': 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
            'voyager': 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
        }
        
        # Generate an animation for each map style
        for suffix, style_info in MAP_STYLES.items():
            # Handle both simple string styles and dictionary style configs
            if isinstance(style_info, dict):
                map_style = style_info['style']
            else:
                map_style = style_info
                
            # Modify the HTML template to use the current map style
            modified_template = trip_html_template.HTML_TEMPLATE.replace(
                "MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json'",
                f"MAP_STYLE = '{map_style}'"
            )
            
            output_file = create_animation(modified_template, map_style, suffix)
            print(f"Animation with {suffix} style saved to: {output_file}")
            
    except Exception as e:
        logger.error(f"Failed to create animations: {str(e)}")
        sys.exit(1) 