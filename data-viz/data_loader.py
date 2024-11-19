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
        self.poi_file = os.path.join(self.base_dir, "data", "poi_with_exact_coordinates.csv")

    def load_zones(self):
        """Load both statistical zones and cities from their respective GeoJSON files"""
        # Load both statistical zones and city zones
        stat_zones = gpd.read_file(os.path.join(self.output_dir, "statistical_zones.geojson"))
        city_zones = gpd.read_file(os.path.join(self.output_dir, "city_zones.geojson"))
        
        # Rename city_id to YISHUV_STAT11 to match statistical zones format
        city_zones = city_zones.rename(columns={'city_id': 'YISHUV_STAT11'})
        
        # Combine the datasets
        zones = pd.concat([stat_zones, city_zones], ignore_index=True)
        
        # Ensure YISHUV_STAT11 is string type
        zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].astype(str)
        
        return zones

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

    def clean_poi_names(self, poi_df, trip_data=None):
        """Clean and standardize POI names in the dataset and update trip_data keys if provided."""
        name_corrections = {
            'Emek Shara industrial area': 'Emek Sara Industrial Area',
            'BGU': 'Ben-Gurion University',
            'Soroka Hospital': 'Soroka Medical Center',
            'Gev Yam': 'Gav-Yam High-Tech Park',
            'K collage': 'Kaye College',
            'Omer industrial area': 'Omer Industrial Area',
            'Sami Shimon collage': 'SCE',
            'Ramat Hovav Industry': 'Ramat Hovav Industrial Zone'
        }
        
        # Print current POI names
        print("\nCurrent POI names:")
        for name in poi_df['name'].values:
            print(f"- {name}")
        
        # Update names using the corrections dictionary
        poi_df['name'] = poi_df['name'].replace(name_corrections)
        
        # If trip_data is provided, update its keys
        if trip_data is not None:
            updated_trip_data = {}
            for (poi, trip_type), data in trip_data.items():
                new_poi = name_corrections.get(poi, poi)
                updated_trip_data[(new_poi, trip_type)] = data
            return poi_df, updated_trip_data
        
        return poi_df

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