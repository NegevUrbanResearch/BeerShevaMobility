import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
import logging
from shapely.geometry import Point
import math
from typing import Dict

# Configuration
POI_LOCATIONS = [
    {"name": "Emek Shara industrial area", "lat": 31.2271875, "lon": 34.8090625},
    {"name": "BGU", "lat": 31.2614375, "lon": 34.7995625},
    {"name": "Soroka Hospital", "lat": 31.2579375, "lon": 34.8003125},
    {"name": "Yes Planet", "lat": 31.2244375, "lon": 34.8010625},
    {"name": "Grand Kenyon", "lat": 31.2506875, "lon": 34.7716875},
    {"name": "Omer industrial area", "lat": 31.2703125, "lon": 34.8364375},
    {"name": "K collage", "lat": 31.2698125, "lon": 34.7815625},
    {"name": "HaNegev Mall", "lat": 31.2436875, "lon": 34.7949375},
    {"name": "BIG", "lat": 31.2443125, "lon": 34.8114375},
    {"name": "Assuta Hospital", "lat": 31.2451875, "lon": 34.7964375},
    {"name": "Gev Yam", "lat": 31.2641875, "lon": 34.8128125},
    {"name": "Ramat Hovav Industry", "lat": 31.1361875, "lon": 34.7898125},
    {"name": "Sami Shimon collage", "lat": 31.2499375, "lon": 34.7893125}
]

class SpatialAnalyzer:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.output_dir = data_dir / "output"
        self.stats_dir = self.output_dir / "statistics"
        self.stats_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize logger
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Load zones once
        self.zones_gdf = self.load_zones()

    def load_zones(self) -> gpd.GeoDataFrame:
        """Load zone geometries from GeoJSON"""
        zones_file = "/Users/noamgal/DSProjects/BeerShevaMobility/EDA/output/data/processed/zones_with_cities.geojson"
        if not zones_file.exists():
            raise FileNotFoundError(f"Zones file not found at {zones_file}")
        
        zones_gdf = gpd.read_file(zones_file)
        return zones_gdf.to_crs('EPSG:4326')  # Ensure WGS84

    def load_poi_data(self, poi_name: str, trip_type: str) -> pd.DataFrame:
        """Load data for a specific POI and trip type"""
        filename = f"{poi_name.lower().replace('-', '_')}_{trip_type}_trips.csv"
        file_path = self.output_dir / "dashboard_data" / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"No data file found for {poi_name} at {file_path}")
        
        df = pd.read_csv(file_path)
        # Ensure tract is string type for consistent merging
        df['tract'] = df['tract'].astype(str)
        return df

    def calculate_distances(self, poi_location: Dict) -> pd.Series:
        """Calculate distances from POI to all zone centroids in kilometers"""
        poi_point = Point(poi_location['lon'], poi_location['lat'])
        self.zones_gdf['centroid'] = self.zones_gdf.geometry.centroid
        
        # Calculate distances and convert to kilometers
        distances = self.zones_gdf.apply(
            lambda row: poi_point.distance(row['centroid']) * 111,  # Approximate degree to km conversion
            axis=1
        )
        return distances

    def analyze_catchment_area(self, poi_name: str) -> Dict:
        """Analyze catchment area characteristics for a POI"""
        try:
            # Get POI location
            poi_location = next(poi for poi in POI_LOCATIONS if poi['name'] == poi_name)
            
            # Load trip data
            trips_df = self.load_poi_data(poi_name, 'inbound')
            
            # Calculate distances
            self.zones_gdf['distance'] = self.calculate_distances(poi_location)
            
            # Convert zone index to string for consistent merging
            self.zones_gdf.index = self.zones_gdf.index.astype(str)
            
            # Merge distances with trip data
            analysis_df = trips_df.merge(
                self.zones_gdf[['distance']],
                left_on='tract',
                right_index=True,
                how='left'
            )
            
            # Calculate weighted statistics
            total_trips = analysis_df['total_trips'].sum()
            weighted_avg_distance = np.average(
                analysis_df['distance'],
                weights=analysis_df['total_trips']
            )
            
            # Calculate cumulative percentage of trips by distance
            analysis_df = analysis_df.sort_values('distance')
            analysis_df['cumulative_trips'] = analysis_df['total_trips'].cumsum()
            analysis_df['cumulative_pct'] = (analysis_df['cumulative_trips'] / total_trips) * 100
            
            # Find distance thresholds
            d50 = analysis_df[analysis_df['cumulative_pct'] >= 50]['distance'].iloc[0]
            d75 = analysis_df[analysis_df['cumulative_pct'] >= 75]['distance'].iloc[0]
            d90 = analysis_df[analysis_df['cumulative_pct'] >= 90]['distance'].iloc[0]
            
            return {
                'total_trips': total_trips,
                'avg_distance': weighted_avg_distance,
                'median_distance': d50,
                'p75_distance': d75,
                'p90_distance': d90,
                'unique_zones': len(trips_df)
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing {poi_name}: {str(e)}")
            return {}

    def analyze_all_pois(self):
        """Analyze catchment areas for all POIs"""
        results = {}
        for poi in POI_LOCATIONS:
            self.logger.info(f"\nAnalyzing catchment area for {poi['name']}")
            results[poi['name']] = self.analyze_catchment_area(poi['name'])
        
        # Save results
        pd.DataFrame(results).to_csv(self.stats_dir / "catchment_analysis.csv")
        return results

def main():
    project_root = Path(__file__).parent.parent  # Adjust based on your project structure
    analyzer = SpatialAnalyzer(project_root)
    results = analyzer.analyze_all_pois()
    
    # Print summary
    print("\nCatchment Area Analysis Summary:")
    for poi_name, metrics in results.items():
        if metrics:
            print(f"\n{poi_name}:")
            print(f"Total trips: {metrics['total_trips']:,.0f}")
            print(f"Average distance: {metrics['avg_distance']:.1f} km")
            print(f"50% of trips within: {metrics['median_distance']:.1f} km")
            print(f"75% of trips within: {metrics['p75_distance']:.1f} km")
            print(f"90% of trips within: {metrics['p90_distance']:.1f} km")

if __name__ == "__main__":
    main()