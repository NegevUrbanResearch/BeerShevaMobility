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
from config import BASE_DIR, OUTPUT_DIR, FINAL_ZONES_FILE, POI_FILE, FINAL_TRIPS_PATTERN
import polyline  # Add this import at the top


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
        trips = []
        route_cache = {}
        departure_time = datetime.now().replace(hour=8, minute=0, second=0)
        
        # Define main POIs using standardized names
        main_pois = [
            'Ben-Gurion-University',
            'Gav-Yam-High-Tech-Park',
            'Soroka-Medical-Center'
        ]
        
        print("\nProcessing routes for main POIs:")
        for poi_name in main_pois:
            print(f"\nProcessing routes to {poi_name}")
            
            # Get POI coordinates
            poi_coords = self.poi_df[self.poi_df['name'] == poi_name]
            if len(poi_coords) == 0:
                print(f"Warning: No coordinates found for {poi_name}")
                continue
            
            # Get trip data using standardized name and inbound trips
            if (poi_name, 'inbound') not in self.trip_data:
                print(f"Warning: No trip data found for {poi_name}")
                continue
            
            trip_df = self.trip_data[(poi_name, 'inbound')].copy()
            
            # Filter out rows with NaN values in critical columns
            trip_df = trip_df.dropna(subset=['total_trips', 'mode_car'])
            
            # Filter for zones that have both trips and car mode share
            trip_df = trip_df[
                (trip_df['total_trips'] > 0) & 
                (trip_df['mode_car'] > 0)
            ]
            
            total_trips = trip_df['total_trips'].sum()
            total_car_trips = (trip_df['total_trips'] * trip_df['mode_car'] / 100).sum()
            
            print(f"\nTrip data summary for {poi_name}:")
            print(f"Total trips across all zones: {total_trips:.1f}")
            print(f"Total car trips: {total_car_trips:.1f}")
            print(f"Number of zones with car trips: {len(trip_df)}")
            
            # Sample a few zones for debugging
            print("\nSample zone data:")
            sample_zones = trip_df.head(3)
            for _, zone_data in sample_zones.iterrows():
                print(f"\nZone {zone_data['tract']}:")
                print(f"Total trips: {zone_data['total_trips']:.1f}")
                print(f"Car mode %: {zone_data['mode_car']:.1f}%")
                car_trips = zone_data['total_trips'] * (zone_data['mode_car'] / 100)
                print(f"Calculated car trips: {car_trips:.1f}")
            
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
                    
                # Get zone centroid
                centroid = zone.geometry.iloc[0].centroid
                origin_coords = self.transform_coords(centroid.x, centroid.y)
                dest_coords = (float(poi_coords['lat'].iloc[0]), float(poi_coords['lon'].iloc[0]))
                
                # Create cache key
                cache_key = f"{zone_id}-{poi_name}"
                
                # Check cache first
                if cache_key not in route_cache:
                    # Get route from OTP
                    params = {
                        'fromPlace': f"{origin_coords[0]},{origin_coords[1]}",
                        'toPlace': f"{dest_coords[0]},{dest_coords[1]}",
                        'time': departure_time.strftime('%I:%M%p'),
                        'date': departure_time.strftime('%Y-%m-%d'),
                        'mode': 'CAR',
                        'arriveBy': 'false'
                    }
                    
                    try:
                        response = requests.get(f"{self.otp_url}/plan", params=params)
                        route_data = response.json()
                        
                        if 'plan' not in route_data or not route_data['plan']['itineraries']:
                            continue
                            
                        itinerary = route_data['plan']['itineraries'][0]
                        leg = itinerary['legs'][0]  # Car route should have single leg
                        
                        # Decode the polyline string into coordinates
                        decoded_points = polyline.decode(leg['legGeometry']['points'])
                        
                        route_cache[cache_key] = {
                            'points': decoded_points,  # Store decoded points
                            'duration': leg['duration']
                        }
                    except Exception as e:
                        print(f"Error processing route: {e}")
                        continue
                    
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