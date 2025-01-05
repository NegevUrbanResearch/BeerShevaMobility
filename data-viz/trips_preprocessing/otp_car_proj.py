import pandas as pd
import geopandas as gpd
import requests
import json
from shapely.geometry import Point, LineString
import numpy as np
from datetime import datetime
import time
from tqdm import tqdm
from shapely import wkt
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from pyproj import Transformer
from config import BASE_DIR, OUTPUT_DIR
import polyline
import logging
from coordinate_utils import CoordinateValidator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OTPClient:
    def __init__(self, base_url="http://localhost:8080/otp/routers/default", max_retries=5, retry_delay=0.5):
        self.base_url = base_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        
        # Beer Sheva region bounds (slightly expanded)
        self.bounds = {
            'minLat': 31.15,
            'maxLat': 31.35,
            'minLon': 34.70,
            'maxLon': 34.90
        }
        
        # Load and store POI polygons
        attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
        self.poi_polygons = attractions[attractions['ID'].isin([7, 11])]  # BGU (7) and Soroka (11)
        if self.poi_polygons.crs is None or self.poi_polygons.crs.to_string() != "EPSG:4326":
            self.poi_polygons = self.poi_polygons.to_crs("EPSG:4326")
            
        # Verify OTP server and log bounds
        try:
            response = self.session.get(f"{self.base_url}/serverinfo", timeout=5)
            if response.status_code == 200:
                logger.info("Successfully connected to OTP server")
                logger.info(f"Using bounds: {self.bounds}")
        except Exception as e:
            logger.error(f"Failed to connect to OTP server: {str(e)}")

    def _validate_coordinates(self, lat, lon):
        """Validate and adjust coordinates to be within bounds"""
        if not (self.bounds['minLat'] <= lat <= self.bounds['maxLat']):
            lat = np.clip(lat, self.bounds['minLat'], self.bounds['maxLat'])
            logger.debug(f"Latitude adjusted to: {lat}")
            
        if not (self.bounds['minLon'] <= lon <= self.bounds['maxLon']):
            lon = np.clip(lon, self.bounds['minLon'], self.bounds['maxLon'])
            logger.debug(f"Longitude adjusted to: {lon}")
            
        return lat, lon
    def get_car_route(self, from_lat, from_lon, to_lat, to_lon, destination_poi=None):
        """
        Query OTP for a driving route with enhanced avoidance parameters.
        
        Parameters:
        - from_lat, from_lon: Origin coordinates
        - to_lat, to_lon: Destination coordinates
        - destination_poi: Name of destination POI ('Ben-Gurion-University' or 'Soroka-Medical-Center')
        """
        point_origin = Point(from_lon, from_lat)
        point_dest = Point(to_lon, to_lat)
        
        # Map POI names to IDs
        poi_name_to_id = {
            'Ben-Gurion-University': 7,
            'Soroka-Medical-Center': 11
        }
        
        # Determine which polygons to avoid with specific penalties
        avoid_polygons = []
        for _, poi in self.poi_polygons.iterrows():
            # Only allow routing through POI if it's explicitly the origin or destination POI
            if (destination_poi and poi_name_to_id.get(destination_poi) == poi['ID']):
                continue
            
            # If this POI contains either the origin or destination, allow routing through it
            if poi.geometry.contains(point_origin) or poi.geometry.contains(point_dest):
                continue
            
            # Ensure the polygon is valid and properly formatted
            if not poi.geometry.is_valid:
                poi.geometry = poi.geometry.buffer(0)
            
            # Add polygon to avoidance list with specific penalty
            avoid_polygons.append({
                'geometry': poi.geometry.wkt,
                'id': poi['ID'],
                'penalty': 1000000  # Very high penalty for crossing avoided areas
            })
        
        params = {
            'fromPlace': f"{from_lat},{from_lon}",
            'toPlace': f"{to_lat},{to_lon}",
            'mode': 'CAR',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': '09:00:00',
            'arriveBy': 'false',
            'locale': 'en'
        }
        
        # Add enhanced avoidance parameters
        if avoid_polygons:
            # Create avoidance string with penalties
            avoid_str = '|'.join(f"{p['geometry']}::{p['penalty']}" for p in avoid_polygons)
            params.update({
                'avoid': avoid_str,
                'walkReluctance': 20,
                'turnReluctance': 2,            # Increased turn reluctance
                'traversalCostMultiplier': 5,   # Higher cost for traversing avoided areas
                'nonpreferredCost': 1000000     # Very high cost for non-preferred routes
            })
        
        logger.debug(f"Requesting route with params: {params}")
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    f"{self.base_url}/plan", 
                    params=params, 
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'error' in data or 'plan' not in data:
                        logger.warning(f"OTP returned invalid response: {data.get('error', 'No plan found')}")
                        return None
                    
                    # Validate the route doesn't cross avoided areas
                    if 'plan' in data and 'itineraries' in data['plan']:
                        itinerary = data['plan']['itineraries'][0]
                        route_points = polyline.decode(itinerary['legs'][0]['legGeometry']['points'])
                        route_line = LineString([(lon, lat) for lat, lon in route_points])
                        
                        # Check if route intersects with any avoided polygons
                        for avoid_poly in avoid_polygons:
                            if route_line.intersects(wkt.loads(avoid_poly['geometry'])):
                                logger.warning(f"Route intersects avoided polygon {avoid_poly['id']}, retrying...")
                                return None
                    
                    return data
                    
                elif response.status_code == 429:  # Too Many Requests
                    wait_time = (attempt + 1) * self.retry_delay
                    logger.warning(f"Rate limited. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                    
            except Exception as e:
                logger.error(f"Error getting route (attempt {attempt + 1}): {str(e)}")
                time.sleep(self.retry_delay)
                
        return None

    def _adjust_coordinates(self, params):
        """Adjust coordinates to be within Israel bounds"""
        try:
            from_coords = params['fromPlace'].split(',')
            to_coords = params['toPlace'].split(',')
            
            from_lat = float(from_coords[0])
            from_lon = float(from_coords[1])
            to_lat = float(to_coords[0])
            to_lon = float(to_coords[1])
            
            # Israel bounds
            MIN_LAT = 29.5
            MAX_LAT = 33.3
            MIN_LON = 34.2
            MAX_LON = 35.9
            
            def adjust_point(lat, lon):
                lat = np.clip(lat, MIN_LAT, MAX_LAT)
                lon = np.clip(lon, MIN_LON, MAX_LON)
                return lat, lon
            
            if not (MIN_LAT <= from_lat <= MAX_LAT and MIN_LON <= from_lon <= MAX_LON):
                from_lat, from_lon = adjust_point(from_lat, from_lon)
                
            if not (MIN_LAT <= to_lat <= MAX_LAT and MIN_LON <= to_lon <= MAX_LON):
                to_lat, to_lon = adjust_point(to_lat, to_lon)
            
            return {
                **params,
                'fromPlace': f"{from_lat},{from_lon}",
                'toPlace': f"{to_lat},{to_lon}"
            }
            
        except Exception as e:
            logger.error(f"Error adjusting coordinates: {str(e)}")
            return None

class RouteModeler:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.output_dir = OUTPUT_DIR
        self.transformer = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)
        self.otp_client = OTPClient(base_url="http://localhost:8080/otp/routers/default")
        self.load_data()
        
    def load_data(self):
        """Load and process required data"""
        loader = DataLoader()
        self.zones = loader.load_zones()
        self.poi_df = loader.load_poi_data()
        self.trip_data = loader.load_trip_data()
        
        # Clean POI names
        self.poi_df, self.trip_data = loader.clean_poi_names(self.poi_df, self.trip_data)
        
        # Debug POI coordinates
        for _, row in self.poi_df.iterrows():
            if not self.is_within_bounds(row['lat'], row['lon']):
                logger.warning(f"POI {row['name']} coordinates outside bounds: lat={row['lat']}, lon={row['lon']}")

    def is_within_bounds(self, lat, lon):
        """Check if coordinates are within Israel bounds"""
        MIN_LAT, MAX_LAT = 29.5, 33.3
        MIN_LON, MAX_LON = 34.2, 35.9
        return (MIN_LAT <= lat <= MAX_LAT) and (MIN_LON <= lon <= MAX_LON)

    def transform_coords(self, x, y):
        """Transform coordinates from ITM to WGS84"""
        try:
            # Validate ITM coordinates first
            x, y, itm_valid = CoordinateValidator.validate_itm(x, y)
            if not itm_valid:
                logger.debug("Using adjusted ITM coordinates for transformation")
            
            # Transform to WGS84
            lon, lat = self.transformer.transform(x, y)
            
            # Validate transformed coordinates against Israel bounds
            lat, lon, wgs_valid = CoordinateValidator.validate_wgs84(lat, lon, use_beer_sheva_bounds=False)
            
            if not wgs_valid:
                logger.debug("Using adjusted WGS84 coordinates")
            
            return lat, lon
            
        except Exception as e:
            logger.error(f"Error in coordinate transformation: {str(e)}")
            return None, None

    def get_route(self, origin_lat, origin_lon, dest_lat, dest_lon):
        """Get a direct route between two points"""
        route = self.otp_client.get_car_route(
            origin_lat, origin_lon,
            dest_lat, dest_lon
        )
        
        if route and 'plan' in route and route['plan'].get('itineraries'):
            try:
                leg = route['plan']['itineraries'][0]['legs'][0]
                return {
                    'points': polyline.decode(leg['legGeometry']['points']),
                    'duration': leg['duration']
                }
            except (KeyError, IndexError) as e:
                logger.warning(f"Error processing route: {str(e)}")
        
        return None

    def process_routes(self):
        """Process routes for all zones to each POI"""
        trips = []
        route_cache = {}
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        main_pois = ['Ben-Gurion-University', 'Soroka-Medical-Center']
        
        for poi_name in main_pois:
            logger.info(f"\nProcessing routes for {poi_name}")
            
            poi_coords = self.poi_df[self.poi_df['name'] == poi_name]
            if len(poi_coords) == 0:
                logger.warning(f"No coordinates found for {poi_name}")
                continue
            
            try:
                poi_lat = float(poi_coords['lat'].iloc[0])
                poi_lon = float(poi_coords['lon'].iloc[0])
            except (KeyError, ValueError) as e:
                logger.error(f"Error getting POI coordinates: {e}")
                continue
            
            for direction in ['inbound', 'outbound']:
                if (poi_name, direction) not in self.trip_data:
                    logger.warning(f"No {direction} trip data found for {poi_name}")
                    continue
                
                trip_df = self.trip_data[(poi_name, direction)].copy()
                trip_df = trip_df.dropna(subset=['total_trips', 'mode_car'])
                trip_df = trip_df[
                    (trip_df['total_trips'] > 0) & 
                    (trip_df['mode_car'] > 0)
                ]
                
                total_car_trips = (trip_df['total_trips'] * trip_df['mode_car'] / 100).sum()
                logger.info(f"Processing {int(total_car_trips)} car trips for {poi_name} - {direction}")
                
                for _, zone_data in tqdm(trip_df.iterrows(), total=len(trip_df)):
                    zone_id = zone_data['tract']
                    car_trips = zone_data['total_trips'] * (zone_data['mode_car'] / 100)
                    
                    if car_trips < 0.5:
                        continue
                    
                    num_trips = int(round(car_trips))
                    zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
                    
                    if len(zone) == 0:
                        continue
                    
                    centroid = zone.geometry.iloc[0].centroid
                    
                    if direction == 'inbound':
                        origin_lat, origin_lon = self.transform_coords(centroid.x, centroid.y)
                        if origin_lat is None:
                            continue
                        dest_lat, dest_lon = poi_lat, poi_lon
                    else:
                        origin_lat, origin_lon = poi_lat, poi_lon
                        dest_lat, dest_lon = self.transform_coords(centroid.x, centroid.y)
                        if dest_lat is None:
                            continue
                    
                    cache_key = f"{origin_lat},{origin_lon}-{dest_lat},{dest_lon}"
                    
                    if cache_key not in route_cache:
                        route_data = self.get_route(origin_lat, origin_lon, dest_lat, dest_lon)
                        if route_data:
                            route_cache[cache_key] = route_data
                        time.sleep(0.1)  # Rate limiting
                    
                    if cache_key in route_cache:
                        route_data = route_cache[cache_key]
                        
                        trip_info = {
                            'geometry': LineString([(lon, lat) for lat, lon in route_data['points']]),
                            'departure_time': departure_time,
                            'arrival_time': departure_time + pd.Timedelta(seconds=route_data['duration']),
                            'origin_zone': zone_id if direction == 'inbound' else poi_name,
                            'destination': poi_name if direction == 'inbound' else zone_id,
                            'route_id': f"{zone_id}-{poi_name}-{direction}-{len(trips)}",
                            'num_trips': num_trips,
                            'direction': direction
                        }
                        
                        trips.append(trip_info)
        
        if trips:
            trips_gdf = gpd.GeoDataFrame(trips, crs="EPSG:4326")
            
            for direction in ['inbound', 'outbound']:
                direction_gdf = trips_gdf[trips_gdf['direction'] == direction]
                output_file = os.path.join(self.output_dir, f"car_routes_{direction}.geojson")
                direction_gdf.to_file(output_file, driver="GeoJSON")
                logger.info(f"Saved {len(direction_gdf)} {direction} routes to {output_file}")
            
            return trips_gdf
        
        logger.warning("No routes were generated!")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    def _generate_unique_point(self, zone_id, geometry, max_attempts=500):  # Increased attempts
        """Generate a unique random point within a geometry with more attempts and edge buffering"""
        used_points = self._get_used_points(zone_id)
        
        # Buffer the geometry slightly inward to avoid edge cases
        buffered_geometry = geometry.buffer(-0.0001)  # About 10m buffer
        if buffered_geometry.is_empty:
            buffered_geometry = geometry  # Fall back to original if buffer makes it empty
        
        minx, miny, maxx, maxy = buffered_geometry.bounds
        
        # Create a list to store failed points for debugging
        failed_points = []
        
        # Try different sampling strategies
        strategies = [
            ('random', int(max_attempts * 0.6)),  # 60% random sampling
            ('grid', int(max_attempts * 0.3)),    # 30% grid sampling
            ('edge', int(max_attempts * 0.1))     # 10% edge sampling
        ]
        
        for strategy, attempts in strategies:
            logger.debug(f"Trying {strategy} sampling for zone {zone_id}")
            
            for attempt in range(attempts):
                if strategy == 'random':
                    point = Point(
                        np.random.uniform(minx, maxx),
                        np.random.uniform(miny, maxy)
                    )
                elif strategy == 'grid':
                    # Create a grid of points
                    grid_size = int(np.sqrt(attempts))
                    x_points = np.linspace(minx, maxx, grid_size)
                    y_points = np.linspace(miny, maxy, grid_size)
                    grid_x = x_points[attempt % grid_size]
                    grid_y = y_points[(attempt // grid_size) % grid_size]
                    point = Point(grid_x, grid_y)
                else:  # edge sampling
                    # Sample points along the geometry's boundary
                    boundary_point = geometry.boundary.interpolate(
                        np.random.random(), normalized=True
                    )
                    # Move slightly inward
                    point = Point(
                        boundary_point.x + np.random.uniform(-0.0005, 0.0005),
                        boundary_point.y + np.random.uniform(-0.0005, 0.0005)
                    )
                
                if buffered_geometry.contains(point):
                    # Check if point is within any POI polygon
                    if any(poi.geometry.contains(point) for _, poi in self.otp_client.poi_polygons.iterrows()):
                        failed_points.append((point, f"Inside POI polygon ({strategy})"))
                        continue
                    
                    # Check if point is sufficiently far from used points (10 meters ≈ 0.0001 degrees)
                    if all(point.distance(p) > 0.0001 for p in used_points):
                        # Verify the point has graph access
                        lat, lon = point.y, point.x
                        if self.otp_client.test_point_access(lat, lon):
                            logger.debug(f"Found valid point using {strategy} sampling: ({lat}, {lon})")
                            return point
                        else:
                            failed_points.append((point, f"No graph access ({strategy})"))
                    else:
                        failed_points.append((point, f"Too close to used points ({strategy})"))
                
                if attempt % 50 == 0:  # Log progress periodically
                    logger.debug(f"Tried {attempt} points with {strategy} sampling")
        
        # If we get here, we failed to find a valid point
        logger.warning(f"Failed to find valid point in zone {zone_id} after trying multiple strategies")
        logger.debug(f"Failed points: {len(failed_points)} total")
        
        # Try points near the centroid as a last resort
        centroid = geometry.centroid
        for offset in [(0,0), (0.001,0), (0,-0.001), (0.001,0.001), (-0.001,-0.001)]:
            point = Point(centroid.x + offset[0], centroid.y + offset[1])
            if buffered_geometry.contains(point):
                # Check if point is within any POI polygon
                if any(poi.geometry.contains(point) for _, poi in self.otp_client.poi_polygons.iterrows()):
                    continue
                
                lat, lon = point.y, point.x
                if self.otp_client.test_point_access(lat, lon):
                    logger.warning(f"Falling back to adjusted centroid point: ({lat}, {lon})")
                    return point
        
        # Absolute last resort - return centroid even if it might not work
        logger.error(f"All point generation strategies failed for zone {zone_id}, using raw centroid")
        return Point(centroid.x, centroid.y)

    def process_zone_trips(self, zone_id, num_trips, poi_name, entrances, zone_data, direction='inbound', fixed_origin=None):
        """Process all trips for a single zone"""
        zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
        if len(zone) == 0:
            return []
        
        zone_geometry = zone.geometry.iloc[0]
        successful_routes = []
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        max_point_attempts = 5  # Try up to 5 different points before giving up
        
        with tqdm(total=num_trips, desc=f"Zone {zone_id} {direction}") as pbar:
            trips_remaining = num_trips
            while trips_remaining > 0:
                route_found = False
                
                # Try different points within the zone
                for point_attempt in range(max_point_attempts):
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
                    
                    route_data = self._get_valid_route(
                        origin_point,
                        destination_point
                    )
                    
                    if route_data:
                        route_found = True
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
                            'zone_total_trips': zone_data['total_trips'],
                            'zone_ped_trips': zone_data['ped_trips']
                        }
                        
                        successful_routes.append(route_info)
                        if direction == 'inbound':
                            self._get_used_points(zone_id).add(origin_point)
                        else:
                            self._get_used_points(zone_id).add(destination_point)
                        trips_remaining -= 1
                        pbar.update(1)
                        break  # Exit point attempt loop if route is found
                    
                    else:
                        logger.debug(f"Failed to find route with point attempt {point_attempt + 1}/{max_point_attempts}")
                
                if not route_found:
                    logger.warning(f"Failed to find valid route after {max_point_attempts} point attempts for zone {zone_id}")
                    break  # Exit trip generation for this zone if we can't find any valid points
                
                time.sleep(0.05)  # Sleep time between successful routes
            
        return successful_routes

if __name__ == "__main__":
    modeler = RouteModeler()
    road_usage = modeler.process_routes()