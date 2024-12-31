import pandas as pd
import geopandas as gpd
import numpy as np
import json
from pathlib import Path
import geopy.distance
from typing import Dict, List, Tuple

class TripDistanceAnalyzer:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.data_dir = self.project_root / "output" / "dashboard_data"
        self.output_dir = self.project_root / "output" / "distance_histograms"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load zones data first
        self.zones_file = self.project_root / "output" / "dashboard_data" / "zones.geojson"
        print(f"\nLoading zones from: {self.zones_file}")
        self.zones = self.load_zones()
        
        # Define POIs
        self.focus_pois = {
            'BGU': {'lat': 31.262218, 'lon': 34.801472},
            'Soroka_Hospital': {'lat': 31.262650, 'lon': 34.799452},
            'Gev_Yam': {'lat': 31.263500, 'lon': 34.803500}
        }
        
        # Define distance ranges for each mode
        self.distance_ranges = {
            'walk': [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, float('inf'))],
            'bike': [(0, 1), (1, 2), (2, 3), (3, 5), (5, float('inf'))],
            'car': [(0, 10), (10, 25), (25, 50), (50, 75), (75, float('inf'))],
            'transit': [(0, 10), (10, 25), (25, 50), (50, 75), (75, float('inf'))]
        }

    def load_zones(self):
        """Load and prepare zones data"""
        zones = gpd.read_file(self.zones_file)
        zones['centroid_itm'] = zones.geometry.centroid
        zones['centroid_lon'] = zones['centroid_itm'].to_crs(epsg=4326).x
        zones['centroid_lat'] = zones['centroid_itm'].to_crs(epsg=4326).y
        print(f"Loaded {len(zones)} zones with columns:", zones.columns.tolist())
        return zones

    def load_poi_data(self, poi_name: str) -> pd.DataFrame:
        """Load and prepare POI data"""
        try:
            # Load data
            print(f"\nLoading data for {poi_name}")
            df = pd.read_csv(self.data_dir / f"{poi_name}_inbound_trips.csv")
            print(f"Original data shape: {df.shape}")
            
            # Add sample data prints
            print("\nSample of raw data:")
            print(df[['tract', 'total_trips'] + [col for col in df.columns if col.startswith('mode_')]].head())
            
            # Merge with zones to get centroids
            df = df.merge(
                self.zones[['YISHUV_STAT11', 'centroid_lon', 'centroid_lat']], 
                left_on='tract',
                right_on='YISHUV_STAT11',
                how='left'
            )
            print(f"Data shape after merge: {df.shape}")
            
            # Calculate distances first
            poi_coords = self.focus_pois[poi_name]
            df['distance'] = df.apply(
                lambda row: geopy.distance.geodesic(
                    (poi_coords['lat'], poi_coords['lon']),
                    (row['centroid_lat'], row['centroid_lon'])
                ).kilometers if pd.notna(row['centroid_lat']) else np.nan,
                axis=1
            )
            
            # Handle mode columns
            print("\nProcessing mode columns...")
            if 'mode_ped' in df.columns:
                df['mode_walk'] = df['mode_ped']
                df = df.drop('mode_ped', axis=1)
                print("Mapped pedestrian mode to walk")
            
            # Combine transit modes
            transit_cols = ['mode_bus', 'mode_link', 'mode_train']
            df['mode_transit'] = df[transit_cols].sum(axis=1)
            print("Combined transit modes")
            
            # Verify mode columns
            expected_modes = ['mode_car', 'mode_transit', 'mode_walk', 'mode_bike']
            for mode in expected_modes:
                if mode not in df.columns:
                    print(f"WARNING: Missing {mode} column")
            
            # Add mode verification prints
            mode_cols = [col for col in df.columns if col.startswith('mode_')]
            print("\nMode columns statistics:")
            print(df[mode_cols].describe())
            
            return df
            
        except Exception as e:
            print(f"Error loading data for {poi_name}: {str(e)}")
            return None

    def calculate_distance_distribution(self, df: pd.DataFrame, mode: str) -> List[Dict]:
        """Calculate trip distribution across distance ranges for a mode"""
        mode_col = f'mode_{mode}'
        print(f"\nCalculating distribution for {mode} mode")
        
        # Debug prints for mode column
        print(f"\nMode column '{mode_col}' statistics:")
        print(df[mode_col].describe())
        print("\nSample of calculations:")
        sample_rows = df.head(3)
        print(f"First 3 rows:")
        print(f"Mode values: {sample_rows[mode_col].tolist()}")
        print(f"Total trips: {sample_rows['total_trips'].tolist()}")
        print(f"Calculated trips: {(sample_rows[mode_col] * sample_rows['total_trips']).tolist()}")
        
        # IMPORTANT: The mode columns might be proportions/probabilities
        # We should not multiply by total_trips if the mode columns already represent actual trips
        # Let's check if mode columns sum to approximately 1 for each row
        mode_cols = [col for col in df.columns if col.startswith('mode_')]
        row_sums = df[mode_cols].sum(axis=1)
        print("\nMode columns row sums statistics:")
        print(row_sums.describe())
        
        # If row sums are close to 1, we should multiply by total_trips
        # If row sums are similar to total_trips, we should use the mode column directly
        use_multiplication = row_sums.mean() < 2  # Arbitrary threshold
        
        # Calculate trips for this mode
        if use_multiplication:
            mode_trips = df[mode_col] * df['total_trips']
            print("\nUsing multiplication with total_trips (mode values are proportions)")
        else:
            mode_trips = df[mode_col]
            print("\nUsing mode values directly (mode values are trip counts)")
        
        # Calculate trips for each distance range
        ranges = self.distance_ranges[mode]
        distribution = []
        
        total_trips = 0  # For verification
        for start, end in ranges:
            mask = (df['distance'] >= start)
            if end != float('inf'):
                mask &= (df['distance'] < end)
            
            # Sum the trips directly from the pre-calculated mode trips
            trips = mode_trips[mask].sum()
            total_trips += trips
            
            range_label = f"{start}-{end}" if end != float('inf') else f">{start}"
            distribution.append({
                'range': range_label,
                'trips': float(trips)  # Convert to float for JSON serialization
            })
            print(f"Range {range_label}km: {trips:.0f} trips")
        
        print(f"Total trips for {mode}: {total_trips:.0f}")
        return distribution

    def generate_distance_distributions(self):
        """Generate distance distribution data for all POIs and modes"""
        modes = ['walk', 'bike', 'car', 'transit']
        
        for poi_name in self.focus_pois:
            print(f"\nAnalyzing distance distributions for {poi_name}")
            
            # Load POI data
            df = self.load_poi_data(poi_name)
            if df is None:
                continue
                
            # Calculate distributions for each mode
            distributions = {}
            for mode in modes:
                print(f"Processing {mode} mode...")
                distributions[mode] = self.calculate_distance_distribution(df, mode)
            
            # Save the data
            output_file = self.output_dir / f"{poi_name.lower()}_distance_dist.json"
            with open(output_file, 'w') as f:
                json.dump(distributions, f)
            
            print(f"Saved distance distributions to {output_file}")

if __name__ == "__main__":
    analyzer = TripDistanceAnalyzer()
    analyzer.generate_distance_distributions()