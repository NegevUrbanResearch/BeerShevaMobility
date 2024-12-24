import pandas as pd
import geopandas as gpd
import requests
import json
from shapely.geometry import Point, LineString
import numpy as np
from datetime import datetime
import time
from tqdm import tqdm
import os
import polyline
from rtree import index
from scipy.spatial import cKDTree
import logging
import sys

# Add parent directory to Python path to access data_loader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from config import OUTPUT_DIR

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OTPClient:
    def __init__(self, base_url="http://localhost:8080/otp/routers/default", max_retries=3, retry_delay=0.1):
        self.base_url = base_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
    def get_walking_route(self, from_lat, from_lon, to_lat, to_lon):
        """Query OTP for a walking route with retries"""
        params = {
            'fromPlace': f"{from_lat},{from_lon}",
            'toPlace': f"{to_lat},{to_lon}",
            'mode': 'WALK',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': '09:00:00',
            'arriveBy': 'false',
            'walkSpeed': 1.4
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    f"{self.base_url}/plan", 
                    params=params, 
                    timeout=10  # Add timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'error' in data or 'plan' not in data:
                        logger.warning(f"OTP returned invalid response: {data.get('error', 'No plan found')}")
                        return None
                    return data
                elif response.status_code == 429:  # Too Many Requests
                    wait_time = (attempt + 1) * self.retry_delay
                    logger.warning(f"Rate limited. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"OTP request failed with status {response.status_code}")
                    
            except requests.exceptions.Timeout:
                logger.warning("OTP request timed out")
            except requests.exceptions.RequestException as e:
                logger.error(f"OTP request failed: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                
            if attempt < self.max_retries - 1:
                wait_time = (attempt + 1) * self.retry_delay
                logger.warning(f"Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{self.max_retries})")
                time.sleep(wait_time)
                
        return None

class EntranceManager:
    def __init__(self, entrances_gdf):
        self.entrances = entrances_gdf
        if self.entrances.crs != "EPSG:4326":
            self.entrances = self.entrances.to_crs("EPSG:4326")
    
    def get_entrances_for_poi(self, poi_name):
        """Get all entrance points for a given POI"""
        prefix = 'Hospital' if 'Soroka' in poi_name else 'Uni'
        return self.entrances[self.entrances['Name'].str.startswith(prefix)]

class ImprovedTripGenerator:
    def __init__(self, zones_gdf, otp_client, entrance_manager, amenities_gdf):
        self.zones = zones_gdf.to_crs("EPSG:4326")
        self.otp_client = otp_client
        self.entrance_manager = entrance_manager
        self.amenities = self._filter_clustered_amenities(amenities_gdf.to_crs("EPSG:4326"))
        self.zone_used_points = {}  # Track used points per zone
        
    def _filter_clustered_amenities(self, amenities_gdf, distance_threshold=25):
        """Filter amenities to keep only those that are part of clusters"""
        logger.info(f"Filtering {len(amenities_gdf)} amenities for clusters...")
        
        coords = np.column_stack((
            amenities_gdf.geometry.x.values,
            amenities_gdf.geometry.y.values
        ))
        tree = cKDTree(coords)
        pairs = tree.query_pairs(r=distance_threshold/111000)
        
        clustered_indices = set()
        for i, j in pairs:
            clustered_indices.add(i)
            clustered_indices.add(j)
        
        filtered_amenities = amenities_gdf.iloc[list(clustered_indices)].copy()
        logger.info(f"Found {len(filtered_amenities)} amenities in clusters")
        return filtered_amenities
    
    def _get_used_points(self, zone_id):
        """Get set of used points for a specific zone"""
        return self.zone_used_points.setdefault(zone_id, set())
    
    def _generate_unique_point(self, zone_id, geometry, max_attempts=100):
        """Generate a unique random point within a geometry"""
        used_points = self._get_used_points(zone_id)
        minx, miny, maxx, maxy = geometry.bounds
        
        for _ in range(max_attempts):
            point = Point(
                np.random.uniform(minx, maxx),
                np.random.uniform(miny, maxy)
            )
            if geometry.contains(point):
                # Check if point is sufficiently far from used points (10 meters ≈ 0.0001 degrees)
                if not any(point.distance(p) < 0.0001 for p in used_points):
                    return point
        return None
        
    def _find_closest_entrance(self, point, entrances):
        """Find the closest entrance to a given point"""
        distances = [point.distance(entrance.geometry) for _, entrance in entrances.iterrows()]
        closest_idx = np.argmin(distances)
        return entrances.iloc[closest_idx]
    
    def _find_suitable_amenity(self, origin_point, destination_point, max_detour_factor=1.5):
        """Find a suitable amenity that doesn't create too much of a detour"""
        if self.amenities.empty:
            return None
            
        direct_distance = origin_point.distance(destination_point)
        
        origin_arr = np.array([origin_point.x, origin_point.y])
        dest_arr = np.array([destination_point.x, destination_point.y])
        
        amenity_coords = np.column_stack((
            self.amenities.geometry.x.values,
            self.amenities.geometry.y.values
        ))
        
        total_distances = (
            np.sqrt(np.sum((amenity_coords - origin_arr)**2, axis=1)) +
            np.sqrt(np.sum((amenity_coords - dest_arr)**2, axis=1))
        )
        
        valid_amenities = total_distances <= (direct_distance * max_detour_factor)
        
        if np.any(valid_amenities):
            valid_indices = np.where(valid_amenities)[0]
            chosen_idx = np.random.choice(valid_indices)
            chosen_amenity = self.amenities.iloc[chosen_idx]
            return {
                'geometry': Point(amenity_coords[chosen_idx]),
                'amenity_id': chosen_amenity.name,
                'amenity_type': chosen_amenity['top_classi']
            }
        
        return None
    
    def _get_valid_route(self, origin_point, destination_point, amenity_stop=None):
        """Get a valid walking route, optionally including an amenity stop"""
        if amenity_stop:
            # Get route segments: origin -> amenity -> destination
            route1 = self.otp_client.get_walking_route(
                origin_point.y, origin_point.x,
                amenity_stop['geometry'].y, amenity_stop['geometry'].x
            )
            if not route1 or 'plan' not in route1 or not route1['plan'].get('itineraries'):
                return None
            
            route2 = self.otp_client.get_walking_route(
                amenity_stop['geometry'].y, amenity_stop['geometry'].x,
                destination_point.y, destination_point.x
            )
            if not route2 or 'plan' not in route2 or not route2['plan'].get('itineraries'):
                return None
            
            try:
                leg1 = route1['plan']['itineraries'][0]['legs'][0]
                leg2 = route2['plan']['itineraries'][0]['legs'][0]
                
                points1 = polyline.decode(leg1['legGeometry']['points'])
                points2 = polyline.decode(leg2['legGeometry']['points'])
                
                return {
                    'points': points1 + points2[1:],  # Combine routes, skip first point of second leg to avoid duplication
                    'duration': leg1['duration'] + leg2['duration'],
                    'amenity_info': amenity_stop
                }
            except (KeyError, IndexError) as e:
                logger.warning(f"Error processing route segments: {str(e)}")
                return None
        else:
            route = self.otp_client.get_walking_route(
                origin_point.y, origin_point.x,
                destination_point.y, destination_point.x
            )
            if not route or 'plan' not in route or not route['plan'].get('itineraries'):
                return None
            
            try:
                leg = route['plan']['itineraries'][0]['legs'][0]
                return {
                    'points': polyline.decode(leg['legGeometry']['points']),
                    'duration': leg['duration'],
                    'amenity_info': None
                }
            except (KeyError, IndexError) as e:
                logger.warning(f"Error processing direct route: {str(e)}")
                return None
    
    def process_zone_trips(self, zone_id, num_trips, poi_name, entrances, zone_data, direction='inbound', fixed_origin=None):
        """Process all trips for a single zone"""
        zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
        if len(zone) == 0:
            return []
        
        zone_geometry = zone.geometry.iloc[0]
        successful_routes = []
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        # Determine how many trips should include amenity stops
        num_amenity_trips = int(num_trips * 0.5)
        
        max_consecutive_failures = 5  # Add failure threshold
        consecutive_failures = 0
        
        with tqdm(total=num_trips, desc=f"Zone {zone_id} {direction}") as pbar:
            trips_remaining = num_trips
            while trips_remaining > 0:
                if direction == 'inbound':
                    origin_point = self._generate_unique_point(zone_id, zone_geometry)
                    if not origin_point:
                        logger.warning(f"Could not generate unique point for zone {zone_id}")
                        break
                    best_entrance = self._find_closest_entrance(origin_point, entrances)
                    destination_point = best_entrance.geometry
                else:  # outbound
                    destination_point = self._generate_unique_point(zone_id, zone_geometry)
                    if not destination_point:
                        logger.warning(f"Could not generate unique point for zone {zone_id}")
                        break
                    origin_point = fixed_origin.geometry
                
                include_amenity = (len(successful_routes) < num_amenity_trips)
                
                route_data = None
                if include_amenity:
                    amenity_stop = self._find_suitable_amenity(
                        origin_point,
                        destination_point,
                        max_detour_factor=1.5
                    )
                    if amenity_stop:
                        route_data = self._get_valid_route(
                            origin_point,
                            destination_point,
                            amenity_stop
                        )
                
                if not route_data:
                    route_data = self._get_valid_route(
                        origin_point,
                        destination_point
                    )
                
                if route_data:
                    consecutive_failures = 0  # Reset failure counter on success
                    route_info = {
                        'geometry': LineString([(lon, lat) for lat, lon in route_data['points']]),
                        'departure_time': departure_time,
                        'arrival_time': departure_time + pd.Timedelta(seconds=route_data['duration']),
                        'origin_zone': zone_id if direction == 'inbound' else poi_name,
                        'destination': poi_name if direction == 'inbound' else zone_id,
                        'entrance': fixed_origin['Name'] if direction == 'outbound' else best_entrance['Name'],
                        'route_id': f"{zone_id}-{poi_name}-{direction}-{len(successful_routes)}",
                        'num_trips': 1,
                        'origin_x': origin_point.x,
                        'origin_y': origin_point.y,
                        'direction': direction,
                        'has_amenity_stop': bool(route_data.get('amenity_info')),
                        'zone_total_trips': zone_data['total_trips'],
                        'zone_ped_trips': zone_data['ped_trips']
                    }
                    
                    # Add amenity information if present
                    if route_data.get('amenity_info'):
                        route_info.update({
                            'amenity_id': route_data['amenity_info']['amenity_id'],
                            'amenity_type': route_data['amenity_info']['amenity_type']
                        })
                    
                    successful_routes.append(route_info)
                    if direction == 'inbound':
                        self._get_used_points(zone_id).add(origin_point)
                    else:
                        self._get_used_points(zone_id).add(destination_point)
                    trips_remaining -= 1
                    pbar.update(1)
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(f"Too many consecutive failures for zone {zone_id}. Skipping remaining trips.")
                        break
                    
                time.sleep(0.05)  # Sleep time
                
        return successful_routes

def main():
    # Initialize components
    loader = DataLoader()
    zones = loader.load_zones()
    poi_df = loader.load_poi_data()
    trip_data = loader.load_trip_data()
    
    # Load amenities
    amenities_path = "/Users/noamgal/DSProjects/BeerShevaMobility/shapes/data/output/points_within_buffer.shp"
    amenities = gpd.read_file(amenities_path)
    logger.info(f"Loaded {len(amenities)} amenities")
    
    # Load entrances
    entrances_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
        "data/filtered-entrances/filtered_entrances.shp"
    )
    entrances = gpd.read_file(entrances_path)
    
    otp_client = OTPClient()
    entrance_manager = EntranceManager(entrances)
    trip_generator = ImprovedTripGenerator(zones, otp_client, entrance_manager, amenities)
    
    target_pois = ['Ben-Gurion-University', 'Soroka-Medical-Center']
    all_trips = []
    
    total_pois = len(target_pois) * 2  # *2 for inbound/outbound
    with tqdm(total=total_pois, desc="Processing POIs") as poi_pbar:
        # Process each POI
        for poi_name in target_pois:
            # Process both inbound and outbound trips
            for direction in ['inbound', 'outbound']:
                logger.info(f"\nProcessing {poi_name} - {direction}")
                if (poi_name, direction) not in trip_data:
                    logger.warning(f"No {direction} trip data found for {poi_name}")
                    poi_pbar.update(1)
                    continue
                
                df = trip_data[(poi_name, direction)]
                
                # Verify required columns exist
                if 'total_trips' not in df.columns or 'mode_ped' not in df.columns:
                    logger.warning(f"Missing required columns in {direction} data for {poi_name}")
                    poi_pbar.update(1)
                    continue
                
                # Calculate and filter pedestrian trips
                df['ped_trips'] = df['total_trips'] * (df['mode_ped'] / 100)
                df = df[df['ped_trips'] >= 1]  # Only include zones with at least 1 pedestrian trip
                
                if df.empty:
                    logger.warning(f"No pedestrian trips found for {poi_name} - {direction}")
                    poi_pbar.update(1)
                    continue
                
                logger.info(f"Processing {int(df['ped_trips'].sum())} pedestrian trips for {poi_name} - {direction}")
                
                entrances = entrance_manager.get_entrances_for_poi(poi_name)
                if entrances.empty:
                    logger.warning(f"No entrances found for {poi_name}")
                    poi_pbar.update(1)
                    continue
                
                # Process each zone
                for _, zone_data in df.iterrows():
                    num_ped_trips = int(round(zone_data['ped_trips']))
                    if num_ped_trips < 1:
                        continue
                        
                    if direction == 'outbound':
                        # Select a random entrance as the origin
                        entrance = entrances.sample(n=1).iloc[0]
                        zone_trips = trip_generator.process_zone_trips(
                            zone_data['tract'],
                            num_ped_trips,
                            poi_name,
                            entrances,
                            zone_data,
                            direction='outbound',
                            fixed_origin=entrance
                        )
                    else:
                        zone_trips = trip_generator.process_zone_trips(
                            zone_data['tract'],
                            num_ped_trips,
                            poi_name,
                            entrances,
                            zone_data,
                            direction='inbound'
                        )
                    all_trips.extend(zone_trips)
                
                poi_pbar.update(1)
    
    # Create and save GeoDataFrames separately for inbound and outbound
    if all_trips:
        trips_gdf = gpd.GeoDataFrame(all_trips, crs="EPSG:4326")
        
        # Split into inbound and outbound
        inbound_trips = trips_gdf[trips_gdf['direction'] == 'inbound']
        outbound_trips = trips_gdf[trips_gdf['direction'] == 'outbound']
        
        # Save inbound trips
        inbound_file = os.path.join(OUTPUT_DIR, "walk_routes_inbound.geojson")
        inbound_trips.to_file(inbound_file, driver="GeoJSON")
        
        # Save outbound trips
        outbound_file = os.path.join(OUTPUT_DIR, "walk_routes_outbound.geojson")
        outbound_trips.to_file(outbound_file, driver="GeoJSON")
        
        # Log statistics
        logger.info(f"\nSaved {len(inbound_trips)} inbound walking routes representing {sum(t['num_trips'] for t in inbound_trips.to_dict('records')):,} trips")
        logger.info(f"Saved {len(outbound_trips)} outbound walking routes representing {sum(t['num_trips'] for t in outbound_trips.to_dict('records')):,} trips")
        logger.info(f"Inbound trips saved to: {inbound_file}")
        logger.info(f"Outbound trips saved to: {outbound_file}")
        
        # Log statistics about amenity stops for each direction
        inbound_amenities = sum(1 for t in inbound_trips.to_dict('records') if t['has_amenity_stop'])
        outbound_amenities = sum(1 for t in outbound_trips.to_dict('records') if t['has_amenity_stop'])
        
        logger.info(f"Inbound trips with amenity stops: {inbound_amenities} ({inbound_amenities/len(inbound_trips)*100:.1f}%)")
        logger.info(f"Outbound trips with amenity stops: {outbound_amenities} ({outbound_amenities/len(outbound_trips)*100:.1f}%)")
    else:
        logger.warning("\nNo walking routes were generated!")

if __name__ == "__main__":
    main()