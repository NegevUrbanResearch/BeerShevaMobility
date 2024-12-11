# walking_route_modeler.py

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

# Add these imports at the top
import sys
# Add parent directory to Python path to access data_loader
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader

entrances_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                    "data/filtered-entrances/filtered_entrances.shp")

class RouteSegmentManager:
    def __init__(self, joining_threshold=10):  # threshold in meters
        self.segments = []  # List of LineStrings
        self.segment_data = []  # Metadata for each segment
        self.spatial_index = index.Index()
        self.joining_threshold = joining_threshold
        
    def _coord_to_meters(self, lat1, lon1, lat2, lon2):
        """Calculate distance between points in meters"""
        R = 6371000
        dlat = np.radians(lat2 - lat1)
        dlon = np.radians(lon2 - lon1)
        a = (np.sin(dlat/2) * np.sin(dlat/2) +
             np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) *
             np.sin(dlon/2) * np.sin(dlon/2))
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        return R * c

    def _find_joining_point(self, route_points, existing_segment):
        """Find where a new route joins an existing segment"""
        min_dist = float('inf')
        join_idx = None
        segment_idx = None
        
        line = LineString(existing_segment)
        
        for i, point in enumerate(route_points):
            # Project point onto line
            proj_point = line.interpolate(line.project(Point(point)))
            dist = self._coord_to_meters(
                point[1], point[0],
                proj_point.y, proj_point.x
            )
            
            if dist < min_dist and dist <= self.joining_threshold:
                min_dist = dist
                join_idx = i
                segment_idx = int(line.project(Point(point)) / line.length * (len(existing_segment) - 1))
        
        return join_idx, segment_idx if min_dist <= self.joining_threshold else (None, None)

    def add_route(self, points, metadata):
        """Add a new route, joining with existing segments where possible"""
        route_coords = [(lon, lat) for lat, lon in points]
        
        # Check for existing segments to join with
        best_join = None
        best_segment_idx = None
        best_existing_idx = None
        
        # Create bounds for spatial indexing
        bounds = LineString(route_coords).bounds
        
        # Query spatial index for potential matches
        potential_matches = list(self.spatial_index.intersection(bounds))
        
        for idx in potential_matches:
            existing_segment = self.segments[idx]
            join_idx, segment_idx = self._find_joining_point(route_coords, existing_segment)
            
            if join_idx is not None:
                best_join = join_idx
                best_segment_idx = segment_idx
                best_existing_idx = idx
                break
        
        if best_join is not None:
            # Join routes
            new_route = route_coords[:best_join + 1]
            existing_segment = self.segments[best_existing_idx]
            joined_route = new_route + existing_segment[best_segment_idx:]
            
            # Update metadata
            combined_metadata = {
                'trips': metadata['trips'] + self.segment_data[best_existing_idx]['trips'],
                'origins': metadata.get('origins', []) + self.segment_data[best_existing_idx].get('origins', []),
                'entrance': metadata['entrance']
            }
            
            # Add joined route as new segment
            self._add_segment(joined_route, combined_metadata)
        else:
            # Add as new independent segment
            self._add_segment(route_coords, {
                'trips': metadata['trips'],
                'origins': [metadata.get('origin')],
                'entrance': metadata['entrance']
            })

    def _add_segment(self, coords, metadata):
        """Add a new segment to the collection"""
        idx = len(self.segments)
        self.segments.append(coords)
        self.segment_data.append(metadata)
        
        # Add to spatial index
        line = LineString(coords)
        self.spatial_index.insert(idx, line.bounds)

    def get_all_segments(self):
        """Get all route segments with their metadata"""
        return list(zip(self.segments, self.segment_data))

class OTPClient:
    def __init__(self, base_url="http://localhost:8080/otp/routers/default"):
        self.base_url = base_url
        self.route_cache = {}  # (origin_x, origin_y) -> route_data
        self.segment_manager = RouteSegmentManager(joining_threshold=10)
        
    def get_walking_route(self, from_lat, from_lon, to_lat, to_lon, metadata=None):
        """Get walking route, using cache and joining similar routes"""
        # Check cache first
        cache_key = (round(from_lon, 5), round(from_lat, 5))
        if cache_key in self.route_cache:
            return self.route_cache[cache_key]
        
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
                
                if 'plan' in data and data['plan']['itineraries']:
                    itinerary = data['plan']['itineraries'][0]
                    leg = itinerary['legs'][0]
                    points = polyline.decode(leg['legGeometry']['points'])
                    
                    if metadata:
                        self.segment_manager.add_route(points, metadata)
                    
                    self.route_cache[cache_key] = data
                    return data
                    
            return None
        except Exception as e:
            print(f"Error getting route: {e}")
            return None

