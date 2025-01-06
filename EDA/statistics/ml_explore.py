import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from scipy import stats
import geopandas as gpd
from libpysal.weights import Queen, KNN
from esda.moran import Moran, Moran_Local
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
import statsmodels.api as sm
import json

@dataclass
class AnalysisResult:
    """Structure for storing analysis results with metadata"""
    method: str
    poi: str
    metric: str
    value: float
    significance: Optional[float] = None
    description: str = ""

class EnhancedMobilityAnalyzer:
    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.results: List[AnalysisResult] = []
        
    def load_and_prepare_data(self, poi_names: List[str]) -> Dict[str, gpd.GeoDataFrame]:
        """Load and prepare data with improved spatial handling and validation"""
        data_dict = {}
        print("Loading zones file...")
        zones = gpd.read_file(self.data_dir / "zones.geojson")
        print(f"Loaded {len(zones)} zones")
        
        # Validate zone geometries
        zones = zones[zones.geometry.is_valid].copy()
        print(f"Valid zones: {len(zones)}")
        
        for poi in poi_names:
            print(f"\nProcessing {poi}...")
            # Load basic data
            df = pd.read_csv(self.data_dir / f"{poi}_inbound_trips.csv")
            
            # Merge with zones and validate
            print(f"Merging {poi} data with zones...")
            gdf = df.merge(
                zones,
                left_on='tract',
                right_on='YISHUV_STAT11',
                how='left'
            )
            
            print(f"Initial shape: {gdf.shape}")
            
            # Check for merge success
            merge_success = (gdf['geometry'].notna().sum() / len(gdf)) * 100
            print(f"Successful merge rate: {merge_success:.1f}%")
            
            # Remove rows with invalid geometries
            gdf = gdf[gdf.geometry.notna()].copy()
            print(f"Shape after removing invalid geometries: {gdf.shape}")
            
            # Convert to GeoDataFrame
            gdf = gpd.GeoDataFrame(gdf, geometry='geometry')
            
            # Add centroids
            gdf['centroid'] = gdf.geometry.centroid
            gdf['centroid_x'] = gdf.centroid.x
            gdf['centroid_y'] = gdf.centroid.y
            
            data_dict[poi] = gdf
            
        return data_dict

    def analyze_high_volume_patterns(self, data_dict: Dict[str, gpd.GeoDataFrame]) -> None:
        """Analyze patterns in high-volume origin tracts"""
        for poi, gdf in data_dict.items():
            # Define high volume threshold
            threshold = gdf['total_trips'].quantile(0.75)
            high_volume = gdf[gdf['total_trips'] >= threshold]
            
            # Compare mode shares
            mode_cols = [col for col in gdf.columns if col.startswith('mode_')]
            for mode in mode_cols:
                t_stat, p_val = stats.ttest_ind(
                    high_volume[mode],
                    gdf[gdf['total_trips'] < threshold][mode]
                )
                
                self.results.append(AnalysisResult(
                    method="high_volume_comparison",
                    poi=poi,
                    metric=f"{mode}_difference",
                    value=t_stat,
                    significance=p_val,
                    description=f"Difference in {mode} between high and low volume origins"
                ))

    def analyze_spatial_autocorrelation(self, data_dict: Dict[str, gpd.GeoDataFrame]) -> None:
        """Analyze spatial autocorrelation of key metrics with robust geometry handling"""
        for poi, gdf in data_dict.items():
            # Remove rows with invalid geometries
            valid_geom_mask = ~gdf.geometry.isna() & gdf.geometry.is_valid
            if valid_geom_mask.sum() < 2:  # Need at least 2 valid geometries
                print(f"Warning: Not enough valid geometries for {poi}")
                continue
                
            valid_gdf = gdf[valid_geom_mask].copy()
            
            # Create KNN weights matrix instead of Queen
            try:
                print(f"Creating KNN weights matrix for {poi}...")
                w = KNN.from_dataframe(valid_gdf, k=5)  # Use 5 nearest neighbors
                w.transform = 'r'  # Row-standardize weights
                print(f"Created weights matrix with {len(w.neighbors)} observations")
            except Exception as e:
                print(f"Warning: Could not create weights matrix for {poi}: {str(e)}")
                continue
            
            # Analyze autocorrelation for key metrics
            metrics = {
                'total_trips': gdf['total_trips'],
                **{col: gdf[col] for col in gdf.columns if col.startswith('mode_')}
            }
            
            for metric_name, values in metrics.items():
                moran = Moran(values, w)
                
                self.results.append(AnalysisResult(
                    method="spatial_autocorrelation",
                    poi=poi,
                    metric=metric_name,
                    value=moran.I,
                    significance=moran.p_sim,
                    description=f"Moran's I for {metric_name}"
                ))
                
                # Local Moran's I for hotspot detection
                local_moran = Moran_Local(values, w)
                significant_clusters = (local_moran.p_sim < 0.05).sum()
                
                self.results.append(AnalysisResult(
                    method="local_clustering",
                    poi=poi,
                    metric=f"{metric_name}_clusters",
                    value=significant_clusters,
                    significance=None,
                    description=f"Number of significant local clusters for {metric_name}"
                ))

    def fit_decay_model(self, distances, y):
        """Helper function to fit distance decay model"""
        try:
            # Ensure proper array shapes
            X = np.array(distances).reshape(-1, 1)
            y = np.array(y)
            
            # Remove any inf or nan values
            mask = np.isfinite(X.ravel()) & np.isfinite(y)
            X = X[mask]
            y = y[mask]
            
            if len(X) < 2:  # Need at least 2 points for regression
                return None, 0
                
            model = LinearRegression()
            model.fit(X, y)
            r2 = r2_score(y, model.predict(X))
            return model.coef_[0], r2
        except Exception as e:
            print(f"Error in fit_decay_model: {str(e)}")
            return None, 0

    def analyze_distance_decay(self, data_dict: Dict[str, gpd.GeoDataFrame]) -> None:
        """Analyze how metrics decay with distance from POI with robust handling"""
        print("\nAnalyzing distance decay patterns...")
        poi_locations = {
            'BGU': {'x': 163000, 'y': 580000},
            'Soroka_Hospital': {'x': 163000, 'y': 580000}
        }
        
        for poi, gdf in data_dict.items():
            print(f"\nProcessing {poi}...")
            
            # Validate data
            valid_mask = (
                gdf['centroid_x'].notna() & 
                gdf['centroid_y'].notna() & 
                gdf['total_trips'].notna() &
                (gdf['total_trips'] > 0)
            )
            
            if valid_mask.sum() < 2:
                print(f"Warning: Not enough valid data for {poi}")
                continue
            
            valid_gdf = gdf[valid_mask].copy()
            
            # Calculate distances
            poi_point = np.array([poi_locations[poi]['x'], poi_locations[poi]['y']])
            distances = np.sqrt(
                (valid_gdf['centroid_x'] - poi_point[0])**2 +
                (valid_gdf['centroid_y'] - poi_point[1])**2
            )
            
            # Analyze relationship with distance
            metrics = {
                'total_trips': valid_gdf['total_trips'],
                **{col: valid_gdf[col] for col in valid_gdf.columns if col.startswith('mode_')}
            }
            
            print(f"Analyzing {len(metrics)} metrics for {poi}...")
            
            for metric_name, values in metrics.items():
                try:
                    # Convert Series to numpy array
                    values_array = np.array(values)
                    # Use log transform for decay analysis
                    y = np.log(values_array + 1)  # Add 1 to handle zeros
                    
                    coef, r2 = self.fit_decay_model(distances, y)
                    
                    if coef is not None and r2 > 0.1:  # Only record meaningful relationships
                        print(f"Found decay relationship for {metric_name}: R2={r2:.3f}")
                        
                        self.results.append(AnalysisResult(
                            method="distance_decay",
                            poi=poi,
                            metric=metric_name,
                            value=coef,
                            significance=r2,
                            description=f"Distance decay coefficient for {metric_name}"
                        ))
                except Exception as e:
                    print(f"Warning: Could not analyze distance decay for {metric_name}: {str(e)}")
    
    def analyze_mode_competition(self, data_dict: Dict[str, gpd.GeoDataFrame]) -> None:
        """Analyze competition between transport modes"""
        for poi, gdf in data_dict.items():
            mode_cols = [col for col in gdf.columns if col.startswith('mode_')]
            
            # Calculate correlations between modes
            mode_correlations = gdf[mode_cols].corr()
            
            # Find strongest competitive relationships
            for mode1 in mode_cols:
                for mode2 in mode_cols:
                    if mode1 < mode2:  # Avoid duplicates
                        correlation = mode_correlations.loc[mode1, mode2]
                        
                        self.results.append(AnalysisResult(
                            method="mode_competition",
                            poi=poi,
                            metric=f"{mode1}_vs_{mode2}",
                            value=correlation,
                            description=f"Correlation between {mode1} and {mode2}"
                        ))

    def analyze_spatial_regression(self, data_dict: Dict[str, gpd.GeoDataFrame]) -> None:
        """Perform spatial regression analysis with cleaner output"""
        print("\nPerforming spatial regression analysis...")
        import warnings
        
        for poi, gdf in data_dict.items():
            print(f"\nAnalyzing {poi}...")
            
            # Prepare features
            mode_cols = [col for col in gdf.columns if col.startswith('mode_')]
            X = gdf[mode_cols].copy()
            X = X.fillna(0)
            
            try:
                # Temporarily suppress detailed warnings
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always")
                    
                    # Create weights matrix
                    queen_w = Queen.from_dataframe(gdf, use_index=True)
                    
                    # Report summary of disconnected components without individual islands
                    if len(w) > 0:
                        disconnect_warning = str(w[-1].message)
                        if "disconnected components" in disconnect_warning:
                            n_components = int(disconnect_warning.split('\n')[1].strip().split()[2])
                            n_islands = len(disconnect_warning.split('islands with ids:')[1].split(',')) if 'islands' in disconnect_warning else 0
                            print(f"Note: Found {n_components} disconnected components and {n_islands} isolated areas")
                
                queen_w.transform = 'r'
                
                # Create spatial lags
                for mode in mode_cols:
                    try:
                        X[f"{mode}_spatial_lag"] = queen_w.sparse.dot(gdf[mode].fillna(0))
                    except Exception as e:
                        print(f"Warning: Could not create spatial lag for {mode}")
                
                # Prepare and fit model
                X = sm.add_constant(X)
                X = X.replace([np.inf, -np.inf], np.nan)
                X = X.fillna(0)
                y = gdf['total_trips'].fillna(0)
                
                model = sm.OLS(y, X)
                results = model.fit()
                
                # Store significant results
                significant_vars = results.pvalues[results.pvalues < 0.05]
                if len(significant_vars) > 0:
                    print(f"Found {len(significant_vars)} significant spatial relationships")
                
                for var in significant_vars.index:
                    self.results.append(AnalysisResult(
                        method="spatial_regression",
                        poi=poi,
                        metric=var,
                        value=results.params[var],
                        significance=results.pvalues[var],
                        description=f"Spatial regression coefficient for {var}"
                    ))
                    
            except Exception as e:
                print(f"Warning: Spatial regression failed for {poi}: {str(e)}")

    def analyze_temporal_patterns(self, data_dict: Dict[str, gpd.GeoDataFrame]) -> None:
        """Analyze temporal patterns and their relationship with other variables"""
        for poi, gdf in data_dict.items():
            time_cols = [col for col in gdf.columns if col.startswith('arrival_')]
            
            # Convert percentages to actual trips
            temporal_trips = gdf[time_cols].multiply(gdf['total_trips'], axis=0) / 100.0
            
            # Identify peak periods
            peak_periods = temporal_trips.mean().nlargest(3)
            
            for period, value in peak_periods.items():
                self.results.append(AnalysisResult(
                    method="temporal_patterns",
                    poi=poi,
                    metric=f"peak_{period}",
                    value=value,
                    description=f"Average trips during {period}"
                ))
                
            # Analyze relationship between peak period usage and mode choice
            mode_cols = [col for col in gdf.columns if col.startswith('mode_')]
            for peak_period in peak_periods.index:
                peak_mask = temporal_trips[peak_period] > temporal_trips[peak_period].median()
                
                for mode in mode_cols:
                    t_stat, p_val = stats.ttest_ind(
                        gdf.loc[peak_mask, mode],
                        gdf.loc[~peak_mask, mode]
                    )
                    
                    self.results.append(AnalysisResult(
                        method="peak_period_mode_choice",
                        poi=poi,
                        metric=f"{peak_period}_{mode}",
                        value=t_stat,
                        significance=p_val,
                        description=f"Difference in {mode} during {peak_period}"
                    ))
    def generate_analysis_summary(self) -> Dict:
        """Generate a structured summary of all analyses with proper type conversion"""
        def convert_to_native_types(obj):
            """Helper function to convert numpy types to native Python types"""
            if isinstance(obj, (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32,
                            np.int64, np.uint8, np.uint16, np.uint32, np.uint64)):
                return int(obj)
            elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {key: convert_to_native_types(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_to_native_types(item) for item in obj]
            return obj

        summary = {
            'significant_findings': [],
            'patterns_by_poi': {},
            'spatial_patterns': [],
            'temporal_patterns': [],
            'mode_choice_patterns': []
        }
        
        # Filter significant results
        significant_results = [
            result for result in self.results
            if result.significance is None or result.significance < 0.05
        ]
        
        # Organize results by type
        for result in significant_results:
            # Convert values to native Python types
            value = convert_to_native_types(result.value)
            significance = convert_to_native_types(result.significance) if result.significance is not None else None
            
            if result.method == "spatial_autocorrelation":
                summary['spatial_patterns'].append({
                    'poi': result.poi,
                    'metric': result.metric,
                    'value': value,
                    'description': result.description
                })
            elif result.method == "temporal_patterns":
                summary['temporal_patterns'].append({
                    'poi': result.poi,
                    'period': result.metric,
                    'volume': value,
                    'description': result.description
                })
            
            # Add to POI-specific patterns
            if result.poi not in summary['patterns_by_poi']:
                summary['patterns_by_poi'][result.poi] = []
            summary['patterns_by_poi'][result.poi].append({
                'method': result.method,
                'metric': result.metric,
                'value': value,
                'significance': significance,
                'description': result.description
            })
        
        return summary

    def run_full_analysis(self, poi_names: List[str]) -> Dict:
        """Run complete analysis pipeline with proper error handling"""
        try:
            # Load and prepare data
            data_dict = self.load_and_prepare_data(poi_names)
            
            # Run all analyses
            self.analyze_high_volume_patterns(data_dict)
            self.analyze_spatial_autocorrelation(data_dict)
            self.analyze_distance_decay(data_dict)
            self.analyze_mode_competition(data_dict)
            self.analyze_spatial_regression(data_dict)
            self.analyze_temporal_patterns(data_dict)
            
            # Generate summary
            summary = self.generate_analysis_summary()
            
            # Ensure output directory exists
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save results
            output_file = self.output_dir / 'enhanced_analysis_summary.json'
            with open(output_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            print("\nAnalysis complete. Summary of findings:")
            print(f"- Spatial patterns found: {len(summary['spatial_patterns'])}")
            print(f"- Temporal patterns found: {len(summary['temporal_patterns'])}")
            print(f"\nResults saved to {output_file}")
            
            return summary
            
        except Exception as e:
            print(f"Error in analysis pipeline: {str(e)}")
            raise

if __name__ == "__main__":
    current_dir = Path(__file__).parent
    data_dir = current_dir / "output/dashboard_data"
    output_dir = current_dir / "output/analysis"
    
    analyzer = EnhancedMobilityAnalyzer(data_dir, output_dir)
    summary = analyzer.run_full_analysis(['BGU', 'Soroka_Hospital'])
    
    print("\nAnalysis complete. Summary of findings:")
    print(f"- Spatial patterns found: {len(summary['spatial_patterns'])}")
    print(f"- Temporal patterns found: {len(summary['temporal_patterns'])}")
    print("\nResults saved to enhanced_analysis_summary.json")