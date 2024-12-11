# otp_client.py
import requests
from datetime import datetime
import time
import polyline
from shapely.geometry import Point, LineString
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from config import OUTPUT_DIR

class OTPClient:
    def __init__(self, base_url="http://localhost:8080/otp/routers/default"):
        self.base_url = base_url
        
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
            response = requests.get(f"{self.base_url}/plan", params=params)
            if response.status_code == 200:
                data = response.json()
                if 'error' in data or 'plan' not in data:
                    return None
                return data
            return None
        except Exception:
            return None

# entrance_manager.py
import geopandas as gpd
import numpy as np

class EntranceManager:
    def __init__(self, entrances_gdf):
        self.entrances = entrances_gdf
        if self.entrances.crs != "EPSG:4326":
            self.entrances = self.entrances.to_crs("EPSG:4326")
    
    def get_entrances_for_poi(self, poi_name):
        """Get all entrance points for a given POI"""
        prefix = 'Hospital' if 'Soroka' in poi_name else 'Uni'
        return self.entrances[self.entrances['Name'].str.startswith(prefix)]
    
    def find_best_entrance(self, point, entrances, otp_client):
        """Find the closest entrance with a valid walking route"""
        best_route = None
        best_duration = float('inf')
        best_entrance = None
        
        origin_lat, origin_lon = point.y, point.x
        
        for _, entrance in entrances.iterrows():
            entrance_point = entrance.geometry
            route_data = otp_client.get_walking_route(
                origin_lat, 
                origin_lon,
                entrance_point.y,
                entrance_point.x
            )
            
            if route_data and 'plan' in route_data and route_data['plan']['itineraries']:
                itinerary = route_data['plan']['itineraries'][0]
                duration = itinerary['duration']
                
                if duration < best_duration:
                    best_duration = duration
                    best_route = route_data
                    best_entrance = entrance
                    
            time.sleep(0.1)
            
        return best_entrance, best_route

# trip_generator.py
import pandas as pd
from tqdm import tqdm
from shapely.geometry import Point
import numpy as np

class TripGenerator:
    def __init__(self, zones_gdf, otp_client, entrance_manager):
        self.zones = zones_gdf
        if self.zones.crs != "EPSG:4326":
            self.zones = self.zones.to_crs("EPSG:4326")
        self.otp_client = otp_client
        self.entrance_manager = entrance_manager
        
    def generate_random_points(self, geometry, num_points=50):
        """Generate random points within a zone geometry"""
        points = []
        minx, miny, maxx, maxy = geometry.bounds
        attempts = 0
        max_attempts = num_points * 2
        
        while len(points) < num_points and attempts < max_attempts:
            point = Point(
                np.random.uniform(minx, maxx),
                np.random.uniform(miny, maxy)
            )
            if geometry.contains(point):
                points.append(point)
            attempts += 1
                
        return points
    
    def process_zone_trips(self, zone_id, num_trips, poi_name, entrances):
        """Process trips for a single zone"""
        zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
        if len(zone) == 0:
            return []
            
        # Generate random points within the zone
        zone_geometry = zone.geometry.iloc[0]
        random_points = self.generate_random_points(zone_geometry, num_points=50)
        
        if not random_points:
            return []
        
        successful_routes = []
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        # Find routes for each point
        for point in random_points:
            best_entrance, route_data = self.entrance_manager.find_best_entrance(
                point, entrances, self.otp_client
            )
            
            if best_entrance is not None and route_data is not None:
                itinerary = route_data['plan']['itineraries'][0]
                leg = itinerary['legs'][0]
                
                successful_routes.append({
                    'points': polyline.decode(leg['legGeometry']['points']),
                    'duration': leg['duration'],
                    'entrance': best_entrance['Name'],
                    'origin_coords': [point.x, point.y]
                })
        
        # Allocate trips among successful routes
        trips = []
        if successful_routes:
            trips_per_route = num_trips / len(successful_routes)
            
            for i, route in enumerate(successful_routes):
                trips.append({
                    'geometry': LineString([(lon, lat) for lat, lon in route['points']]),
                    'departure_time': departure_time,
                    'arrival_time': departure_time + pd.Timedelta(seconds=route['duration']),
                    'origin_zone': zone_id,
                    'destination': poi_name,
                    'entrance': route['entrance'],
                    'route_id': f"{zone_id}-{poi_name}-{route['entrance']}-{i}",
                    'num_trips': trips_per_route,
                    'origin_x': route['origin_coords'][0],
                    'origin_y': route['origin_coords'][1]
                })
                
        return trips

# main.py
from data_loader import DataLoader
import os
import geopandas as gpd

def main():
    # Initialize components
    loader = DataLoader()
    zones = loader.load_zones()
    poi_df = loader.load_poi_data()
    trip_data = loader.load_trip_data()
    
    entrances_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                "data/filtered-entrances/filtered_entrances.shp")
    entrances = gpd.read_file(entrances_path)
    
    otp_client = OTPClient()
    entrance_manager = EntranceManager(entrances)
    trip_generator = TripGenerator(zones, otp_client, entrance_manager)
    
    target_pois = ['Ben-Gurion-University', 'Soroka-Medical-Center']
    all_trips = []
    
    # Process each POI
    for poi_name in target_pois:
        if (poi_name, 'inbound') not in trip_data:
            continue
            
        df = trip_data[(poi_name, 'inbound')]
        if 'total_trips' not in df.columns or 'mode_ped' not in df.columns:
            continue
            
        # Calculate pedestrian trips
        df['ped_trips'] = df['total_trips'] * (df['mode_ped'] / 100)
        df = df[df['ped_trips'] > 0]
        
        if df.empty:
            continue
            
        entrances = entrance_manager.get_entrances_for_poi(poi_name)
        if entrances.empty:
            continue
        
        # Process each zone
        for _, zone_data in tqdm(df.iterrows(), total=len(df)):
            zone_trips = trip_generator.process_zone_trips(
                zone_data['tract'],
                int(round(zone_data['ped_trips'])),
                poi_name,
                entrances
            )
            all_trips.extend(zone_trips)
    
    # Create and save GeoDataFrame
    if all_trips:
        trips_gdf = gpd.GeoDataFrame(all_trips, crs="EPSG:4326")
        output_file = os.path.join(OUTPUT_DIR, "walking_routes_trips.geojson")
        trips_gdf.to_file(output_file, driver="GeoJSON")
        print(f"\nSaved {len(trips_gdf)} walking routes to: {output_file}")
    else:
        print("\nNo walking routes were generated!")

if __name__ == "__main__":
    main()