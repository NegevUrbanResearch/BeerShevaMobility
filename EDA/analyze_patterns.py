import pandas as pd
import numpy as np
from pathlib import Path
import os
from utils.data_standards import DataStandardizer
from utils.zone_utils import get_zone_type
import logging
import json
from scipy.spatial.distance import cosine

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

        # Define focus POIs and all POIs
        self.focus_pois = [
            'Ben-Gurion-University',
            'Soroka-Medical-Center',
            'Gav-Yam-High-Tech-Park'
        ]
        
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
        
        self.other_pois = [poi for poi in self.analysis_pois if poi not in self.focus_pois]
        
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

    def analyze_temporal_patterns(self):
        """Analyze temporal patterns across POIs"""
        patterns = {}
        
        for poi in self.analysis_pois:
            for trip_type in ['inbound', 'outbound']:
                try:
                    df = self.load_poi_data(poi, trip_type)
                    print(f"\nAnalyzing {poi} - {trip_type}")
                    
                    # Extract arrival time columns
                    time_cols = [col for col in df.columns if col.startswith('arrival_')]
                    if not time_cols:
                        print(f"No temporal columns found for {poi}")
                        continue
                    
                    # Calculate actual trip counts by multiplying percentages by total trips
                    hourly_counts = df[time_cols].multiply(df['total_trips'], axis=0)
                    
                    # Sum up total trips for each hour
                    total_by_hour = hourly_counts.sum()
                    
                    # Calculate the distribution (ensure it sums to 100%)
                    if total_by_hour.sum() > 0:
                        temporal_dist = total_by_hour / total_by_hour.sum()
                        
                        print(f"\nTemporal distribution summary for {poi} {trip_type}:")
                        print(f"Total trips processed: {total_by_hour.sum():.1f}")
                        print("\nTop 5 peak hours:")
                        top_hours = temporal_dist.sort_values(ascending=False).head()
                        for hour, value in top_hours.items():
                            print(f"{hour}: {value*100:.1f}%")
                    else:
                        print(f"Warning: No trips found for {poi} {trip_type}")
                        temporal_dist = pd.Series(0, index=time_cols)
                    
                    patterns[f"{poi}_{trip_type}"] = temporal_dist
                    
                except FileNotFoundError as e:
                    logger.warning(f"Skipping {poi} {trip_type}: {str(e)}")
                    continue
                except Exception as e:
                    logger.error(f"Error analyzing temporal patterns for {poi} {trip_type}: {str(e)}")
                    logger.error("Stack trace:", exc_info=True)
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
                    
                    # Calculate actual trip counts by mode
                    mode_counts = df[mode_cols].multiply(df['total_trips'], axis=0)
                    total_trips = df['total_trips'].sum()
                    
                    # Calculate weighted average mode split
                    if total_trips > 0:
                        mode_split = mode_counts.sum() / total_trips
                    else:
                        mode_split = pd.Series(0, index=mode_cols)
                    
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
                df_sorted['cumulative_percentage'] = (df_sorted['cumulative_trips'] / 
                                                    df_sorted['total_trips'].sum()) * 100
                
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

    def calculate_poi_similarity(self, poi1_data: dict, poi2_data: dict) -> float:
        """Calculate similarity between two POIs based on their characteristics"""
        features = []
        weights = {
            'mode_split': 0.4,
            'catchment': 0.3,
            'total_trips': 0.2,
            'purpose_split': 0.1
        }
        
        # Mode split similarity
        if 'mode_split' in poi1_data and 'mode_split' in poi2_data:
            # Get all unique modes
            all_modes = set(poi1_data['mode_split'].keys()) | set(poi2_data['mode_split'].keys())
            
            # Create vectors with 0s for missing modes
            vec1 = [poi1_data['mode_split'].get(mode, 0) for mode in all_modes]
            vec2 = [poi2_data['mode_split'].get(mode, 0) for mode in all_modes]
            
            if vec1 and vec2:  # Check if vectors are non-empty
                mode_sim = 1 - cosine(vec1, vec2)
                features.append(mode_sim * weights['mode_split'])
        
        # Purpose split similarity
        if 'purpose_split' in poi1_data and 'purpose_split' in poi2_data:
            # Get all unique purposes
            all_purposes = set(poi1_data['purpose_split'].keys()) | set(poi2_data['purpose_split'].keys())
            
            # Create vectors with 0s for missing purposes
            vec1 = [poi1_data['purpose_split'].get(purpose, 0) for purpose in all_purposes]
            vec2 = [poi2_data['purpose_split'].get(purpose, 0) for purpose in all_purposes]
            
            if vec1 and vec2:  # Check if vectors are non-empty
                purpose_sim = 1 - cosine(vec1, vec2)
                features.append(purpose_sim * weights['purpose_split'])
        
        # Catchment area similarity
        if 'top_5_concentration' in poi1_data and 'top_5_concentration' in poi2_data:
            catchment_sim = 1 - abs(
                poi1_data['top_5_concentration'] - poi2_data['top_5_concentration']
            ) / 100
            features.append(catchment_sim * weights['catchment'])
            
        # Trip volume similarity
        if 'total_trips' in poi1_data and 'total_trips' in poi2_data:
            volume_ratio = min(
                poi1_data['total_trips'],
                poi2_data['total_trips']
            ) / max(
                poi1_data['total_trips'],
                poi2_data['total_trips']
            )
            features.append(volume_ratio * weights['total_trips'])
        
        return np.mean(features)

    def find_most_similar_pois(self):
        """Find the most similar non-focus POI for each focus POI"""
        similarities = {}
        all_poi_stats = self.generate_poi_statistics()
        
        for focus_poi in self.focus_pois:
            focus_stats = all_poi_stats[focus_poi]['inbound']
            poi_similarities = {}
            
            for other_poi in self.other_pois:
                if other_poi not in self.focus_pois:
                    other_stats = all_poi_stats[other_poi]['inbound']
                    similarity = self.calculate_poi_similarity(focus_stats, other_stats)
                    poi_similarities[other_poi] = similarity
            
            most_similar = max(poi_similarities.items(), key=lambda x: x[1])
            similarities[focus_poi] = {
                'most_similar_poi': most_similar[0],
                'similarity_score': most_similar[1]
            }
        
        return similarities

    def calculate_aggregate_metrics(self):
        """Calculate aggregate metrics for non-focus POIs"""
        all_poi_stats = self.generate_poi_statistics()
        
        # Initialize aggregates
        aggregates = {
            'total_trips': [],
            'concentration_index': [],
            'mode_split': {},
            'purpose_split': {},
            'zones_80_percent': []
        }
        
        # Collect metrics from other POIs
        for poi in self.other_pois:
            stats = all_poi_stats[poi]['inbound']
            
            if 'total_trips' in stats:
                aggregates['total_trips'].append(stats['total_trips'])
            
            if 'top_5_concentration' in stats:
                aggregates['concentration_index'].append(stats['top_5_concentration'])
            
            if 'mode_split' in stats:
                for mode, share in stats['mode_split'].items():
                    if mode not in aggregates['mode_split']:
                        aggregates['mode_split'][mode] = []
                    aggregates['mode_split'][mode].append(share)
            
            if 'purpose_split' in stats:
                for purpose, share in stats['purpose_split'].items():
                    if purpose not in aggregates['purpose_split']:
                        aggregates['purpose_split'][purpose] = []
                    aggregates['purpose_split'][purpose].append(share)
        
        # Calculate averages and standard deviations
        average_metrics = {
            'avg_total_trips': np.mean(aggregates['total_trips']),
            'avg_concentration_index': np.mean(aggregates['concentration_index']),
            'avg_mode_split': {mode: np.mean(shares) for mode, shares in aggregates['mode_split'].items()},
            'avg_purpose_split': {purpose: np.mean(shares) for purpose, shares in aggregates['purpose_split'].items()},
            'std_total_trips': np.std(aggregates['total_trips']),
            'std_concentration_index': np.std(aggregates['concentration_index']),
            'std_mode_split': {mode: np.std(shares) for mode, shares in aggregates['mode_split'].items()},
            'std_purpose_split': {purpose: np.std(shares) for purpose, shares in aggregates['purpose_split'].items()}
        }
        
        return average_metrics

    def calculate_innovation_district_metrics(self):
        """Calculate aggregate metrics for the innovation district POIs"""
        all_poi_stats = self.generate_poi_statistics()
        
        innovation_metrics = {
            'total_trips': 0,
            'mode_split': {},
            'purpose_split': {},
            'weighted_concentration': 0
        }
        
        total_district_trips = 0
        
        for poi in self.focus_pois:
            stats = all_poi_stats[poi]['inbound']
            trips = stats.get('total_trips', 0)
            total_district_trips += trips
            
            # Weighted mode split
            if 'mode_split' in stats:
                for mode, share in stats['mode_split'].items():
                    if mode not in innovation_metrics['mode_split']:
                        innovation_metrics['mode_split'][mode] = 0
                    innovation_metrics['mode_split'][mode] += share * trips
            
            # Weighted purpose split
            if 'purpose_split' in stats:
                for purpose, share in stats['purpose_split'].items():
                    if purpose not in innovation_metrics['purpose_split']:
                        innovation_metrics['purpose_split'][purpose] = 0
                    innovation_metrics['purpose_split'][purpose] += share * trips
            
            # Weighted concentration
            if 'top_5_concentration' in stats:
                innovation_metrics['weighted_concentration'] += stats['top_5_concentration'] * trips
        
        # Normalize weighted metrics
        if total_district_trips > 0:
            innovation_metrics['mode_split'] = {
                mode: share / total_district_trips 
                for mode, share in innovation_metrics['mode_split'].items()
            }
            
            innovation_metrics['purpose_split'] = {
                purpose: share / total_district_trips 
                for purpose, share in innovation_metrics['purpose_split'].items()
            }
            
            innovation_metrics['weighted_concentration'] /= total_district_trips
        
        innovation_metrics['total_trips'] = total_district_trips
        
        return innovation_metrics

    def generate_insights_report(self):
        """Generate a comprehensive insights report"""
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
                print(f"  Total trips: {data.get('total_trips', 0):,.1f}")
                if data.get('zones_80_percent'):
                    print(f"  Zones for 80% of trips: {data.get('zones_80_percent', 0)}")
                if data.get('concentration_index'):
                    print(f"  Concentration index: {data.get('concentration_index', 0):.2f}")
                
                top_zones = data.get('top_zones', [])
                if top_zones:
                    print("\n  Top zones by trip volume:")
                    for zone in top_zones[:5]:
                        print(f"    - Zone {zone['tract']}: {zone['total_trips']:.1f} trips")
            except Exception as e:
                logger.error(f"Error processing catchment data for {poi}: {str(e)}")
                continue

    def generate_comparative_report(self):
        """Generate a comparative analysis report"""
        print("\n=== Comparative Mobility Pattern Analysis Report ===\n")
        
        # Find most similar POIs
        similarities = self.find_most_similar_pois()
        print("1. Most Similar POIs to Innovation District Components")
        print("------------------------------------------------")
        for focus_poi, similar in similarities.items():
            print(f"\n{focus_poi}:")
            print(f"  Most similar to: {similar['most_similar_poi']}")
            print(f"  Similarity score: {similar['similarity_score']:.2f}")
        
        # Aggregate metrics for non-focus POIs
        print("\n2. Comparison with City Averages")
        print("------------------------------")
        avg_metrics = self.calculate_aggregate_metrics()
        print("\nAverage metrics for non-innovation district POIs:")
        print(f"  Average total trips: {avg_metrics['avg_total_trips']:.1f} (±{avg_metrics['std_total_trips']:.1f})")
        print(f"  Average concentration index: {avg_metrics['avg_concentration_index']:.2f} (±{avg_metrics['std_concentration_index']:.2f})")
        
        print("\nMode split averages:")
        for mode, share in avg_metrics['avg_mode_split'].items():
            std = avg_metrics['std_mode_split'][mode]
            mode_name = mode.replace('mode_', '')
            print(f"  - {mode_name}: {share*100:.1f}% (±{std*100:.1f}%)")
        
        # Innovation district metrics
        print("\n3. Innovation District Aggregate Analysis")
        print("--------------------------------------")
        district_metrics = self.calculate_innovation_district_metrics()
        print(f"\nTotal district trips: {district_metrics['total_trips']:.1f}")
        print(f"Weighted concentration index: {district_metrics['weighted_concentration']:.2f}")
        
        print("\nDistrict-wide mode split:")
        for mode, share in district_metrics['mode_split'].items():
            mode_name = mode.replace('mode_', '')
            print(f"  - {mode_name}: {share*100:.1f}%")
        
        # Compare with city averages
        print("\n4. Innovation District vs City Average Comparisons")
        print("---------------------------------------------")
        for mode, district_share in district_metrics['mode_split'].items():
            mode_name = mode.replace('mode_', '')
            city_share = avg_metrics['avg_mode_split'].get(mode, 0)
            difference = (district_share - city_share) * 100
            print(f"\n{mode_name}:")
            print(f"  District: {district_share*100:.1f}%")
            print(f"  City Average: {city_share*100:.1f}%")
            print(f"  Difference: {difference:+.1f} percentage points")

if __name__ == "__main__":
    analyzer = MobilityPatternAnalyzer()
    
    # Generate all analyses
    stats = analyzer.generate_poi_statistics()
    print("\nStatistics generated and saved to:", analyzer.stats_dir)
    
    # Generate both reports
    analyzer.generate_insights_report()
    analyzer.generate_comparative_report()