# Data loading and preprocessing functions
import pandas as pd
import geopandas as gpd
import os
from config import BASE_DIR, OUTPUT_DIR, COLOR_SCHEME, CHART_COLORS

class DataLoader:
    def __init__(self, base_dir, output_dir):
        self.base_dir = base_dir
        self.output_dir = output_dir
        self.zones_file = os.path.join(self.output_dir, "zones.geojson")
        self.poi_file = os.path.join(self.output_dir, "poi_with_exact_coordinates.csv")

    def load_zones(self):
        return gpd.read_file(self.zones_file)

    def load_poi_data(self):
        return pd.read_csv(self.poi_file)

    def load_trip_data(self):
        trip_data = {}
        poi_df = self.load_poi_data()
        for poi_name in poi_df['name']:
            for trip_type in ['inbound', 'outbound']:
                file_name = f"{poi_name.replace(' ', '_')}_{trip_type}_trips.csv"
                file_path = os.path.join(self.output_dir, file_name)
                if os.path.exists(file_path):
                    df = pd.read_csv(file_path)
                    df['tract'] = df['tract'].astype(str).str.zfill(6)
                    trip_data[(poi_name, trip_type)] = df
        return trip_data

def test_data_loader():
    loader = DataLoader(BASE_DIR, OUTPUT_DIR)
    
    print("Testing load_zones():")
    zones = loader.load_zones()
    print(f"Loaded {len(zones)} zones")
    
    print("\nTesting load_poi_data():")
    poi_df = loader.load_poi_data()
    print(f"Loaded {len(poi_df)} POIs")
    
    print("\nTesting load_trip_data():")
    trip_data = loader.load_trip_data()
    print(f"Loaded trip data for {len(trip_data)} POI-trip type combinations")
    
    return loader

if __name__ == "__main__":
    test_data_loader()
