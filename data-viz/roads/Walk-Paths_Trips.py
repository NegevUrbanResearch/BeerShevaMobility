
#    Bash Commands to Launch the OTP server on my local machine:
#    cd /Users/noamgal/Downloads/NUR/otp_project
#    java -Xmx8G -jar otp-2.5.0-shaded.jar --load --serve graphs
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
# Add parent directory to Python path to access data_loader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from pyproj import Transformer
from config import BASE_DIR, OUTPUT_DIR, FINAL_ZONES_FILE, POI_FILE, FINAL_TRIPS_PATTERN
import polyline

class RouteModeler:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.output_dir = OUTPUT_DIR
        self.otp_url = "http://localhost:8080/otp/routers/default"
        self.target_pois = ['Ben-Gurion-University', 'Soroka-Medical-Center']
        self.load_data()
        
    def load_data(self):
        """Load and process required data"""
        loader = DataLoader()
        
        self.zones = loader.load_zones()
        if self.zones.crs != "EPSG:4326":
            self.zones = self.zones.to_crs("EPSG:4326")
            
        self.poi_df = loader.load_poi_data()
        self.trip_data = loader.load_trip_data()
        
        # Load entrances data
        entrances_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                    "data/filtered-entrances/filtered_entrances.shp")
        self.entrances = gpd.read_file(entrances_path)
        if self.entrances.crs != "EPSG:4326":
            self.entrances = self.entrances.to_crs("EPSG:4326")
        
        # Process only target POIs
        self.poi_df, self.trip_data = loader.clean_poi_names(self.poi_df, self.trip_data)
        self.processed_trip_data = {}
        
        for poi_name, trip_type in self.trip_data.keys():
            if poi_name not in self.target_pois or trip_type != 'inbound':
                continue
                
            df = self.trip_data[(poi_name, trip_type)]
            if 'total_trips' not in df.columns or 'mode_ped' not in df.columns:
                continue
                
            ped_trips = df['total_trips'] * (df['mode_ped'] / 100)
            df_with_peds = df.copy()
            df_with_peds['ped_trips'] = ped_trips
            df_with_peds = df_with_peds[df_with_peds['ped_trips'] > 0]
            
            if len(df_with_peds) > 0:
                self.processed_trip_data[poi_name] = df_with_peds
                print(f"\nProcessed {poi_name}:")
                print(f"Total pedestrian trips: {ped_trips.sum():.1f}")
                print(f"Zones with pedestrian trips: {len(df_with_peds)}")
    
    def get_entrances_for_poi(self, poi_name):
        """Get all entrance points for a given POI"""
        prefix = 'Hospital' if 'Soroka' in poi_name else 'Uni'
        entrances = self.entrances[self.entrances['Name'].str.startswith(prefix)]
        return entrances
    
    def find_best_entrance(self, point, entrances):
        """Find the best entrance by trying walking routes to all entrances"""
        best_route = None
        best_duration = float('inf')
        best_entrance = None
        
        # Ensure point is in correct CRS
        if not isinstance(point, Point):
            print(f"Warning: Invalid point type: {type(point)}")
            return None, None
            
        transformed_coords = self.transform_coords(point.x, point.y)
        if transformed_coords is None:
            print("Invalid coordinates after transformation")
            return None, None
        
        origin_lat, origin_lon = transformed_coords
        print(f"\nTrying routes from origin ({origin_lat:.6f}, {origin_lon:.6f})")
        
        for _, entrance in entrances.iterrows():
            entrance_point = entrance.geometry
            entrance_name = entrance['Name']
            print(f"  Testing entrance {entrance_name}: ({entrance_point.y:.6f}, {entrance_point.x:.6f})")
            
            route_data = self.get_walking_route(
                origin_lat, 
                origin_lon,
                entrance_point.y,
                entrance_point.x
            )
            
            if route_data and 'plan' in route_data and route_data['plan']['itineraries']:
                itinerary = route_data['plan']['itineraries'][0]
                duration = itinerary['duration']
                print(f"    Route found: {duration:.1f} seconds")
                
                if duration < best_duration:
                    best_duration = duration
                    best_route = route_data
                    best_entrance = entrance
            else:
                print("    No route found")
                
            time.sleep(0.1)
        
        if best_entrance is not None:
            print(f"  Best entrance: {best_entrance['Name']} ({best_duration:.1f} seconds)")
        else:
            print("  No valid entrances found")
            
        return best_entrance, best_route

            
    
    def get_walking_route(self, from_lat, from_lon, to_lat, to_lon):
        """Query OTP for a walking route"""
        params = {
            'fromPlace': f"{from_lat},{from_lon}",
            'toPlace': f"{to_lat},{to_lon}",
            'mode': 'WALK',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': '09:00:00',
            'arriveBy': 'false',
            'walkSpeed': 1.4
        }
        
        try:
            response = requests.get(f"{self.otp_url}/plan", params=params)
            if response.status_code == 200:
                data = response.json()
                if 'error' in data or 'plan' not in data:
                    return None
                return data
            return None
        except Exception as e:
            return None

    def process_routes(self):
        """Process walking routes using best entrance approach"""
        trips = []
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        print("\nProcessing walking routes for POIs:")
        for poi_name in self.target_pois:
            print(f"\nProcessing routes to {poi_name}")
            
            if poi_name not in self.processed_trip_data:
                print(f"No trip data found for {poi_name}")
                continue
            
            # Get all entrances for this POI
            entrances = self.get_entrances_for_poi(poi_name)
            if len(entrances) == 0:
                print(f"No entrances found for {poi_name}")
                continue
                
            print(f"Found {len(entrances)} entrances:")
            for _, entrance in entrances.iterrows():
                print(f"  {entrance['Name']}: ({entrance.geometry.y:.6f}, {entrance.geometry.x:.6f})")
            
            trip_df = self.processed_trip_data[poi_name]
            
            # Calculate and filter distances before processing
            def calc_min_distance(row):
                zone = self.zones[self.zones['YISHUV_STAT11'] == row['tract']]
                if len(zone) == 0:
                    return float('inf')
                zone_centroid = zone.geometry.iloc[0].centroid
                min_dist = float('inf')
                for _, entrance in entrances.iterrows():
                    # Convert distance to meters (approximately)
                    dist = zone_centroid.distance(entrance.geometry) * 111000
                    min_dist = min(min_dist, dist)
                return min_dist
            
            trip_df['distance'] = trip_df.apply(calc_min_distance, axis=1)
            trip_df = trip_df[trip_df['distance'] <= 5000]
            print(f"Zones within walking distance (5km): {len(trip_df)}")
            
            # Process each zone
            for _, zone_data in tqdm(trip_df.iterrows(), total=len(trip_df)):
                zone_id = zone_data['tract']
                print(f"\nProcessing zone {zone_id}")
                print(f"Distance to nearest entrance: {zone_data['distance']:.1f}m")
                print(f"Pedestrian trips: {zone_data['ped_trips']:.1f}")
                
                num_trips = int(round(zone_data['ped_trips']))
                if num_trips < 1:
                    continue
                
                zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
                if len(zone) == 0:
                    print(f"Zone {zone_id} not found in geometries")
                    continue
                
                zone_geometry = zone.geometry.iloc[0]
                points_needed = min(num_trips, 20)
                random_points = self.generate_alternative_points(zone_geometry, points_needed)
                
                print(f"Generated {len(random_points)} random points")
                
                if not random_points:
                    print("No valid points generated")
                    continue
                
                successful_routes = []
                
                for i, point in enumerate(random_points):
                    print(f"\nTrying point {i+1}/{len(random_points)}")
                    best_entrance, route_data = self.find_best_entrance(point, entrances)
                    
                    if best_entrance is not None and route_data is not None:
                        itinerary = route_data['plan']['itineraries'][0]
                        leg = itinerary['legs'][0]
                        successful_routes.append({
                            'points': polyline.decode(leg['legGeometry']['points']),
                            'duration': leg['duration'],
                            'entrance': best_entrance['Name']
                        })
                
                if successful_routes:
                    print(f"Found {len(successful_routes)} successful routes")
                    
                    trips_per_route = num_trips // len(successful_routes)
                    extra_trips = num_trips % len(successful_routes)
                    
                    for i, route in enumerate(successful_routes):
                        route_trips = trips_per_route + (1 if i < extra_trips else 0)
                        if route_trips > 0:
                            trips.append({
                                'geometry': LineString([(lon, lat) for lat, lon in route['points']]),
                                'departure_time': departure_time,
                                'arrival_time': departure_time + pd.Timedelta(seconds=route['duration']),
                                'origin_zone': zone_id,
                                'destination': poi_name,
                                'entrance': route['entrance'],
                                'route_id': f"{zone_id}-{poi_name}-{route['entrance']}-{i}",
                                'num_trips': route_trips
                            })
                else:
                    print("No successful routes found")
        
        if trips:
            trips_gdf = gpd.GeoDataFrame(trips, crs="EPSG:4326")
            print(f"\nTotal number of unique walking routes: {len(trips_gdf)}")
            return trips_gdf
        else:
            print("\nNo walking routes were generated!")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


    def process_routes(self):
        """Process walking routes using best entrance approach"""
        trips = []
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        print("\nProcessing walking routes for POIs:")
        for poi_name in self.target_pois:
            print(f"\nProcessing routes to {poi_name}")
            
            if poi_name not in self.processed_trip_data:
                print(f"No trip data found for {poi_name}")
                continue
            
            # Get all entrances for this POI
            entrances = self.get_entrances_for_poi(poi_name)
            if len(entrances) == 0:
                print(f"No entrances found for {poi_name}")
                continue
                
            print(f"Found {len(entrances)} entrances:")
            for _, entrance in entrances.iterrows():
                print(f"  {entrance['Name']}: ({entrance.geometry.y:.6f}, {entrance.geometry.x:.6f})")
            
            trip_df = self.processed_trip_data[poi_name]
            
            # Calculate and filter distances before processing
            def calc_min_distance(row):
                zone = self.zones[self.zones['YISHUV_STAT11'] == row['tract']]
                if len(zone) == 0:
                    return float('inf')
                zone_centroid = zone.geometry.iloc[0].centroid
                min_dist = float('inf')
                for _, entrance in entrances.iterrows():
                    # Convert distance to meters (approximately)
                    dist = zone_centroid.distance(entrance.geometry) * 111000
                    min_dist = min(min_dist, dist)
                return min_dist
            
            trip_df['distance'] = trip_df.apply(calc_min_distance, axis=1)
            trip_df = trip_df[trip_df['distance'] <= 5000]
            print(f"Zones within walking distance (5km): {len(trip_df)}")
            
            # Process each zone
            for _, zone_data in tqdm(trip_df.iterrows(), total=len(trip_df)):
                zone_id = zone_data['tract']
                print(f"\nProcessing zone {zone_id}")
                print(f"Distance to nearest entrance: {zone_data['distance']:.1f}m")
                print(f"Pedestrian trips: {zone_data['ped_trips']:.1f}")
                
                num_trips = int(round(zone_data['ped_trips']))
                if num_trips < 1:
                    continue
                
                zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
                if len(zone) == 0:
                    print(f"Zone {zone_id} not found in geometries")
                    continue
                
                zone_geometry = zone.geometry.iloc[0]
                points_needed = min(num_trips, 20)
                random_points = self.generate_alternative_points(zone_geometry, points_needed)
                
                print(f"Generated {len(random_points)} random points")
                
                if not random_points:
                    print("No valid points generated")
                    continue
                
                successful_routes = []
                
                for i, point in enumerate(random_points):
                    print(f"\nTrying point {i+1}/{len(random_points)}")
                    best_entrance, route_data = self.find_best_entrance(point, entrances)
                    
                    if best_entrance is not None and route_data is not None:
                        itinerary = route_data['plan']['itineraries'][0]
                        leg = itinerary['legs'][0]
                        successful_routes.append({
                            'points': polyline.decode(leg['legGeometry']['points']),
                            'duration': leg['duration'],
                            'entrance': best_entrance['Name']
                        })
                
                if successful_routes:
                    print(f"Found {len(successful_routes)} successful routes")
                    
                    trips_per_route = num_trips // len(successful_routes)
                    extra_trips = num_trips % len(successful_routes)
                    
                    for i, route in enumerate(successful_routes):
                        route_trips = trips_per_route + (1 if i < extra_trips else 0)
                        if route_trips > 0:
                            trips.append({
                                'geometry': LineString([(lon, lat) for lat, lon in route['points']]),
                                'departure_time': departure_time,
                                'arrival_time': departure_time + pd.Timedelta(seconds=route['duration']),
                                'origin_zone': zone_id,
                                'destination': poi_name,
                                'entrance': route['entrance'],
                                'route_id': f"{zone_id}-{poi_name}-{route['entrance']}-{i}",
                                'num_trips': route_trips
                            })
                else:
                    print("No successful routes found")
        
        if trips:
            trips_gdf = gpd.GeoDataFrame(trips, crs="EPSG:4326")
            print(f"\nTotal number of unique walking routes: {len(trips_gdf)}")
            return trips_gdf
        else:
            print("\nNo walking routes were generated!")
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    
    def generate_alternative_points(self, geometry, num_points=20):
        """Generate alternative points within a zone"""
        points = []
        minx, miny, maxx, maxy = geometry.bounds
        
        for _ in range(num_points):
            point = Point(
                np.random.uniform(minx, maxx),
                np.random.uniform(miny, maxy)
            )
            if geometry.contains(point):
                points.append(point)
                
        return points
    
    def transform_coords(self, x, y):
        """Convert coordinates to lat,lon order for OTP"""
        # Since input is already in WGS84, just return in correct order
        return y, x  # Switch to lat,lon order for OTP

if __name__ == "__main__":
    modeler = RouteModeler()
    walking_routes = modeler.process_routes()
    
    if not walking_routes.empty:
        output_file = os.path.join(modeler.output_dir, "walking_routes_trips.geojson")
        walking_routes.to_file(output_file, driver="GeoJSON")
        print(f"\nWalking routes saved to: {output_file}")