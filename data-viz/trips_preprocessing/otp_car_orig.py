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
import logging
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from pyproj import Transformer
from config import BASE_DIR, OUTPUT_DIR, FINAL_ZONES_FILE, POI_FILE, FINAL_TRIPS_PATTERN, BUILDINGS_FILE
import polyline  




#    Bash Commands to Launch the OTP server on my local machine:
# 1. Navigate to the directory containing the OTP jar:
#    cd /Users/noamgal/Downloads/NUR/otp_project
# If necessary, run the build command:
# java -Xmx8G -jar otp-2.5.0-shaded.jar --build graphs/israel-and-palestine-latest.osm.pbf graphs/israel-public-transportation
# Run the server:
#    java -Xmx8G -jar otp-2.5.0-shaded.jar --load --serve graphs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RouteModeler:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.output_dir = OUTPUT_DIR
        self.otp_url = "http://localhost:8080/otp/routers/default"
        
        # Add coordinate transformer
        self.transformer = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)
        
        self.load_data()
        
        # Load and store POI polygons
        attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
        self.poi_polygons = attractions[attractions['ID'].isin([11, 7])]  # BGU and Soroka
        if self.poi_polygons.crs is None or self.poi_polygons.crs.to_string() != "EPSG:4326":
            self.poi_polygons = self.poi_polygons.to_crs("EPSG:4326")
            
    def load_data(self):
        """Load and process all required data"""
        loader = DataLoader()  # DataLoader will use the correct files from config
        
        # Load processed data that includes city zones
        self.zones = loader.load_zones()  # This will load from FINAL_ZONES_FILE
        self.poi_df = loader.load_poi_data()
        self.trip_data = loader.load_trip_data()
        
        # Clean POI names
        self.poi_df, self.trip_data = loader.clean_poi_names(self.poi_df, self.trip_data)
        
        # Debug zone types
        city_zones = self.zones[self.zones['YISHUV_STAT11'].str.startswith('C', na=False)]
        stat_zones = self.zones[~self.zones['YISHUV_STAT11'].str.startswith('C', na=False)]
        print(f"\nZone types loaded:")
        print(f"City zones: {len(city_zones)}")
        print(f"Statistical areas: {len(stat_zones)}")
        
        # Process trip data for POIs
        self.processed_trip_data = {}
        for poi_name, trip_type in self.trip_data.keys():
            if trip_type == 'inbound':  # We only want inbound trips
                df = self.trip_data[(poi_name, trip_type)]
                # Calculate car trips for both city and statistical area zones
                car_trips = df['mode_car'].sum()
                
                # Add car trips to dataframe
                df_with_cars = df.copy()
                df_with_cars['car_trips'] = car_trips
                
                # Store processed data
                self.processed_trip_data[poi_name] = df_with_cars
                
                print(f"\nProcessed {poi_name}:")
                print(f"Total car trips: {car_trips}")
                print(f"Zones with trips: {len(df_with_cars['tract'].unique())}")
        
    def generate_alternative_points(self, geometry, max_attempts=500):
        """Generate alternative points within a zone using multiple sampling strategies"""
        points = []
        failed_points = []
        
        # Buffer the geometry slightly inward to avoid edge cases
        buffered_geometry = geometry.buffer(-0.0001)  # About 10m buffer
        if buffered_geometry.is_empty:
            buffered_geometry = geometry
        
        minx, miny, maxx, maxy = buffered_geometry.bounds
        
        # Define sampling strategies with weights
        strategies = [
            ('random', int(max_attempts * 0.6)),  # 60% random sampling
            ('grid', int(max_attempts * 0.3)),    # 30% grid sampling
            ('edge', int(max_attempts * 0.1))     # 10% edge sampling
        ]
        
        for strategy, attempts in strategies:
            logger.debug(f"Trying {strategy} sampling strategy")
            
            for attempt in range(attempts):
                # Generate point based on strategy
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
                    if any(poi.geometry.contains(point) for _, poi in self.poi_polygons.iterrows()):
                        failed_points.append((point, f"Inside POI polygon ({strategy})"))
                        continue
                    
                    # Transform coordinates and validate
                    lat, lon = self.transform_coords(point.x, point.y)
                    if lat is None or lon is None:
                        failed_points.append((point, f"Invalid coordinates ({strategy})"))
                        continue
                        
                    # Test if point has graph access
                    params = {
                        'fromPlace': f"{lat},{lon}",
                        'toPlace': f"{lat},{lon}",
                        'mode': 'CAR'
                    }
                    
                    try:
                        response = requests.get(f"{self.otp_url}/plan", params=params)
                        if response.status_code == 200 and 'error' not in response.json():
                            points.append(point)
                            if len(points) >= 5:  # We only need a few valid points
                                return points
                    except Exception as e:
                        failed_points.append((point, f"OTP access error: {str(e)} ({strategy})"))
                        continue
                
                if attempt % 50 == 0:
                    logger.debug(f"Tried {attempt} points with {strategy} sampling")
        
        # If we haven't found enough points, try centroid-based fallback
        if not points:
            logger.warning("Trying centroid-based fallback points")
            centroid = geometry.centroid
            offsets = [(0,0), (0.001,0), (0,-0.001), (0.001,0.001), (-0.001,-0.001)]
            
            for offset in offsets:
                point = Point(centroid.x + offset[0], centroid.y + offset[1])
                if geometry.contains(point):
                    if not any(poi.geometry.contains(point) for _, poi in self.poi_polygons.iterrows()):
                        lat, lon = self.transform_coords(point.x, point.y)
                        if lat is not None and lon is not None:
                            points.append(point)
                            break
        
        if points:
            logger.info(f"Found {len(points)} valid points after trying multiple strategies")
            return points
        else:
            logger.error(f"Failed to find any valid points. Total failed attempts: {len(failed_points)}")
            return None
    
    def get_car_route(self, from_lat, from_lon, to_lat, to_lon, destination_poi=None):
        """Query OTP for a driving route with enhanced avoidance parameters"""
        logger.debug(f"Attempting route from ({from_lat}, {from_lon}) to ({to_lat}, {to_lon})")
        
        point_origin = Point(from_lon, from_lat)
        point_dest = Point(to_lon, to_lat)
        
        # Update POI name to ID mapping
        poi_name_to_id = {
            'Ben-Gurion-University': 11,
            'Soroka-Medical-Center': 7,
            'Gav-Yam-High-Tech-Park': 12  # Add Gav Yam mapping
        }
        
        # Only avoid BGU and Soroka polygons
        restricted_poi_ids = [11, 7]  # BGU and Soroka IDs
        avoid_polygons = []
        for _, poi in self.poi_polygons.iterrows():
            # Skip if this POI is not restricted (i.e., Gav Yam)
            if poi['ID'] not in restricted_poi_ids:
                continue
            
            # Only allow routing through POI if it's explicitly the destination POI
            if (destination_poi and poi_name_to_id.get(destination_poi) == poi['ID']):
                continue
            
            # If this POI contains either the origin or destination, allow routing through it
            if poi.geometry.contains(point_origin) or poi.geometry.contains(point_dest):
                continue
            
            # Ensure the polygon is valid and properly formatted
            if not poi.geometry.is_valid:
                poi.geometry = poi.geometry.buffer(0)
            
            # Calculate penalty based on area and add huge base penalty
            area_penalty = poi.geometry.area * 1e7  # Scale penalty by area
            base_penalty = 1e8  # Increase base penalty significantly
            
            # Add polygon to avoidance list with combined penalty
            avoid_polygons.append({
                'geometry': poi.geometry.wkt,
                'id': poi['ID'],
                'penalty': base_penalty + area_penalty
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
                'walkReluctance': 50,              # Increased from 20
                'turnReluctance': 4,               # Increased from 2
                'traversalCostMultiplier': 100,    # Increased from 5
                'nonpreferredCost': 1e8,           # Increased from 1000000
                'maxHours': 5,                     # Add maximum trip duration
                'maxWalkDistance': 0,              # Disable walking segments
                'alightSlack': 0,                  # Minimize slack time
                'driveDistanceReluctance': 5,      # Penalize longer routes
                'intersectionTraversalCost': 100   # Penalize complex intersections
            })
        
        try:
            response = requests.get(f"{self.otp_url}/plan", params=params)
            logger.debug(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if 'error' in data:
                    logger.warning(f"OTP Error: {data['error']}")
                    return None
                if 'plan' not in data:
                    logger.warning("No plan in response")
                    return None
                    
                # Validate the route doesn't cross avoided areas
                if 'plan' in data and 'itineraries' in data['plan']:
                    itinerary = data['plan']['itineraries'][0]
                    route_points = polyline.decode(itinerary['legs'][0]['legGeometry']['points'])
                    route_line = LineString([(lon, lat) for lat, lon in route_points])
                    
                    # Check if route intersects with any avoided polygons
                    for avoid_poly in avoid_polygons:
                        if route_line.intersects(wkt.loads(avoid_poly['geometry'])):
                            logger.warning(f"Route intersects avoided polygon {avoid_poly['id']}, rejecting...")
                            return None
                
                return data
                
            else:
                logger.error(f"Error response content: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting route: {str(e)}")
            return None
            
    def decode_polyline(self, encoded):
        """Decode Google's encoded polyline format"""
        points = []
        index = 0
        length = len(encoded)
        lat, lng = 0, 0

        while index < length:
            result = 1
            shift = 0
            while True:
                b = ord(encoded[index]) - 63 - 1
                index += 1
                result += b << shift
                shift += 5
                if b < 0x1f:
                    break
            lat += (~(result >> 1) if (result & 1) != 0 else (result >> 1))

            result = 1
            shift = 0
            while True:
                b = ord(encoded[index]) - 63 - 1
                index += 1
                result += b << shift
                shift += 5
                if b < 0x1f:
                    break
            lng += (~(result >> 1) if (result & 1) != 0 else (result >> 1))

            points.append([lat * 1e-5, lng * 1e-5])

        return points
    
    def process_routes(self):
        """Process routes for all zones to each POI"""
        trips = []
        route_cache = {}
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        # Update main POIs list
        main_pois = [
            'Ben-Gurion-University',
            'Soroka-Medical-Center',
            'Gav-Yam-High-Tech-Park'  # Add Gav Yam
        ]
        
        print("\nProcessing routes for main POIs:")
        for poi_name in main_pois:
            print(f"\nProcessing routes to {poi_name}")
            
            # Get POI coordinates
            poi_coords = self.poi_df[self.poi_df['name'] == poi_name]
            if len(poi_coords) == 0:
                print(f"Warning: No coordinates found for {poi_name}")
                continue
            
            # Process trip data for zones
            trip_df = self.trip_data.get((poi_name, 'inbound'))
            if trip_df is None:
                print(f"Warning: No trip data found for {poi_name}")
                continue
            
            # Filter out rows with NaN values in critical columns
            trip_df = trip_df.dropna(subset=['total_trips', 'mode_car'])
            
            # Filter for zones that have both trips and car mode share
            trip_df = trip_df[
                (trip_df['total_trips'] > 0) & 
                (trip_df['mode_car'] > 0)
            ]
            
            # Process only zones that have car trips
            for _, zone_data in tqdm(trip_df.iterrows(), total=len(trip_df)):
                zone_id = zone_data['tract']
                
                # Calculate actual car trips
                car_trips = zone_data['total_trips'] * (zone_data['mode_car'] / 100)
                if car_trips < 0.5:  # Skip if less than 0.5 car trips
                    continue
                    
                num_trips = int(round(car_trips))
                
                # Get zone geometry
                zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
                if len(zone) == 0:
                    continue
                    
                # Generate points avoiding POI polygons
                alternative_points = self.generate_alternative_points(zone.geometry.iloc[0])
                if not alternative_points:
                    print(f"Warning: Could not generate valid points for zone {zone_id}")
                    continue
                
                # Use the first valid point
                origin_point = alternative_points[0]
                origin_coords = self.transform_coords(origin_point.x, origin_point.y)
                dest_coords = (float(poi_coords['lat'].iloc[0]), float(poi_coords['lon'].iloc[0]))
                
                # Create cache key
                cache_key = f"{zone_id}-{poi_name}"
                
                # Check cache first
                if cache_key not in route_cache:
                    # Get route from OTP with POI avoidance
                    route_data = self.get_car_route(
                        origin_coords[0], origin_coords[1],
                        dest_coords[0], dest_coords[1],
                        destination_poi=poi_name
                    )
                    
                    if route_data and 'plan' in route_data and route_data['plan']['itineraries']:
                        itinerary = route_data['plan']['itineraries'][0]
                        leg = itinerary['legs'][0]
                        
                        route_cache[cache_key] = {
                            'points': polyline.decode(leg['legGeometry']['points']),
                            'duration': leg['duration']
                        }
                    
                    time.sleep(0.1)  # Rate limiting
                
                if cache_key in route_cache:
                    route_data = route_cache[cache_key]
                    # No need to transform points since they're already lat/lon pairs
                    trips.append({
                        'geometry': LineString([(lon, lat) for lat, lon in route_data['points']]),
                        'departure_time': departure_time,
                        'arrival_time': departure_time + pd.Timedelta(seconds=route_data['duration']),
                        'origin_zone': zone_id,
                        'destination': poi_name,
                        'route_id': cache_key,
                        'num_trips': num_trips
                    })

        # Create GeoDataFrame with routes
        if trips:
            trips_gdf = gpd.GeoDataFrame(trips, crs="EPSG:4326")
            print(f"\nTotal number of unique routes: {len(trips_gdf)}")
            return trips_gdf
        else:
            print("\nNo routes were generated!")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    def transform_coords(self, x, y):
        """Transform coordinates from ITM to WGS84"""
        # Note: transformer expects (x,y) but returns (lon,lat)
        lon, lat = self.transformer.transform(x, y)
        return lat, lon  # Return in lat,lon order for OTP

if __name__ == "__main__":
    modeler = RouteModeler()
    road_usage = modeler.process_routes()
    
    # Save the results
    output_file = os.path.join(modeler.output_dir, "road_usage_trips.geojson")
    road_usage.to_file(output_file, driver="GeoJSON")
    print(f"\nRoad usage data saved to: {output_file}")