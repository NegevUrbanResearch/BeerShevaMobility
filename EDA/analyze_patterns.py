import pandas as pd
import numpy as np
from pathlib import Path
import os
from utils.data_standards import DataStandardizer
from utils.zone_utils import get_zone_type
import logging
import json

logger = logging.getLogger(__name__)

class MobilityPatternAnalyzer:
    def __init__(self):
        # Use project root directory structure
        self.project_root = Path(__file__).parent
        self.data_dir = self.project_root / "output" / "dashboard_data"
        self.stats_dir = self.project_root / "output" / "statistics"
        self.output_dir = self.data_dir
        os.makedirs(self.stats_dir, exist_ok=True)
        self.standardizer = DataStandardizer()

        # Get list of standard POI names we want to analyze
        self.analysis_pois = [
            'Ben-Gurion-University',
            'Soroka-Medical-Center',
            'Emek-Sara-Industrial-Area',
            'Omer-Industrial-Area',
            'HaNegev-Mall',
            'BIG',
            'Assuta-Hospital',
            'Gav-Yam-High-Tech-Park',
            'Ramat-Hovav-Industrial-Zone',
            'SCE',
            'Grand-Kenyon'
        ]
        
        # POI coordinates
        self.poi_locations = {
            'Ben-Gurion-University': {'lat': 31.262218, 'lon': 34.801472},
            'Soroka-Medical-Center': {'lat': 31.262650, 'lon': 34.799452}
        }

    def load_poi_data(self, poi_name: str, trip_type: str) -> pd.DataFrame:
        """Load data for a specific POI and trip type using the standardizer"""
        # Get the original name that maps to this standardized POI name
        original_name = None
        for key, value in self.standardizer.POI_NAME_MAPPING.items():
            if value == poi_name:
                original_name = key
                break
        
        if original_name is None:
            logger.warning(f"No original name found for standardized POI: {poi_name}")
            original_name = poi_name
        
        # Convert spaces to underscores for filename
        file_name = original_name.replace(' ', '_')
        filename = f"{file_name}_{trip_type}_trips.csv"
        file_path = self.data_dir / filename
        
        print(f"\nTrying to load data for {poi_name} ({trip_type})")
        print(f"Using filename: {filename}")
        
        if file_path.exists():
            print(f"Found file: {file_path}")
            try:
                df = pd.read_csv(file_path)
                return df
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {str(e)}")
                raise
        
        error_msg = f"No data file found for {poi_name} {trip_type} trips at {file_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

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
        mode_patterns = {}
        
        for poi in self.analysis_pois:
            for trip_type in ['inbound', 'outbound']:
                try:
                    df = self.load_poi_data(poi, trip_type)
                    
                    # Get mode columns
                    mode_cols = [col for col in df.columns if col.startswith('mode_')]
                    
                    # Calculate weighted average mode split
                    mode_split = (df[mode_cols].multiply(df['total_trips'], axis=0).sum() / 
                                df['total_trips'].sum())
                    
                    # Use standardized POI name in the key
                    mode_patterns[f"{poi}_{trip_type}"] = mode_split
                    
                except FileNotFoundError as e:
                    logger.warning(f"Skipping {poi} {trip_type}: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"Error analyzing mode patterns for {poi} {trip_type}: {str(e)}")
                    logger.error("Stack trace:", exc_info=True)
                    continue
        
        return mode_patterns

    def analyze_catchment_areas(self):
        """Analyze catchment areas for each POI"""
        catchment_areas = {}
        
        for poi in self.analysis_pois:
            try:
                # Load inbound trips data
                df = self.load_poi_data(poi, 'inbound')
                
                # Sort by total trips
                df_sorted = df.sort_values('total_trips', ascending=False)
                
                # Calculate cumulative percentage
                df_sorted['cumulative_trips'] = df_sorted['total_trips'].cumsum()
                df_sorted['cumulative_percentage'] = (df_sorted['cumulative_trips'] / df_sorted['total_trips'].sum()) * 100
                
                # Find zones that make up 80% of trips
                zones_80 = df_sorted[df_sorted['cumulative_percentage'] <= 80]
                
                catchment_areas[poi] = {
                    'total_zones': len(df),
                    'zones_80_percent': len(zones_80),
                    'total_trips': df['total_trips'].sum(),
                    'top_zones': df_sorted.head(10)[['tract', 'total_trips']].to_dict('records'),
                    'concentration_index': len(zones_80) / len(df) if len(df) > 0 else 0
                }
                
            except FileNotFoundError:
                logger.warning(f"No inbound data found for {poi}")
                catchment_areas[poi] = {
                    'total_zones': 0,
                    'zones_80_percent': 0,
                    'total_trips': 0,
                    'top_zones': [],
                    'concentration_index': 0
                }
            except Exception as e:
                logger.error(f"Error analyzing catchment area for {poi}: {str(e)}")
                logger.error("Stack trace:", exc_info=True)
                catchment_areas[poi] = {
                    'total_zones': 0,
                    'zones_80_percent': 0,
                    'total_trips': 0,
                    'top_zones': [],
                    'concentration_index': 0
                }
        
        # Save catchment areas analysis
        with open(self.stats_dir / "catchment_areas.json", 'w') as f:
            json.dump(catchment_areas, f, indent=2)
        
        return catchment_areas

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
        """Generate comprehensive insights report"""
        print("=== Mobility Pattern Analysis Report ===\n")
        
        # 1. Temporal patterns
        print("1. Peak Hour Comparison")
        print("--------------------------")
        temporal_patterns = self.analyze_temporal_patterns()
        for poi_direction, pattern in temporal_patterns.items():
            peak_hour = pattern.idxmax()
            peak_pct = pattern.max() * 100
            print(f"{poi_direction}:")
            print(f"  Peak hour: {peak_hour}")
            print(f"  Peak percentage: {peak_pct:.1f}%\n")
        
        # 2. Mode differences
        print("\n2. Mode Share Insights")
        print("----------------------")
        modes = self.analyze_mode_differences()
        
        for poi in self.analysis_pois:
            try:
                inbound = modes.get(f"{poi}_inbound", pd.Series())
                if not inbound.empty:
                    print(f"\n{poi}:")
                    top_modes = inbound.sort_values(ascending=False).head(3)
                    print("  Top 3 modes (inbound):")
                    for mode, share in top_modes.items():
                        mode_name = mode.replace('mode_', '')
                        print(f"    - {mode_name}: {share*100:.1f}%")
            except Exception as e:
                logger.error(f"Error processing mode data for {poi}: {str(e)}")
                continue
        
        # 3. Catchment areas
        print("\n\n3. Catchment Area Analysis")
        print("-------------------------\n")
        catchment = self.analyze_catchment_areas()
        
        for poi, data in catchment.items():
            try:
                print(f"\n{poi}:")
                # Use .get() with default values for optional fields
                print(f"  Total trips: {data.get('total_trips', 0):,.1f}")
                if data.get('active_zones'):
                    print(f"  Active zones: {data.get('active_zones', 0)}")
                if data.get('zones_80_percent'):
                    print(f"  Zones for 80% of trips: {data.get('zones_80_percent', 0)}")
                if data.get('concentration_index'):
                    print(f"  Concentration index: {data.get('concentration_index', 0):.2f}")
                
                # Print top zones if available
                top_zones = data.get('top_zones', [])
                if top_zones:
                    print("\n  Top zones by trip volume:")
                    for zone in top_zones[:5]:  # Show top 5 zones
                        print(f"    - Zone {zone['tract']}: {zone['total_trips']:.1f} trips")
            except Exception as e:
                logger.error(f"Error processing catchment data for {poi}: {str(e)}")
                continue

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
            
            if 'tract' in df.columns:
                top_zones = df.nlargest(5, 'total_trips')[['tract', 'total_trips']].to_dict('records')
                stats['top_5_zones'] = top_zones
                stats['top_5_concentration'] = sum(z['total_trips'] for z in top_zones) / df['total_trips'].sum() * 100
            else:
                print("WARNING: No tract column found!")
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