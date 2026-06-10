import glob
import os

import geopandas as gpd
import pandas as pd

from mobility.config import (
    CHART_COLORS,
    COLOR_SCHEME,
    FINAL_TRIPS_PATTERN,
    FINAL_ZONES_FILE,
    POI_FILE,
)
from mobility.utils.data_standards import DataStandardizer
from mobility.utils.zone_utils import analyze_zone_ids, get_zone_type, standardize_zone_ids

class DataLoader:
    def __init__(self):
        self.zones_file = FINAL_ZONES_FILE
        self.poi_file = POI_FILE
        self.trips_pattern = FINAL_TRIPS_PATTERN

        print("DataLoader initialized with:")
        print(f"Zones file: {self.zones_file}")
        print(f"POI file: {self.poi_file}")
        print(f"Trips pattern: {self.trips_pattern}")

    def load_zones(self):
        print(f"\nAttempting to load zones from: {self.zones_file}")
        if not os.path.exists(self.zones_file):
            raise FileNotFoundError(f"Zones file not found at {self.zones_file}")

        zones = gpd.read_file(self.zones_file)
        zone_analysis = analyze_zone_ids(zones, ["YISHUV_STAT11"])
        print("\nZone types in loaded data:")
        print(f"City zones: {zone_analysis['city']}")
        print(f"Statistical areas: {zone_analysis['statistical']}")
        print(f"Unknown/Invalid: {zone_analysis['unknown']}")
        return zones

    def load_poi_data(self):
        return pd.read_csv(self.poi_file)

    def load_trip_data(self):
        print(f"\nLooking for trip files matching: {self.trips_pattern}")
        trip_files = glob.glob(self.trips_pattern)
        print(f"Found {len(trip_files)} trip files")

        trip_data = {}
        for file in trip_files:
            filename = os.path.basename(file)
            print(f"\nProcessing file: {filename}")

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
        print("\nCurrent POI names:")
        for name in poi_df["name"].values:
            print(f"- {name}")

        poi_df["name"] = poi_df["name"].apply(DataStandardizer.standardize_poi_name)

        if trip_data is not None:
            updated_trip_data = {}
            for (poi, trip_type), data in trip_data.items():
                standardized_poi = DataStandardizer.standardize_poi_name(poi)
                updated_trip_data[(standardized_poi, trip_type)] = data
            return poi_df, updated_trip_data

        return poi_df

def test_data_loader():
    loader = DataLoader()
    loader.load_zones()
    poi_df = loader.load_poi_data()
    poi_df = loader.clean_poi_names(poi_df)
    trip_data = loader.load_trip_data()
    _, trip_data = loader.clean_poi_names(poi_df, trip_data)
    print(f"Loaded trip data for {len(trip_data)} POI-trip type combinations")
    return loader

if __name__ == "__main__":
    test_data_loader()