class RouteModeler:
    def __init__(self):
        self.target_pois = ['Ben-Gurion-University', 'Soroka-Medical-Center']
        self.otp_client = OTPClient()
        self.load_data()
    # Update the load_data method in the RouteModeler class:
    def load_data(self):
        """Load and process required data"""
        loader = DataLoader()
        
        self.zones = loader.load_zones()
        if self.zones.crs != "EPSG:4326":
            self.zones = self.zones.to_crs("EPSG:4326")
            
        self.poi_df = loader.load_poi_data()
        self.trip_data = loader.load_trip_data()
        
        # Load entrances
        self.entrances = gpd.read_file(entrances_path)
        if self.entrances.crs != "EPSG:4326":
            self.entrances = self.entrances.to_crs("EPSG:4326")
        
        # Process trip data like in the original
        self.processed_trips = {}
        self.poi_df, self.trip_data = loader.clean_poi_names(self.poi_df, self.trip_data)
            
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
                self.processed_trips[poi_name] = df_with_peds
                print(f"\nProcessed {poi_name}:")
                print(f"Total pedestrian trips: {ped_trips.sum():.1f}")
                print(f"Zones with pedestrian trips: {len(df_with_peds)}")
        
    def process_trip_data(self):
        """Process trip data for pedestrian trips"""
        self.processed_trips = {}
        
        for poi_name in self.target_pois:
            df = self.trip_data[self.trip_data['destination'] == poi_name].copy()
            if 'total_trips' in df.columns and 'mode_ped' in df.columns:
                df['ped_trips'] = df['total_trips'] * (df['mode_ped'] / 100)
                df = df[df['ped_trips'] > 0]
                
                if len(df) > 0:
                    self.processed_trips[poi_name] = df
                    print(f"\nProcessed {poi_name}:")
                    print(f"Total pedestrian trips: {df['ped_trips'].sum():.1f}")
                    print(f"Zones with pedestrian trips: {len(df)}")
    
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
    
    def find_closest_entrance(self, point, entrances):
        """Find the closest entrance"""
        min_dist = float('inf')
        closest = None
        
        for _, entrance in entrances.iterrows():
            dist = point.distance(entrance.geometry)
            if dist < min_dist:
                min_dist = dist
                closest = entrance
                
        return closest
    
    def process_all_routes(self):
        """Process walking routes for all POIs"""
        all_segments = []
        
        for poi_name in self.target_pois:
            if poi_name not in self.processed_trips:
                continue
                
            print(f"\nProcessing routes for {poi_name}")
            trip_df = self.processed_trips[poi_name]
            
            # Get entrances for this POI
            poi_prefix = 'Hospital' if 'Soroka' in poi_name else 'Uni'
            entrances = self.entrances[self.entrances['Name'].str.startswith(poi_prefix)]
            
            if len(entrances) == 0:
                print(f"No entrances found for {poi_name}")
                continue
                
            print(f"Found {len(entrances)} entrances")
            
            # Process each zone
            for _, zone_data in tqdm(trip_df.iterrows(), total=len(trip_df)):
                zone_id = zone_data['tract']
                num_trips = int(round(zone_data['ped_trips']))
                
                if num_trips < 1:
                    continue
                    
                zone = self.zones[self.zones['YISHUV_STAT11'] == zone_id]
                if len(zone) == 0:
                    continue
                
                zone_geometry = zone.geometry.iloc[0]
                random_points = self.generate_random_points(zone_geometry, num_points=50)
                
                for point in random_points:
                    closest_entrance = self.find_closest_entrance(point, entrances)
                    
                    if closest_entrance is not None:
                        metadata = {
                            'trips': num_trips / len(random_points),
                            'origin': point,
                            'entrance': closest_entrance['Name']
                        }
                        
                        route_data = self.otp_client.get_walking_route(
                            point.y, point.x,
                            closest_entrance.geometry.y,
                            closest_entrance.geometry.x,
                            metadata=metadata
                        )
                        
                        time.sleep(0.1)  # Rate limiting
        
        # Get all segments and create GeoDataFrame
        segments = self.otp_client.segment_manager.get_all_segments()
        
        if segments:
            gdf_data = []
            for segment_coords, metadata in segments:
                gdf_data.append({
                    'geometry': LineString(segment_coords),
                    'trips': metadata['trips'],
                    'entrance': metadata['entrance'],
                    'num_origins': len(metadata['origins'])
                })
            
            segments_gdf = gpd.GeoDataFrame(gdf_data, crs="EPSG:4326")
            return segments_gdf
        else:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

if __name__ == "__main__":
    modeler = RouteModeler()
    walking_segments = modeler.process_all_routes()
    
    if not walking_segments.empty:
        output_file = "walking_segments.geojson"
        walking_segments.to_file(output_file, driver="GeoJSON")
        print(f"\nSaved {len(walking_segments)} walking segments to: {output_file}")
    else:
        print("\nNo walking segments were generated!")