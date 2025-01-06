import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
import logging
from typing import Dict
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.data_standards import DataStandardizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InnovationDistrictAnalyzer:
    def __init__(self):
        self.base_dir = Path("/Users/noamgal/DSProjects/BeerShevaMobility/EDA")
        self.data_dir = self.base_dir / "output" / "dashboard_data"
        self.output_dir = self.base_dir / "output" / "analysis"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize DataStandardizer
        self.standardizer = DataStandardizer()

        # Define innovation district POIs using standardized names
        self.innovation_district_pois = [
            'Ben-Gurion-University',
            'Soroka-Medical-Center',
            'Gav-Yam-High-Tech-Park'
        ]
        
        # Get all POIs except innovation district ones for city averages
        self.other_pois = [
            poi for poi in self.standardizer.get_all_standard_poi_names()
            if poi not in self.innovation_district_pois
        ]
        
        # Use the original file names (keys) from DataStandardizer
        self.file_name_mapping = {
            'Ben-Gurion-University': 'BGU',
            'Soroka-Medical-Center': 'Soroka Hospital',
            'Gav-Yam-High-Tech-Park': 'Gev Yam',
            'Emek-Sara-Industrial-Area': 'Emek Shara industrial area',
            'Omer-Industrial-Area': 'Omer industrial area',
            'HaNegev-Mall': 'HaNegev Mall',
            'BIG': 'BIG',
            'Assuta-Hospital': 'Assuta Hospital',
            'SCE': 'Sami Shimon collage',
            'Grand-Kenyon': 'Grand Kenyon',
            'Yes-Planet': 'Yes Planet',
            'Kaye-College': 'K collage',
            'Ramat-Hovav-Industrial-Zone': 'Ramat Hovav Industry'
        }

    def load_and_merge_data(self) -> pd.DataFrame:
        """Load and merge all POI data with zones"""
        logger.info("Loading zones data...")
        zones = gpd.read_file(self.data_dir / "zones.geojson")
        
        all_data = []
        
        # Load both innovation district and other POIs
        for poi in self.innovation_district_pois + self.other_pois:
            file_name = self.file_name_mapping.get(poi, poi)
            # Convert spaces to underscores for filename
            file_name = file_name.replace(' ', '_')
            
            for direction in ['inbound', 'outbound']:
                try:
                    file_path = self.data_dir / f"{file_name}_{direction}_trips.csv"
                    if file_path.exists():
                        df = pd.read_csv(file_path)
                        df = df.merge(
                            zones[['YISHUV_STAT11', 'SHEM_YISHUV_ENGLISH']], 
                            left_on='tract', 
                            right_on='YISHUV_STAT11',
                            how='left'
                        )
                        df['poi'] = poi
                        df['direction'] = direction
                        df['is_innovation_district'] = poi in self.innovation_district_pois
                        all_data.append(df)
                        logger.info(f"Loaded {poi} ({file_name}) {direction} data: {len(df)} records")
                    else:
                        logger.warning(f"File not found: {file_path}")
                except Exception as e:
                    logger.error(f"Error loading {poi} {direction}: {str(e)}")
        
        if not all_data:
            raise ValueError("No data loaded for any POI")
            
        return pd.concat(all_data, ignore_index=True)

    def analyze_city_patterns(self, df: pd.DataFrame) -> Dict:
        """Analyze patterns for each city with focus on innovation district"""
        city_stats = []
        beer_sheva_data = None
        
        for city, city_data in df.groupby('SHEM_YISHUV_ENGLISH'):
            if pd.isna(city):
                continue
                
            # Calculate total trips
            total_trips = city_data['total_trips'].sum()
            
            # Calculate POI distribution
            poi_trips = city_data.groupby('poi')['total_trips'].sum()
            poi_shares = poi_trips / total_trips
            
            # Calculate raw trips for each innovation district POI
            raw_trips = {
                'BGU_trips': poi_trips.get('Ben-Gurion-University', 0),
                'Soroka_trips': poi_trips.get('Soroka-Medical-Center', 0),
                'GavYam_trips': poi_trips.get('Gav-Yam-High-Tech-Park', 0),
                'ID_trips': poi_trips.get('Soroka-Medical-Center', 0) + poi_trips.get('Ben-Gurion-University', 0) + poi_trips.get('Gav-Yam-High-Tech-Park', 0)
            }
            
            # Calculate innovation share
            innovation_share = sum(poi_shares.get(poi, 0) 
                                for poi in self.innovation_district_pois)
            
            # Mode shares calculation
            mode_cols = [col for col in city_data.columns if col.startswith('mode_')]
            mode_shares = {}
            
            for mode in mode_cols:
                mode_shares[mode.replace('mode_', '')] = (
                    (city_data[mode] * city_data['total_trips']).sum() / 
                    city_data['total_trips'].sum()
                )
            
            stats = {
                'city': city,
                'total_trips': total_trips,
                'innovation_share': innovation_share,
                'poi_distribution': poi_shares.to_dict(),
                'mode_shares': mode_shares,
                **raw_trips  # Add raw trip counts to stats
            }
            
            city_stats.append(stats)
            
            if city.lower() in ['beer sheva', 'be\'er sheva', 'beer-sheva']:
                beer_sheva_data = stats
        
        # Create DataFrame and sort
        results_df = pd.DataFrame(city_stats)
        results_df = results_df.sort_values('total_trips', ascending=False)
        
        return {
            'city_data': results_df,
            'beer_sheva_stats': beer_sheva_data
        }

    def run_analysis(self):
        """Run the complete analysis and save results"""
        logger.info("Starting innovation district mobility analysis...")
        
        # Load and process data
        all_data = self.load_and_merge_data()
        
        # Run analysis
        results = self.analyze_city_patterns(all_data)
        
        # Save results with raw trip counts
        top_15_df = results['city_data'].head(15)
        
        # Rearrange columns for better readability
        columns_order = [
            'city', 'total_trips', 'innovation_share',
            'BGU_trips', 'Soroka_trips', 'GavYam_trips',
            'poi_distribution', 'mode_shares'
        ]
        top_15_df = top_15_df[columns_order]
        
        top_15_df.to_csv(self.output_dir / 'top_15_cities_innovation_district.csv', index=False)
        
        return results

    def run_analysis(self):
        """Run the complete analysis and save results"""
        logger.info("Starting innovation district mobility analysis...")
        
        # Load and process data
        all_data = self.load_and_merge_data()
        
        # Run analysis
        results = self.analyze_city_patterns(all_data)
        
        # Save results
        top_15_df = results['city_data'].head(15)
        top_15_df.to_csv(self.output_dir / 'top_15_cities_innovation_district.csv', index=False)
        print('results saved to', self.output_dir / 'top_15_cities_innovation_district.csv')
        return results

if __name__ == "__main__":
    analyzer = InnovationDistrictAnalyzer()
    results = analyzer.run_analysis()

