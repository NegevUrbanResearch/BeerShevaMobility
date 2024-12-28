import pandas as pd
import numpy as np
from pathlib import Path
import os
from utils.data_standards import DataStandardizer
from utils.zone_utils import get_zone_type
import logging

logger = logging.getLogger(__name__)

class MobilityPatternAnalyzer:
    def __init__(self):
        # Use project root directory structure
        self.project_root = Path(__file__).parent
        self.data_dir = self.project_root / "output" / "dashboard_data"
        self.stats_dir = self.project_root / "output" / "statistics"
        os.makedirs(self.stats_dir, exist_ok=True)
        self.standardizer = DataStandardizer()
        
        # Get list of standard POI names we want to analyze
        self.analysis_pois = [
            'Ben-Gurion-University',
            'Soroka-Medical-Center'
        ]
        
        # POI coordinates
        self.poi_locations = {
            'Ben-Gurion-University': {'lat': 31.262218, 'lon': 34.801472},
            'Soroka-Medical-Center': {'lat': 31.262650, 'lon': 34.799452}
        }

    def load_poi_data(self, poi_name: str, trip_type: str) -> pd.DataFrame:
        """Load data for a specific POI and trip type using standardized names"""
        # Get the file-format POI name (reverse lookup from standardized name)
        file_poi_name = None
        for key, value in self.standardizer.POI_NAME_MAPPING.items():
            if value == poi_name:
                file_poi_name = key
                break
        
        if not file_poi_name:
            file_poi_name = 'BGU' if poi_name == 'Ben-Gurion-University' else poi_name
        
        # Construct filename
        filename = f"{file_poi_name}_{trip_type}_trips.csv"
        file_path = self.data_dir / filename
        
        if not file_path.exists():
            # Try alternative filename format
            alt_filename = f"{poi_name.replace('-', '_')}_{trip_type}_trips.csv"
            alt_file_path = self.data_dir / alt_filename
            
            if not alt_file_path.exists():
                logger.error(f"Data file not found: {file_path} or {alt_file_path}")
                raise FileNotFoundError(f"No data file found for {poi_name} {trip_type} trips")
            file_path = alt_file_path

        try:
            df = pd.read_csv(file_path)
            # Standardize zone IDs if present
            if 'zone_id' in df.columns:
                df['zone_id'] = df['zone_id'].apply(self.standardizer.standardize_zone_id)
            return df
        except Exception as e:
            logger.error(f"Error loading data for {poi_name}: {str(e)}")
            raise

    def get_poi_location(self, poi_name: str) -> dict:
        """Get POI coordinates"""
        std_poi_name = self.standardizer.standardize_poi_name(poi_name)
        if std_poi_name not in self.poi_locations:
            raise ValueError(f"Location not defined for POI: {poi_name}")
        return self.poi_locations[std_poi_name]

    def analyze_temporal_patterns(self):
        """Analyze temporal patterns across POIs"""
        patterns = {}
        
        for poi in self.analysis_pois:
            for trip_type in ['inbound', 'outbound']:
                try:
                    df = self.load_poi_data(poi, trip_type)
                    
                    # Extract arrival time columns
                    time_cols = [col for col in df.columns if col.startswith('arrival_')]
                    
                    # Calculate average temporal distribution weighted by total trips
                    temporal_dist = (df[time_cols].multiply(df['total_trips'], axis=0).sum() / 
                                   df['total_trips'].sum())
                    
                    patterns[f"{poi}_{trip_type}"] = temporal_dist
                except FileNotFoundError as e:
                    logger.warning(f"Skipping {poi} {trip_type}: {str(e)}")
                    continue
        
        return patterns

    def analyze_mode_differences(self):
        """Compare transportation mode differences between POIs"""
        all_pois = [f.replace('_inbound_trips.csv', '') 
                   for f in os.listdir(self.output_dir) 
                   if f.endswith('_inbound_trips.csv')]
        
        mode_patterns = {}
        
        for poi in all_pois:
            for trip_type in ['inbound', 'outbound']:
                df = self.load_poi_data(poi, trip_type)
                
                # Get mode columns
                mode_cols = [col for col in df.columns if col.startswith('mode_')]
                
                # Calculate weighted average mode split
                mode_split = (df[mode_cols].multiply(df['total_trips'], axis=0).sum() / 
                            df['total_trips'].sum())
                
                mode_patterns[f"{poi}_{trip_type}"] = mode_split
        
        return mode_patterns

    def analyze_catchment_areas(self):
        """Analyze the geographical reach and key origin/destination patterns of different POIs"""
        catchment_patterns = {}
        
        for poi in ['Ben-Gurion-University', 'Soroka-Medical-Center']:
            for trip_type in ['inbound', 'outbound']:
                df = self.load_poi_data(poi, trip_type)
                
                # Sort zones by trip volume
                df_sorted = df.sort_values('total_trips', ascending=False)
                
                # Calculate cumulative percentage of trips
                df_sorted['cumulative_trips'] = df_sorted['total_trips'].cumsum()
                df_sorted['cumulative_percentage'] = (df_sorted['cumulative_trips'] / 
                                                    df_sorted['total_trips'].sum()) * 100
                
                # Find zones that make up different percentage thresholds
                thresholds = {
                    '50%': df_sorted[df_sorted['cumulative_percentage'] <= 50],
                    '75%': df_sorted[df_sorted['cumulative_percentage'] <= 75],
                    '90%': df_sorted[df_sorted['cumulative_percentage'] <= 90]
                }
                
                # Calculate key metrics
                catchment_patterns[f"{poi}_{trip_type}"] = {
                    'total_trips': df['total_trips'].sum(),
                    'active_zones': len(df[df['total_trips'] > 0]),
                    'zones_50_percent': len(thresholds['50%']),
                    'zones_75_percent': len(thresholds['75%']),
                    'zones_90_percent': len(thresholds['90%']),
                    'top_5_concentration': (df_sorted['total_trips'].head(5).sum() / 
                                          df_sorted['total_trips'].sum()) * 100,
                    'top_10_concentration': (df_sorted['total_trips'].head(10).sum() / 
                                           df_sorted['total_trips'].sum()) * 100,
                    'top_zones': df_sorted.head(10)[['zone_id', 'total_trips']].to_dict('records'),
                    'average_trip_distance': df['distance'].mean() if 'distance' in df.columns else None,
                    'median_trip_distance': df['distance'].median() if 'distance' in df.columns else None
                }
                
                # Regional analysis (if coordinates are available)
                if 'zone_lat' in df.columns and 'zone_lon' in df.columns:
                    # Calculate distance-based metrics
                    poi_location = self.get_poi_location(poi)  # You'll need to implement this
                    df['distance_to_poi'] = df.apply(
                        lambda row: self.calculate_distance(
                            row['zone_lat'], row['zone_lon'], 
                            poi_location['lat'], poi_location['lon']
                        ), axis=1
                    )
                    
                    # Find radius containing 90% of trips
                    df_dist_sorted = df.sort_values('distance_to_poi')
                    df_dist_sorted['cumulative_trips'] = df_dist_sorted['total_trips'].cumsum()
                    df_dist_sorted['cumulative_percentage'] = (df_dist_sorted['cumulative_trips'] / 
                                                             df_dist_sorted['total_trips'].sum()) * 100
                    radius_90 = df_dist_sorted[df_dist_sorted['cumulative_percentage'] <= 90]['distance_to_poi'].max()
                    
                    catchment_patterns[f"{poi}_{trip_type}"].update({
                        'radius_90_percent': radius_90,
                        'direction_analysis': self.analyze_directional_patterns(df, poi_location)
                    })
        
        return catchment_patterns

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate the Haversine distance between two points"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth's radius in kilometers
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        
        return distance

    def analyze_directional_patterns(self, df, poi_location):
        """Analyze the directional distribution of trips"""
        from math import degrees, atan2
        
        df = df.copy()
        
        # Calculate bearing from POI to each zone
        df['bearing'] = df.apply(
            lambda row: degrees(atan2(
                row['zone_lon'] - poi_location['lon'],
                row['zone_lat'] - poi_location['lat']
            )) % 360, axis=1
        )
        
        # Define direction sectors
        sectors = {
            'North': (315, 45),
            'East': (45, 135),
            'South': (135, 225),
            'West': (225, 315)
        }
        
        # Calculate trips by direction
        direction_patterns = {}
        for direction, (start, end) in sectors.items():
            if start < end:
                mask = (df['bearing'] >= start) & (df['bearing'] < end)
            else:
                mask = (df['bearing'] >= start) | (df['bearing'] < end)
            
            direction_patterns[direction] = {
                'total_trips': df[mask]['total_trips'].sum(),
                'percentage': (df[mask]['total_trips'].sum() / df['total_trips'].sum()) * 100,
                'top_zones': df[mask].nlargest(3, 'total_trips')[['zone_id', 'total_trips']].to_dict('records')
            }
        
        return direction_patterns

    def analyze_purpose_patterns(self):
        """Analyze trip purpose patterns"""
        purpose_patterns = {}
        
        for poi in ['Ben-Gurion-University', 'Soroka-Medical-Center']:
            for trip_type in ['inbound', 'outbound']:
                df = self.load_poi_data(poi, trip_type)
                
                # Get purpose columns
                purpose_cols = [col for col in df.columns if col.startswith('purpose_')]
                
                # Calculate weighted average purpose split
                purpose_split = (df[purpose_cols].multiply(df['total_trips'], axis=0).sum() / 
                               df['total_trips'].sum())
                
                purpose_patterns[f"{poi}_{trip_type}"] = purpose_split
        
        return purpose_patterns

    def generate_insights_report(self):
        """Generate a report of key insights"""
        temporal = self.analyze_temporal_patterns()
        modes = self.analyze_mode_differences()
        catchment = self.analyze_catchment_areas()
        purposes = self.analyze_purpose_patterns()
        
        print("=== Mobility Pattern Analysis Report ===\n")
        
        print("1. Peak Hour Comparison")
        print("--------------------------")
        for poi_pattern in temporal.items():
            peak_hour = pd.Series(poi_pattern[1]).idxmax()
            peak_percentage = poi_pattern[1].max()
            print(f"{poi_pattern[0]}:")
            print(f"  Peak hour: {peak_hour}")
            print(f"  Peak percentage: {peak_percentage:.1f}%\n")
        
        print("\n2. Mode Share Insights")
        print("----------------------")
        for poi in ['Ben-Gurion-University', 'Soroka-Medical-Center']:
            inbound = modes[f"{poi}_inbound"]
            print(f"{poi}:")
            print("  Top 3 modes (inbound):")
            for mode, share in inbound.nlargest(3).items():
                print(f"    - {mode.replace('mode_', '')}: {share:.1f}%")
            print()
        
        print("\n3. Catchment Area Analysis")
        print("-------------------------")
        for poi_data in catchment.items():
            print(f"\n{poi_data[0]}:")
            data = poi_data[1]
            print(f"  Total trips: {data['total_trips']:,}")
            print(f"  Active zones: {data['active_zones']}")
            print(f"  Concentration metrics:")
            print(f"    - Zones for 50% of trips: {data['zones_50_percent']}")
            print(f"    - Zones for 75% of trips: {data['zones_75_percent']}")
            print(f"    - Zones for 90% of trips: {data['zones_90_percent']}")
            print(f"    - Top 5 zones concentration: {data['top_5_concentration']:.1f}%")
            print(f"    - Top 10 zones concentration: {data['top_10_concentration']:.1f}%")
            
            if 'radius_90_percent' in data:
                print(f"\n  Spatial coverage:")
                print(f"    - 90% of trips within: {data['radius_90_percent']:.1f} km")
                
                print("\n  Directional patterns:")
                for direction, dir_data in data['direction_analysis'].items():
                    print(f"    - {direction}: {dir_data['percentage']:.1f}% of trips")
                    if dir_data['percentage'] > 15:  # Only show significant corridors
                        print(f"      Key zones: {', '.join(str(z['zone_id']) for z in dir_data['top_zones'])}")
            
            print("\n  Top 5 origin/destination zones:")
            for zone in data['top_zones'][:5]:
                print(f"    - Zone {zone['zone_id']}: {zone['total_trips']:,} trips")
        
        print("\n4. Trip Purpose Distribution")
        print("---------------------------")
        for poi_purpose in purposes.items():
            print(f"{poi_purpose[0]}:")
            for purpose, percentage in poi_purpose[1].nlargest(3).items():
                print(f"  - {purpose.replace('purpose_', '')}: {percentage:.1f}%")
            print()

    def generate_poi_statistics(self):
        """Generate comprehensive statistics for each POI"""
        stats = {}
        
        for poi in self.analysis_pois:
            stats[poi] = {
                'inbound': self.analyze_poi_trips(poi, 'inbound'),
                'outbound': self.analyze_poi_trips(poi, 'outbound')
            }
            
            # Save individual POI statistics
            poi_stats_file = self.stats_dir / f"{poi.lower().replace('-', '_')}_statistics.csv"
            pd.DataFrame(stats[poi]).to_csv(poi_stats_file)
        
        # Save summary statistics
        summary_stats = pd.DataFrame.from_dict(
            {(i,j): stats[i][j] 
             for i in stats.keys() 
             for j in stats[i].keys()},
            orient='index'
        )
        summary_stats.to_csv(self.stats_dir / "poi_summary_statistics.csv")
        
        return stats

    def analyze_poi_trips(self, poi_name: str, trip_type: str) -> dict:
        """Analyze trips for a specific POI and direction"""
        try:
            df = self.load_poi_data(poi_name, trip_type)
            
            # Debug prints
            print(f"\nAnalyzing {poi_name} - {trip_type}")
            print("Available columns:", df.columns.tolist())
            print("\nSample data:")
            print(df.head(2))
            
            # Basic trip statistics
            stats = {
                'total_trips': df['total_trips'].sum(),
                'unique_zones': len(df),
                'active_zones': len(df[df['total_trips'] > 0])
            }
            
            # Debug print for zone identification columns
            zone_cols = [col for col in df.columns if 'zone' in col.lower() or 'tract' in col.lower()]
            print("\nPossible zone columns:", zone_cols)
            
            # Distance statistics (if available)
            if 'distance' in df.columns:
                print("\nDistance column found")
                distance_stats = df.assign(
                    weighted_distance=df['distance'] * df['total_trips']
                ).agg({
                    'weighted_distance': lambda x: x.sum() / df['total_trips'].sum(),
                    'distance': ['min', 'max', 'median']
                })
                stats.update({
                    'avg_distance_km': distance_stats['weighted_distance'],
                    'min_distance_km': distance_stats['distance']['min'],
                    'max_distance_km': distance_stats['distance']['max'],
                    'median_distance_km': distance_stats['distance']['median']
                })
            
            # Temporal patterns
            time_cols = [col for col in df.columns if col.startswith('arrival_')]
            print("\nTemporal columns:", time_cols)
            
            if time_cols:
                temporal_dist = df[time_cols].multiply(df['total_trips'], axis=0).sum() / df['total_trips'].sum()
                stats['peak_hour'] = temporal_dist.idxmax().replace('arrival_', '')
                stats['peak_hour_percentage'] = temporal_dist.max()
            
            # Mode split
            mode_cols = [col for col in df.columns if col.startswith('mode_')]
            print("\nMode columns:", mode_cols)
            
            if mode_cols:
                mode_split = df[mode_cols].multiply(df['total_trips'], axis=0).sum() / df['total_trips'].sum()
                stats['primary_mode'] = mode_split.idxmax().replace('mode_', '')
                stats['primary_mode_percentage'] = mode_split.max()
                stats['mode_split'] = mode_split.to_dict()
            
            # Purpose split
            purpose_cols = [col for col in df.columns if col.startswith('purpose_')]
            print("\nPurpose columns:", purpose_cols)
            
            if purpose_cols:
                purpose_split = df[purpose_cols].multiply(df['total_trips'], axis=0).sum() / df['total_trips'].sum()
                stats['primary_purpose'] = purpose_split.idxmax().replace('purpose_', '')
                stats['primary_purpose_percentage'] = purpose_split.max()
                stats['purpose_split'] = purpose_split.to_dict()
            
            # Find the correct zone identifier column
            zone_id_col = next((col for col in ['zone_id', 'tract', 'zone'] if col in df.columns), None)
            print(f"\nUsing zone identifier column: {zone_id_col}")
            
            if zone_id_col:
                # Top zones
                top_zones = df.nlargest(5, 'total_trips')[[zone_id_col, 'total_trips']].to_dict('records')
                stats['top_5_zones'] = top_zones
                stats['top_5_concentration'] = sum(z['total_trips'] for z in top_zones) / df['total_trips'].sum() * 100
            else:
                print("WARNING: No zone identifier column found!")
                stats['top_5_zones'] = []
                stats['top_5_concentration'] = 0
            
            return stats
            
        except FileNotFoundError:
            logger.warning(f"No data found for {poi_name} {trip_type}")
            return {}
        except Exception as e:
            logger.error(f"Error analyzing {poi_name} {trip_type}: {str(e)}")
            logger.error("Stack trace:", exc_info=True)
            return {}

if __name__ == "__main__":
    analyzer = MobilityPatternAnalyzer()
    
    # Generate statistics
    stats = analyzer.generate_poi_statistics()
    print("\nStatistics generated and saved to:", analyzer.stats_dir)
    
    # Generate insights report
    analyzer.generate_insights_report() 