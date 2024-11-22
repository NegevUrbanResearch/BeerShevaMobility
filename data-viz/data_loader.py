# Data loading and preprocessing functions
import pandas as pd
import geopandas as gpd
import os
import glob
from utils.zone_utils import (
    standardize_zone_ids,  # Keep for validation only
    analyze_zone_ids,
    get_zone_type
)
from config import (
    BASE_DIR, DATA_DIR, PROCESSED_DIR, OUTPUT_DIR,
    POI_FILE, FINAL_ZONES_FILE, FINAL_TRIPS_PATTERN,
    COLOR_SCHEME, CHART_COLORS
)
from utils.data_standards import DataStandardizer

class DataLoader:
    def __init__(self):
        self.zones_file = FINAL_ZONES_FILE  # Use final (already standardized) zones
        self.poi_file = POI_FILE
        self.trips_pattern = FINAL_TRIPS_PATTERN
        
        print(f"DataLoader initialized with:")
        print(f"Zones file: {self.zones_file}")
        print(f"POI file: {self.poi_file}")
        print(f"Trips pattern: {self.trips_pattern}")

    def load_zones(self):
        """Load preprocessed zone geometries"""
        print(f"\nAttempting to load zones from: {self.zones_file}")
        if not os.path.exists(self.zones_file):
            raise FileNotFoundError(f"Zones file not found at {self.zones_file}")
            
        zones = gpd.read_file(self.zones_file)
        
        # Validate but don't modify
        zone_analysis = analyze_zone_ids(zones, ['YISHUV_STAT11'])
        print("\nZone types in loaded data:")
        print(f"City zones: {zone_analysis['city']}")
        print(f"Statistical areas: {zone_analysis['statistical']}")
        print(f"Unknown/Invalid: {zone_analysis['unknown']}")
        
        return zones

    def load_poi_data(self):
        return pd.read_csv(self.poi_file)

    def load_trip_data(self):
        """Load preprocessed trip data"""
        print(f"\nLooking for trip files matching: {self.trips_pattern}")
        trip_files = glob.glob(self.trips_pattern)
        print(f"Found {len(trip_files)} trip files")
        
        trip_data = {}
        for file in trip_files:
            filename = os.path.basename(file)
            print(f"\nProcessing file: {filename}")
            
            # Extract standardized POI name and trip type from filename
            poi_name, trip_type = DataStandardizer.extract_poi_name_from_filename(filename)
            
            if not poi_name or not trip_type:
                print(f"Warning: Cannot parse filename: {filename}")
                continue
            
            df = pd.read_csv(file)
            print(f"Loaded trip data for {poi_name}:")
            print(f"Shape: {df.shape}")
            print(f"Columns: {df.columns.tolist()}")
            
            trip_data[(poi_name, trip_type)] = df
        
        return trip_data

    def clean_poi_names(self, poi_df, trip_data=None):
        """Clean and standardize POI names using the centralized DataStandardizer."""
        
        # Print current POI names
        print("\nCurrent POI names:")
        for name in poi_df['name'].values:
            print(f"- {name}")
        
        # Update names using the standardizer
        poi_df['name'] = poi_df['name'].apply(DataStandardizer.standardize_poi_name)
        
        # If trip_data is provided, update its keys
        if trip_data is not None:
            updated_trip_data = {}
            for (poi, trip_type), data in trip_data.items():
                standardized_poi = DataStandardizer.standardize_poi_name(poi)
                updated_trip_data[(standardized_poi, trip_type)] = data
            return poi_df, updated_trip_data
        
        return poi_df

def test_data_loader():
    """Test the data loader with verbose output"""
    loader = DataLoader()
    
    print("\nTesting load_zones():")
    zones = loader.load_zones()
    print(f"Loaded {len(zones)} zones")
    
    print("\nTesting load_poi_data():")
    poi_df = loader.load_poi_data()
    # Clean POI names
    poi_df = loader.clean_poi_names(poi_df)
    print(f"Loaded {len(poi_df)} POIs")
    
    print("\nTesting load_trip_data():")
    trip_data = loader.load_trip_data()
    # Clean POI names in trip data
    _, trip_data = loader.clean_poi_names(poi_df, trip_data)
    print(f"Loaded trip data for {len(trip_data)} POI-trip type combinations")
    
    return loader

if __name__ == "__main__":
    test_data_loader()