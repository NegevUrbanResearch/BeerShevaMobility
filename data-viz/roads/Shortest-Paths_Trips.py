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
from config import BASE_DIR, OUTPUT_DIR

# Rest of the file remains the same

#    Bash Commands to Launch the OTP server on my local machine:
#    cd /Users/noamgal/Downloads/NUR/otp_project
#    java -Xmx8G -jar otp-2.5.0-shaded.jar --load --serve graphs

class RouteModeler:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.output_dir = OUTPUT_DIR
        self.otp_url = "http://localhost:8080/otp/routers/default"
        
        # Add coordinate transformer
        self.transformer = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)
        
        self.load_data()
        
    def load_data(self):
        # Use the existing DataLoader
        loader = DataLoader(self.base_dir, self.output_dir)
        self.zones = loader.load_zones()
        self.poi_df = loader.load_poi_data()
        
        # Load trip data for the three POIs we're interested in
        self.trip_data = {}
        for poi in ['BGU', 'Gev Yam', 'Soroka Hospital']:
            df = loader.load_trip_data()[(poi, 'inbound')]
            
            # Debug: print column names
            print(f"\nColumns for {poi}:")
            print(df.columns.tolist())
            
            # Find the car mode column (it might be 'mode_car' or 'mode_Car' or similar)
            car_mode_col = next((col for col in df.columns if col.lower().startswith('mode_') and 'car' in col.lower()), None)
            
            if car_mode_col:
                df['car_trips'] = df['total_trips'] * (df[car_mode_col] / 100)
            else:
                print(f"Warning: No car mode column found for {poi}")
                df['car_trips'] = 0
                
            self.trip_data[poi] = df
            
    def generate_alternative_points(self, geometry, num_points=20):
        """Generate alternative points within a zone if centroid isn't accessible"""
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
    
    def get_car_route(self, from_x, from_y, to_lat, to_lon):
        """Query OTP for a driving route"""
        # Transform only the origin coordinates from ITM to WGS84
        from_lat, from_lon = self.transform_coords(from_x, from_y)
        
        print(f"\nTransformed coordinates:")
        print(f"From: ({from_x}, {from_y}) -> ({from_lat}, {from_lon})")
        print(f"To: ({to_lat}, {to_lon})")  # Already in WGS84
        
        params = {
            'fromPlace': f"{from_lat},{from_lon}",
            'toPlace': f"{to_lat},{to_lon}",
            'mode': 'CAR',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': '09:00:00',
            'arriveBy': 'false'
        }
        
        try:
            response = requests.get(f"{self.otp_url}/plan", params=params)
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if 'error' in data:
                    print(f"OTP Error: {data['error']}")
                    return None
                if 'plan' not in data:
                    print("No plan in response")
                    print(f"Response content: {data}")
                    return None
                return data
            else:
                print(f"Error response content: {response.text}")
                return None
        except Exception as e:
            print(f"Error getting route: {str(e)}")
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
        # Initialize list to store individual trips
        trips = []
        route_cache = {}  # Cache for storing unique routes
        
        # Set fixed departure time
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        for poi_name in ['BGU', 'Gev Yam', 'Soroka Hospital']:
            print(f"\nProcessing routes to {poi_name}")
            poi_coords = self.poi_df[self.poi_df['name'] == poi_name].iloc[0]
            trip_df = self.trip_data[poi_name]
            
            for _, zone in tqdm(self.zones.iterrows(), total=len(self.zones)):
                car_trips = trip_df[trip_df['tract'] == zone['YISHUV_STAT11']]['car_trips'].values
                if not len(car_trips) or car_trips[0] < 1:
                    continue
                
                num_trips = int(round(car_trips[0]))
                
                # Create cache key for this origin-destination pair
                cache_key = f"{zone['YISHUV_STAT11']}_{poi_name}"
                
                # Check if route is already cached
                if cache_key not in route_cache:
                    centroid = zone.geometry.centroid
                    route = self.get_car_route(
                        centroid.x, centroid.y,
                        float(poi_coords['lat']), float(poi_coords['lon'])
                    )
                    
                    if route and 'plan' in route:
                        try:
                            leg = route['plan']['itineraries'][0]['legs'][0]
                            points = self.decode_polyline(leg['legGeometry']['points'])
                            route_cache[cache_key] = {
                                'points': points,
                                'duration': leg['duration']
                            }
                        except Exception as e:
                            print(f"Error processing route: {e}")
                            continue
                    
                    time.sleep(0.1)  # Rate limiting
                
                # Use cached route data
                if cache_key in route_cache:
                    route_data = route_cache[cache_key]
                    # Create single trip entry with number of trips as attribute
                    trips.append({
                        'geometry': LineString([(p[1], p[0]) for p in route_data['points']]),
                        'departure_time': departure_time,
                        'arrival_time': departure_time + pd.Timedelta(seconds=route_data['duration']),
                        'origin_zone': zone['YISHUV_STAT11'],
                        'destination': poi_name,
                        'route_id': cache_key,
                        'num_trips': num_trips  # Add number of trips using this route
                    })

        # Create GeoDataFrame with routes
        trips_gdf = gpd.GeoDataFrame(trips, crs="EPSG:4326")
        print(f"\nTotal number of unique routes: {len(trips_gdf)}")
        
        return trips_gdf

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
