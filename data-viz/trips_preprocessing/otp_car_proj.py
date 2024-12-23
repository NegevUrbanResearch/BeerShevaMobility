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
import sys
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from pyproj import Transformer
from config import BASE_DIR, OUTPUT_DIR, FINAL_ZONES_FILE, POI_FILE, FINAL_TRIPS_PATTERN, BUILDINGS_FILE
import polyline  # Add this import at the top
from rtree import index
from scipy.spatial import cKDTree
import logging


#    Bash Commands to Launch the OTP server on my local machine:
#    cd /Users/noamgal/Downloads/NUR/otp_project
#    java -Xmx8G -jar otp-2.5.0-shaded.jar --load --serve graphs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OTPClient:
    def __init__(self, base_url="http://localhost:8080/otp/routers/default", max_retries=3, retry_delay=0.5):
        self.base_url = base_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        
        # Verify OTP server is running and get graph bounds
        try:
            response = self.session.get(f"{self.base_url}/serverinfo", timeout=5)
            if response.status_code == 200:
                logger.info("Successfully connected to OTP server")
                # Log server bounds if available
                server_info = response.json()
                if 'bounds' in server_info:
                    logger.info(f"OTP Graph bounds: {server_info['bounds']}")
        except Exception as e:
            logger.error(f"Failed to connect to OTP server: {str(e)}")
    
    def get_car_route(self, from_lat, from_lon, to_lat, to_lon):
        """Query OTP for a driving route with retries and detailed logging"""
        params = {
            'fromPlace': f"{from_lat},{from_lon}",
            'toPlace': f"{to_lat},{to_lon}",
            'mode': 'CAR',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': '09:00:00',
            'arriveBy': 'false'
        }
        
        logger.info(f"Requesting route: from=({from_lat},{from_lon}) to=({to_lat},{to_lon})")
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    f"{self.base_url}/plan", 
                    params=params, 
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'error' in data:
                        error_msg = data.get('error', {}).get('msg', 'Unknown error')
                        logger.warning(f"OTP Error (attempt {attempt + 1}): {error_msg}")
                        
                        if 'OUTSIDE_BOUNDS' in error_msg:
                            # Try with adjusted coordinates
                            adjusted_params = self._adjust_coordinates(params)
                            if adjusted_params:
                                logger.info("Trying with adjusted coordinates")
                                adjusted_response = self.session.get(
                                    f"{self.base_url}/plan",
                                    params=adjusted_params,
                                    timeout=10
                                )
                                if adjusted_response.status_code == 200:
                                    adjusted_data = adjusted_response.json()
                                    if 'plan' in adjusted_data:
                                        return adjusted_data
                        
                        time.sleep(self.retry_delay)
                        continue
                    
                    if 'plan' in data:
                        return data
                    else:
                        logger.warning(f"No plan in response (attempt {attempt + 1})")
                        
                elif response.status_code == 500:
                    logger.warning(f"OTP server error (500) on attempt {attempt + 1}")
                    
                time.sleep(self.retry_delay)
                    
            except Exception as e:
                logger.error(f"Error getting route (attempt {attempt + 1}): {str(e)}")
                time.sleep(self.retry_delay)
                
        return None

    def _adjust_coordinates(self, params):
        """Adjust coordinates slightly to find a valid route"""
        try:
            from_coords = params['fromPlace'].split(',')
            to_coords = params['toPlace'].split(',')
            
            from_lat = float(from_coords[0])
            from_lon = float(from_coords[1])
            to_lat = float(to_coords[0])
            to_lon = float(to_coords[1])
            
            # Use Israel bounds
            MIN_LAT = 29.5
            MAX_LAT = 33.3
            MIN_LON = 34.2
            MAX_LON = 35.9
            
            # Adjust coordinates to nearest valid point if outside bounds
            def adjust_point(lat, lon):
                lat = np.clip(lat, MIN_LAT, MAX_LAT)
                lon = np.clip(lon, MIN_LON, MAX_LON)
                return lat, lon
            
            # Check if points are far outside bounds before adjusting
            if not self.is_within_bounds(from_lat, from_lon):
                from_lat, from_lon = adjust_point(from_lat, from_lon)
                
            if not self.is_within_bounds(to_lat, to_lon):
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
        self.otp_url = "http://localhost:8080/otp/routers/default"
        self.otp_client = OTPClient(base_url=self.otp_url)
        self.zone_used_points = {}
        self.load_data()
        
    def load_data(self):
        """Load and process all required data"""
        loader = DataLoader()
        self.zones = loader.load_zones()
        self.poi_df = loader.load_poi_data()
        
        # Debug POI coordinates
        print("\nPOI Coordinates:")
        for _, row in self.poi_df.iterrows():
            print(f"{row['name']}: lat={row['lat']}, lon={row['lon']}")
            if not self.is_within_bounds(row['lat'], row['lon']):
                logger.warning(f"POI {row['name']} coordinates outside bounds: lat={row['lat']}, lon={row['lon']}")
        
        self.trip_data = loader.load_trip_data()
        
        # Load amenities and ensure correct CRS
        amenities_path = "/Users/noamgal/DSProjects/BeerShevaMobility/shapes/data/output/points_within_buffer.shp"
        self.amenities = gpd.read_file(amenities_path)
        
        # Ensure amenities are in WGS84 (EPSG:4326)
        if self.amenities.crs != "EPSG:4326":
            self.amenities = self.amenities.to_crs("EPSG:4326")
        
        # Validate amenity coordinates
        invalid_amenities = self.amenities[~self.amenities.apply(
            lambda x: self.is_within_bounds(x.geometry.y, x.geometry.x), axis=1
        )]
        if not invalid_amenities.empty:
            logger.warning(f"Found {len(invalid_amenities)} amenities outside bounds")
        
        self.amenities = self._filter_clustered_amenities(self.amenities)
        
        # Clean POI names
        self.poi_df, self.trip_data = loader.clean_poi_names(self.poi_df, self.trip_data)
        
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

    def is_within_bounds(self, lat, lon):
        """Check if coordinates are within reasonable bounds for Israel"""
        # Israel approximate bounds
        MIN_LAT = 29.5  # Southern tip of Israel
        MAX_LAT = 33.3  # Northern tip of Israel
        MIN_LON = 34.2  # Western border
        MAX_LON = 35.9  # Eastern border
        
        return (MIN_LAT <= lat <= MAX_LAT) and (MIN_LON <= lon <= MAX_LON)

    def is_near_destination(self, amenity_lat, amenity_lon, dest_lat, dest_lon, max_distance_km=2.0):
        """Check if amenity is within max_distance_km of destination"""
        # Convert lat/lon to approximate kilometers (rough approximation)
        lat_diff = abs(amenity_lat - dest_lat) * 111  # 1 degree lat ≈ 111 km
        lon_diff = abs(amenity_lon - dest_lon) * 111 * np.cos(np.radians(dest_lat))
        
        distance = np.sqrt(lat_diff**2 + lon_diff**2)
        return distance <= max_distance_km

    def load_model_boundary(self):
        """Load the model boundary from shapefile"""
        model = gpd.read_file('data-viz/data/model_outline/big model.shp')
        if model.crs != 'EPSG:4326':
            model = model.to_crs('EPSG:4326')
        return model.geometry.iloc[0]

    def _find_suitable_amenity(self, origin_point, destination_point, max_detour_factor=1.3):
        """Find a suitable amenity that doesn't create too much of a detour"""
        if self.amenities.empty:
            return None
        
        # Load model boundary if not already loaded
        if not hasattr(self, 'model_boundary'):
            self.model_boundary = self.load_model_boundary()
        
        # Filter amenities to only those within model boundary
        valid_amenities = self.amenities[self.amenities.geometry.within(self.model_boundary)]
        
        if valid_amenities.empty:
            return None
        
        direct_distance = origin_point.distance(destination_point)
        
        # Ensure consistent coordinate order (lon, lat) for calculations
        origin_arr = np.array([origin_point.x, origin_point.y])  # x=lon, y=lat
        dest_arr = np.array([destination_point.x, destination_point.y])
        
        amenity_coords = np.column_stack((
            valid_amenities.geometry.x.values,  # lon
            valid_amenities.geometry.y.values   # lat
        ))
        
        # Calculate total distances through each amenity
        total_distances = (
            np.sqrt(np.sum((amenity_coords - origin_arr)**2, axis=1)) +
            np.sqrt(np.sum((amenity_coords - dest_arr)**2, axis=1))
        )
        
        # Filter by total route distance
        detour_mask = total_distances <= (direct_distance * max_detour_factor)
        
        if np.any(detour_mask):
            valid_indices = np.where(detour_mask)[0]
            chosen_idx = np.random.choice(valid_indices)
            chosen_amenity = valid_amenities.iloc[chosen_idx]
            
            return {
                'geometry': Point(amenity_coords[chosen_idx]),
                'amenity_id': chosen_amenity.name,
                'amenity_type': chosen_amenity['top_classi']
            }
        
        return None

    def _get_valid_route(self, origin_point, destination_point, amenity_stop=None):
        """Get a valid driving route, optionally including an amenity stop"""
        # Add debug logging for input coordinates
        logger.info(f"Route request - Origin: lat={origin_point.y}, lon={origin_point.x}")
        logger.info(f"Route request - Destination: lat={destination_point.y}, lon={destination_point.x}")
        
        # Create new points with adjusted coordinates if needed
        origin_y = origin_point.y
        origin_x = origin_point.x
        dest_y = destination_point.y
        dest_x = destination_point.x
        
        # Validate input coordinates before making request
        if not self.is_within_bounds(origin_y, origin_x):
            logger.warning("Origin coordinates out of bounds, adjusting...")
            origin_y = np.clip(origin_y, 31.0, 31.5)
            origin_x = np.clip(origin_x, 34.6, 35.0)
            origin_point = Point(origin_x, origin_y)
            
        if not self.is_within_bounds(dest_y, dest_x):
            logger.warning("Destination coordinates out of bounds, adjusting...")
            dest_y = np.clip(dest_y, 31.0, 31.5)
            dest_x = np.clip(dest_x, 34.6, 35.0)
            destination_point = Point(dest_x, dest_y)
        
        if amenity_stop:
            # Get route segments with detailed logging
            logger.info("Attempting route with amenity stop...")
            route1 = self.otp_client.get_car_route(
                origin_point.y, origin_point.x,
                amenity_stop['geometry'].y, amenity_stop['geometry'].x
            )
            if not route1 or 'plan' not in route1:
                logger.warning("Failed to get first route segment")
                if 'error' in route1:
                    logger.warning(f"OTP Error: {route1['error']}")
                return None
            
            route2 = self.otp_client.get_car_route(
                amenity_stop['geometry'].y, amenity_stop['geometry'].x,
                destination_point.y, destination_point.x
            )
            if not route2 or 'plan' not in route2:
                logger.warning("Failed to get second route segment")
                if 'error' in route2:
                    logger.warning(f"OTP Error: {route2['error']}")
                return None
            
            try:
                leg1 = route1['plan']['itineraries'][0]['legs'][0]
                leg2 = route2['plan']['itineraries'][0]['legs'][0]
                
                points1 = polyline.decode(leg1['legGeometry']['points'])
                points2 = polyline.decode(leg2['legGeometry']['points'])
                
                return {
                    'points': points1 + points2[1:],
                    'duration': leg1['duration'] + leg2['duration'],
                    'amenity_info': amenity_stop
                }
            except (KeyError, IndexError) as e:
                logger.warning(f"Error processing route segments: {str(e)}")
                return None
            
        else:
            # Add retry logic for direct routes
            max_retries = 3
            for attempt in range(max_retries):
                route = self.otp_client.get_car_route(
                    origin_point.y, origin_point.x,
                    destination_point.y, destination_point.x
                )
                
                if route and 'plan' in route and route['plan'].get('itineraries'):
                    try:
                        leg = route['plan']['itineraries'][0]['legs'][0]
                        return {
                            'points': polyline.decode(leg['legGeometry']['points']),
                            'duration': leg['duration'],
                            'amenity_info': None
                        }
                    except (KeyError, IndexError) as e:
                        logger.warning(f"Error processing route on attempt {attempt + 1}: {str(e)}")
                else:
                    logger.warning(f"Route attempt {attempt + 1} failed")
                    if route and 'error' in route:
                        logger.warning(f"OTP Error: {route['error']}")
                    if attempt < max_retries - 1:
                        time.sleep(1)  # Wait before retry
                        
            return None

    def transform_coords(self, x, y):
        """Transform coordinates from ITM to WGS84"""
        try:
            # Add detailed debug print before transformation
            logger.info(f"Input ITM coordinates: x={x}, y={y}")
            
            # Validate input coordinates
            if not (120000 <= x <= 250000) or not (500000 <= y <= 700000):
                logger.warning(f"ITM coordinates appear to be out of expected range: x={x}, y={y}")
            
            # Note: transformer expects (x,y) but returns (lon,lat)
            lon, lat = self.transformer.transform(x, y)
            
            # Add detailed debug print after transformation
            logger.info(f"Transformed to WGS84: lat={lat}, lon={lon}")
            
            # Validate the transformed coordinates
            if not (29.5 <= lat <= 33.3) or not (34.2 <= lon <= 35.9):
                logger.warning(f"Transformed coordinates outside Israel bounds: lat={lat}, lon={lon}")
                
                # Only adjust if coordinates are wildly off
                if abs(lat - 31.25) > 2 or abs(lon - 34.75) > 2:
                    logger.info("Coordinates far from Beer Sheva area, attempting adjustment")
                    # Center coordinates around Beer Sheva if they're way off
                    lat = np.clip(lat, 31.0, 31.5)
                    lon = np.clip(lon, 34.6, 35.0)
                    logger.info(f"Adjusted coordinates to: lat={lat}, lon={lon}")
            
            return lat, lon  # Return in lat,lon order for OTP
            
        except Exception as e:
            logger.error(f"Error in coordinate transformation: {str(e)}")
            return None, None

    def process_routes(self):
        """Process routes for all zones to each POI"""
        trips = []  # Define trips list
        route_cache = {}
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        main_pois = [
            'Ben-Gurion-University',
            'Soroka-Medical-Center'
        ]
        
        for poi_name in main_pois:
            logger.info(f"\nProcessing routes for {poi_name}")
            
            # Get POI coordinates
            poi_coords = self.poi_df[self.poi_df['name'] == poi_name]
            if len(poi_coords) == 0:
                logger.warning(f"No coordinates found for {poi_name}")
                continue
            
            # Debug POI data
            print(f"\nPOI data for {poi_name}:")
            print(f"Coordinates: {poi_coords[['name', 'lon', 'lat']].iloc[0].to_dict()}")
            
            try:
                poi_lat = float(poi_coords['lat'].iloc[0])
                poi_lon = float(poi_coords['lon'].iloc[0])
            except (KeyError, ValueError) as e:
                logger.error(f"Error getting POI coordinates: {e}")
                continue
                
            print(f"Using POI coordinates: lat={poi_lat}, lon={poi_lon}")
            
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
                
                # Process zones
                for _, zone_data in tqdm(trip_df.iterrows(), total=len(trip_df)):
                    zone_id = zone_data['tract']
                    car_trips = zone_data['total_trips'] * (zone_data['mode_car'] / 100)
                    
                    if car_trips < 0.5:
                        continue
                    
                    num_trips = int(round(car_trips))
                    zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
                    
                    if len(zone) == 0:
                        continue
                    
                    # Use zone centroid
                    centroid = zone.geometry.iloc[0].centroid
                    print(f"\nProcessing zone {zone_id}:")
                    print(f"Zone centroid (ITM): x={centroid.x}, y={centroid.y}")
                    
                    if direction == 'inbound':
                        # Transform from ITM to WGS84
                        origin_lat, origin_lon = self.transform_coords(centroid.x, centroid.y)
                        if origin_lat is None or origin_lon is None:
                            logger.warning(f"Skipping zone {zone_id} - coordinates out of bounds")
                            continue
                        dest_lat = poi_lat
                        dest_lon = poi_lon
                        print(f"Inbound route:")
                        print(f"From: lat={origin_lat}, lon={origin_lon}")
                        print(f"To: lat={dest_lat}, lon={dest_lon}")
                    else:
                        # For outbound, origin is POI and destination needs transformation
                        origin_lat = poi_lat
                        origin_lon = poi_lon
                        dest_lat, dest_lon = self.transform_coords(centroid.x, centroid.y)
                        if dest_lat is None or dest_lon is None:
                            logger.warning(f"Skipping zone {zone_id} - coordinates out of bounds")
                            continue
                        print(f"Outbound route:")
                        print(f"From: lat={origin_lat}, lon={origin_lon}")
                        print(f"To: lat={dest_lat}, lon={dest_lon}")
                    
                    # Debug coordinate transformation
                    logger.debug(f"Zone {zone_id} coordinates:")
                    logger.debug(f"Origin: lat={origin_lat}, lon={origin_lon}")
                    logger.debug(f"Destination: lat={dest_lat}, lon={dest_lon}")
                    
                    # Try to get route with amenity stop
                    route_data = None
                    if np.random.random() < 0.3:  # 30% chance of amenity stop
                        amenity_stop = self._find_suitable_amenity(
                            Point(origin_lon, origin_lat),
                            Point(dest_lon, dest_lat)
                        )
                        if amenity_stop:
                            route_data = self._get_valid_route(
                                Point(origin_lat, origin_lon),
                                Point(dest_lat, dest_lon),
                                amenity_stop
                            )
                    
                    # If no amenity route, try direct route
                    if not route_data:
                        cache_key = f"{origin_lat},{origin_lon}-{dest_lat},{dest_lon}"
                        if cache_key not in route_cache:
                            route = self.otp_client.get_car_route(
                                origin_lat, origin_lon,
                                dest_lat, dest_lon
                            )
                            
                            if route and 'plan' in route and route['plan']['itineraries']:
                                leg = route['plan']['itineraries'][0]['legs'][0]
                                route_cache[cache_key] = {
                                    'points': polyline.decode(leg['legGeometry']['points']),
                                    'duration': leg['duration']
                                }
                            
                            time.sleep(0.1)  # Rate limiting
                        
                        if cache_key in route_cache:
                            route_data = route_cache[cache_key]
                    
                    if route_data:
                        trip_info = {
                            'geometry': LineString([(lon, lat) for lat, lon in route_data['points']]),
                            'departure_time': departure_time,
                            'arrival_time': departure_time + pd.Timedelta(seconds=route_data['duration']),
                            'origin_zone': zone_id if direction == 'inbound' else poi_name,
                            'destination': poi_name if direction == 'inbound' else zone_id,
                            'route_id': f"{zone_id}-{poi_name}-{direction}-{len(trips)}",
                            'num_trips': num_trips,
                            'direction': direction,
                            'has_amenity_stop': bool(route_data.get('amenity_info'))
                        }
                        
                        if route_data.get('amenity_info'):
                            trip_info.update({
                                'amenity_id': route_data['amenity_info']['amenity_id'],
                                'amenity_type': route_data['amenity_info']['amenity_type']
                            })
                        
                        trips.append(trip_info)
        
        # Save results
        if trips:
            trips_gdf = gpd.GeoDataFrame(trips, crs="EPSG:4326")
            
            # Split and save inbound/outbound
            for direction in ['inbound', 'outbound']:
                direction_gdf = trips_gdf[trips_gdf['direction'] == direction]
                output_file = os.path.join(self.output_dir, f"car_routes_{direction}.geojson")
                direction_gdf.to_file(output_file, driver="GeoJSON")
                logger.info(f"Saved {len(direction_gdf)} {direction} routes to {output_file}")
            
            return trips_gdf
        else:
            logger.warning("No routes were generated!")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

if __name__ == "__main__":
    modeler = RouteModeler()
    road_usage = modeler.process_routes()