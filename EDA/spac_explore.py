import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass
import geopandas as gpd
from shapely.geometry import Point
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import pyproj
from scipy.spatial import cKDTree
import json

@dataclass
class SpatialPOIData:
    inbound: gpd.GeoDataFrame
    outbound: gpd.GeoDataFrame
    location: Point
    name: str

class CoordinateConverter:
    def __init__(self):
        self.itm = pyproj.CRS("EPSG:2039")  # Israeli Transverse Mercator
        self.wgs84 = pyproj.CRS("EPSG:4326")  # WGS84
        self.transformer = pyproj.Transformer.from_crs(self.itm, self.wgs84, always_xy=True)
    
    def itm_to_wgs84(self, x: float, y: float) -> Tuple[float, float]:
        """Convert ITM coordinates to WGS84"""
        return self.transformer.transform(x, y)

class SpatialMobilityAnalyzer:
    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.poi_data: Dict[str, SpatialPOIData] = {}
        self.converter = CoordinateConverter()
        
        # Update zones file path and loading
        self.zones_file = data_dir / "zones.geojson"
        print(f"\nAttempting to load zones from: {self.zones_file}")
        
        if not self.zones_file.exists():
            raise FileNotFoundError(f"Zones file not found at {self.zones_file}")
        
        # Load and standardize zones
        self.zones = gpd.read_file(self.zones_file)
        print('jump here')
        print(self.zones.columns)
        print(self.zones['SHEM_YISHUV_ENGLISH'].head())
        # Add centroids if they don't exist
        if 'centroid_lon' not in self.zones.columns:
            print("Calculating zone centroids...")
            self.zones['centroid_lon'] = self.zones.geometry.centroid.x
            self.zones['centroid_lat'] = self.zones.geometry.centroid.y
        
        print(f"Loaded {len(self.zones)} zones")
        print("Zone columns:", self.zones.columns.tolist())
        
    def load_spatial_data(self, poi_names: List[str], poi_locations: Dict) -> None:
        """Load and prepare spatial data for analysis"""
        for poi in poi_names:
            try:
                print(f"\nLoading data for {poi}")
                
                # Load basic data
                inbound = pd.read_csv(self.data_dir / f"{poi}_inbound_trips.csv")
                outbound = pd.read_csv(self.data_dir / f"{poi}_outbound_trips.csv")
                
                print(f"Inbound shape: {inbound.shape}")
                print(f"Outbound shape: {outbound.shape}")
                
                # Merge with zone geometries
                print("\nMerging with zone geometries...")
                inbound = inbound.merge(
                    self.zones[['YISHUV_STAT11', 'geometry', 'centroid_lon', 'centroid_lat']], 
                    left_on='tract',
                    right_on='YISHUV_STAT11',
                    how='left'
                )
                outbound = outbound.merge(
                    self.zones[['YISHUV_STAT11', 'geometry', 'centroid_lon', 'centroid_lat']], 
                    left_on='tract',
                    right_on='YISHUV_STAT11',
                    how='left'
                )
                
                # Create GeoDataFrames
                print("\nCreating GeoDataFrames...")
                inbound_gdf = gpd.GeoDataFrame(
                    inbound,
                    geometry='geometry',
                    crs=self.zones.crs
                )
                outbound_gdf = gpd.GeoDataFrame(
                    outbound,
                    geometry='geometry',
                    crs=self.zones.crs
                )
                
                # Create POI location point
                poi_location = Point(poi_locations[poi]['lon'], poi_locations[poi]['lat'])
                
                self.poi_data[poi] = SpatialPOIData(
                    inbound=inbound_gdf,
                    outbound=outbound_gdf,
                    location=poi_location,
                    name=poi
                )
                print(f"\nSuccessfully loaded data for {poi}")
                
            except Exception as e:
                print(f"\nError loading data for {poi}: {str(e)}")
                print("Stack trace:")
                import traceback
                print(traceback.format_exc())
                continue

    def analyze_catchment_areas(self) -> Dict:
        """Analyze catchment areas using distance-based approach"""
        catchment_analysis = {}
        
        for poi_name, data in self.poi_data.items():
            # Calculate distances to POI
            distances = data.inbound.geometry.distance(data.location)
            
            # Calculate distance-based statistics
            distance_stats = {
                '25th_percentile': np.percentile(distances, 25),
                'median': np.percentile(distances, 50),
                '75th_percentile': np.percentile(distances, 75),
                '90th_percentile': np.percentile(distances, 90)
            }
            
            # Analyze catchment areas by mode
            mode_cols = [col for col in data.inbound.columns if col.startswith('mode_')]
            mode_catchments = {}
            
            for mode in mode_cols:
                mode_distances = distances[data.inbound[mode] > 0.5]  # Threshold for mode usage
                if len(mode_distances) > 0:
                    mode_catchments[mode] = {
                        'median_distance': np.median(mode_distances),
                        'max_distance': np.max(mode_distances),
                        'trip_count': len(mode_distances)
                    }
            
            catchment_analysis[poi_name] = {
                'distance_stats': distance_stats,
                'mode_catchments': mode_catchments
            }
        
        return catchment_analysis

    def identify_spatial_clusters(self) -> Dict:
            """Identify spatial clusters of trip origins/destinations"""
            cluster_analysis = {}
            
            for poi_name, data in self.poi_data.items():
                print(f"\nAnalyzing clusters for {poi_name}")
                
                # Filter out rows with missing values
                mask = ~(data.inbound[['centroid_lon', 'centroid_lat', 'total_trips']].isna().any(axis=1))
                valid_data = data.inbound[mask].copy()
                
                if len(valid_data) == 0:
                    print(f"No valid data points for {poi_name} after filtering NaN values")
                    cluster_analysis[poi_name] = {
                        'error': 'No valid data points after filtering NaN values',
                        'original_points': len(data.inbound),
                        'valid_points': 0
                    }
                    continue
                    
                print(f"Using {len(valid_data)} valid data points for clustering")
                
                # Use centroids for clustering
                X = np.column_stack([
                    valid_data['centroid_lon'],
                    valid_data['centroid_lat'],
                    valid_data['total_trips']
                ])
                
                # Scale the features
                X_scaled = StandardScaler().fit_transform(X)
                
                # Perform DBSCAN clustering with adjusted parameters
                db = DBSCAN(eps=0.5, min_samples=3).fit(X_scaled)  # Relaxed parameters
                
                # Analyze clusters
                labels = db.labels_
                n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
                
                print(f"Found {n_clusters} clusters")
                
                # Store cluster information
                clusters = []
                for i in range(n_clusters):
                    mask = labels == i
                    if mask.any():  # Check if cluster has any points
                        cluster_data = valid_data[mask]
                        cluster_info = {
                            'size': int(mask.sum()),
                            'total_trips': float(cluster_data['total_trips'].sum()),
                            'center': {
                                'longitude': float(cluster_data['centroid_lon'].mean()),
                                'latitude': float(cluster_data['centroid_lat'].mean())
                            },
                            'dominant_mode': self._get_dominant_mode(cluster_data)
                        }
                        clusters.append(cluster_info)
                
                # Analyze noise points
                noise_mask = labels == -1
                noise_points = valid_data[noise_mask]
                noise_info = {
                    'noise_points': int(noise_mask.sum()),
                    'noise_trips': float(noise_points['total_trips'].sum()) if len(noise_points) > 0 else 0,
                    'noise_percentage': float((noise_mask.sum() / len(valid_data)) * 100)
                }
                
                # Store analysis results
                cluster_analysis[poi_name] = {
                    'n_clusters': n_clusters,
                    'clusters': clusters,
                    'noise_stats': noise_info,
                    'data_stats': {
                        'total_points_analyzed': len(valid_data),
                        'points_removed_nan': len(data.inbound) - len(valid_data)
                    }
                }
            
            return cluster_analysis

    def analyze_directional_patterns(self) -> Dict:
        """Analyze directional distribution of trips"""
        directional_analysis = {}
        
        for poi_name, data in self.poi_data.items():
            # Calculate bearings from POI to trip origins
            bearings = self._calculate_bearings(data.inbound.geometry, data.location)
            
            # Analyze trips by direction
            directions = self._categorize_directions(bearings, data.inbound['total_trips'])
            
            # Analyze mode split by direction
            mode_cols = [col for col in data.inbound.columns if col.startswith('mode_')]
            mode_by_direction = self._analyze_modes_by_direction(
                data.inbound, bearings, mode_cols
            )
            
            directional_analysis[poi_name] = {
                'direction_distribution': directions,
                'mode_by_direction': mode_by_direction
            }
        
        return directional_analysis

    def analyze_spatial_mode_competition(self) -> Dict:
        """Analyze spatial competition between different transport modes"""
        competition_analysis = {}
        
        for poi_name, data in self.poi_data.items():
            mode_cols = [col for col in data.inbound.columns if col.startswith('mode_')]
            
            # Calculate mode dominance at different distances
            distance_breaks = np.linspace(0, data.inbound.geometry.distance(data.location).max(), 10)
            mode_dominance = []
            
            for i in range(len(distance_breaks)-1):
                min_dist, max_dist = distance_breaks[i], distance_breaks[i+1]
                mask = (data.inbound.geometry.distance(data.location) >= min_dist) & \
                       (data.inbound.geometry.distance(data.location) < max_dist)
                
                if mask.any():
                    dominant_mode = self._get_dominant_mode(data.inbound[mask])
                    mode_dominance.append({
                        'distance_range': (min_dist, max_dist),
                        'dominant_mode': dominant_mode['mode'],
                        'mode_share': dominant_mode['share']
                    })
            
            # Analyze mode transition points
            mode_transitions = self._find_mode_transitions(mode_dominance)
            
            competition_analysis[poi_name] = {
                'mode_dominance': mode_dominance,
                'mode_transitions': mode_transitions
            }
        
        return competition_analysis

    def analyze_spatial_interactions(self) -> Dict:
        """Analyze spatial interactions between POIs"""
        interactions = {}
        
        poi_pairs = [(p1, p2) for i, p1 in enumerate(self.poi_data.keys()) 
                     for p2 in list(self.poi_data.keys())[i+1:]]
        
        for poi1, poi2 in poi_pairs:
            data1, data2 = self.poi_data[poi1], self.poi_data[poi2]
            
            # Find common trip origins
            common_origins = self._identify_common_origins(data1.inbound, data2.inbound)
            
            # Analyze mode choice differences for common origins
            mode_differences = self._analyze_mode_differences(
                data1.inbound.loc[common_origins],
                data2.inbound.loc[common_origins]
            )
            
            # Calculate spatial correlation
            spatial_correlation = self._calculate_spatial_correlation(
                data1.inbound.loc[common_origins, 'total_trips'],
                data2.inbound.loc[common_origins, 'total_trips']
            )
            
            interactions[f"{poi1}_vs_{poi2}"] = {
                'common_origins_count': len(common_origins),
                'mode_differences': mode_differences,
                'spatial_correlation': spatial_correlation
            }
        
        return interactions

    def _get_dominant_mode(self, df: pd.DataFrame) -> Dict:
        """Find dominant transportation mode in a subset of data"""
        mode_cols = [col for col in df.columns if col.startswith('mode_')]
        mode_shares = df[mode_cols].multiply(df['total_trips'], axis=0).sum() / \
                     df['total_trips'].sum()
        
        dominant_mode = mode_shares.idxmax()
        return {
            'mode': dominant_mode.replace('mode_', ''),
            'share': mode_shares[dominant_mode]
        }

    def _calculate_bearings(self, origins: gpd.GeoSeries, dest: Point) -> pd.Series:
        """Calculate bearings from destination to origins using centroids"""
        # Convert geometries to centroids if they aren't points
        origin_points = origins.centroid
        
        y_diff = origin_points.y - dest.y
        x_diff = origin_points.x - dest.x
        bearings = np.degrees(np.arctan2(y_diff, x_diff)) % 360
        return bearings

    def _categorize_directions(self, bearings: pd.Series, trips: pd.Series) -> Dict:
        """Categorize trips by direction"""
        direction_bins = {
            'North': (315, 45),
            'East': (45, 135),
            'South': (135, 225),
            'West': (225, 315)
        }
        
        directions = {}
        for direction, (start, end) in direction_bins.items():
            if start < end:
                mask = (bearings >= start) & (bearings < end)
            else:
                mask = (bearings >= start) | (bearings < end)
            
            directions[direction] = {
                'trip_count': trips[mask].sum(),
                'percentage': (trips[mask].sum() / trips.sum()) * 100
            }
        
        return directions

    def _analyze_modes_by_direction(self, df: gpd.GeoDataFrame, bearings: pd.Series, 
                                  mode_cols: List[str]) -> Dict:
        """Analyze mode split by direction"""
        direction_bins = {
            'North': (315, 45),
            'East': (45, 135),
            'South': (135, 225),
            'West': (225, 315)
        }
        
        mode_by_direction = {}
        for direction, (start, end) in direction_bins.items():
            if start < end:
                mask = (bearings >= start) & (bearings < end)
            else:
                mask = (bearings >= start) | (bearings < end)
            
            subset = df[mask]
            if len(subset) > 0:
                mode_shares = subset[mode_cols].multiply(subset['total_trips'], axis=0).sum() / \
                            subset['total_trips'].sum()
                mode_by_direction[direction] = mode_shares.to_dict()
        
        return mode_by_direction

    def _find_mode_transitions(self, mode_dominance: List[Dict]) -> List[Dict]:
        """Identify points where dominant mode changes"""
        transitions = []
        for i in range(len(mode_dominance)-1):
            if mode_dominance[i]['dominant_mode'] != mode_dominance[i+1]['dominant_mode']:
                transitions.append({
                    'distance': mode_dominance[i]['distance_range'][1],
                    'from_mode': mode_dominance[i]['dominant_mode'],
                    'to_mode': mode_dominance[i+1]['dominant_mode']
                })
        return transitions

    def _identify_common_origins(self, gdf1: gpd.GeoDataFrame, gdf2: gpd.GeoDataFrame) -> List[int]:
        """Identify common trip origins between two POIs"""
        print("\nDebugging _identify_common_origins:")
        print(f"GDF1 shape: {gdf1.shape}")
        print(f"GDF2 shape: {gdf2.shape}")
        
        # Use centroids for comparison
        centroids1 = gdf1.geometry.centroid
        centroids2 = gdf2.geometry.centroid
        
        print("\nCentroid 1 stats:")
        print(pd.DataFrame({
            'X coordinates': centroids1.x.describe(),
            'Y coordinates': centroids1.y.describe()
        }))
        
        # Remove any invalid geometries
        valid_mask1 = ~centroids1.isna()
        valid_mask2 = ~centroids2.isna()
        
        if not (valid_mask1.all() and valid_mask2.all()):
            print(f"Warning: Found {(~valid_mask1).sum()} invalid geometries in GDF1")
            print(f"Warning: Found {(~valid_mask2).sum()} invalid geometries in GDF2")
        
        # Use only valid geometries
        centroids1 = centroids1[valid_mask1]
        centroids2 = centroids2[valid_mask2]
        
        # Build KD-tree for efficient spatial search
        tree = cKDTree(np.column_stack([centroids1.x, centroids1.y]))
        
        # Find points within threshold distance
        threshold = 1000  # meters
        indices = []
        for x, y in zip(centroids2.x, centroids2.y):
            nearby = tree.query_ball_point([x, y], threshold)
            indices.extend(nearby)
        
        return list(set(indices))

    def _analyze_mode_differences(self, gdf1: gpd.GeoDataFrame, 
                                gdf2: gpd.GeoDataFrame) -> Dict:
        """Analyze differences in mode choice for common origins"""
        mode_cols = [col for col in gdf1.columns if col.startswith('mode_')]
        
        mode_shares1 = gdf1[mode_cols].multiply(gdf1['total_trips'], axis=0).sum() / \
                      gdf1['total_trips'].sum()
        mode_shares2 = gdf2[mode_cols].multiply(gdf2['total_trips'], axis=0).sum() / \
                      gdf2['total_trips'].sum()
        
        return {
            'differences': (mode_shares1 - mode_shares2).to_dict(),
            'correlation': mode_shares1.corr(mode_shares2)
        }

    def _calculate_spatial_correlation(self, trips1: pd.Series, trips2: pd.Series) -> float:
        """Calculate spatial correlation of trip patterns"""
        return trips1.corr(trips2)

    def generate_report(self):
        """Generate comprehensive spatial analysis report"""
        report = {
            'catchment_areas': self.analyze_catchment_areas(),
            'spatial_clusters': self.identify_spatial_clusters(),
            'directional_patterns': self.analyze_directional_patterns(),
            'mode_competition': self.analyze_spatial_mode_competition(),
            'spatial_interactions': self.analyze_spatial_interactions()
        }
        
        # Save to JSON
        with open(self.output_dir / 'spatial_analysis_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        return report

    def validate_data(self, df: pd.DataFrame, name: str) -> None:
        """Validate loaded data"""
        print(f"\nValidating {name} data:")
        print("Columns:", df.columns.tolist())
        print("Sample data:")
        print(df.head())
        
        # Check for required columns
        required_cols = ['tract', 'total_trips']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns in {name}: {missing_cols}")
        
        # Check for mode columns
        mode_cols = [col for col in df.columns if col.startswith('mode_')]
        if not mode_cols:
            raise ValueError(f"No mode columns found in {name}")
        
        # Validate percentages
        for col in mode_cols:
            total = df[col].sum()
            if not (99.5 <= total <= 100.5):  # Allow for small floating point differences
                print(f"WARNING: {col} percentages sum to {total}%")

if __name__ == "__main__":
    current_dir = Path(__file__).parent
    data_dir = current_dir / "output" / "dashboard_data"
    output_dir = current_dir / "output" / "analysis"
    
    # POI locations in WGS84
    poi_locations = {
        'BGU': {'lat': 31.262218, 'lon': 34.801472},
        'Soroka_Hospital': {'lat': 31.262650, 'lon': 34.799452}
    }
    
    try:
        analyzer = SpatialMobilityAnalyzer(data_dir, output_dir)
        analyzer.load_spatial_data(
            ['BGU', 'Soroka_Hospital'],
            poi_locations
        )
        report = analyzer.generate_report()
        print("\nAnalysis complete. Report generated successfully.")
        
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        import traceback
        print(traceback.format_exc())