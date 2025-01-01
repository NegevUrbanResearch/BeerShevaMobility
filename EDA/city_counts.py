import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
import logging
from typing import Dict
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
            
            # Try multiple variations of POI names
            bgu_variants = ['BGU', 'Ben-Gurion-University', 'Ben Gurion', 'Ben_Gurion']
            gav_yam_variants = ['Gav-Yam-High-Tech-Park', 'Gev Yam', 'Gav Yam', 'Gev-Yam']
            
            # Calculate innovation share using standardized names
            bgu_share = sum(poi_shares.get(self.standardizer.standardize_poi_name(var), 0) 
                           for var in bgu_variants)
            gav_yam_share = sum(poi_shares.get(self.standardizer.standardize_poi_name(var), 0) 
                              for var in gav_yam_variants)
            innovation_share = bgu_share + gav_yam_share
            
            # Mode shares - fixed calculation
            mode_cols = [col for col in city_data.columns if col.startswith('mode_')]
            mode_shares = {}
            for mode in mode_cols:
                # Calculate weighted mode share
                mode_trips = (city_data[mode] * city_data['total_trips']).sum()
                mode_share = mode_trips / total_trips if total_trips > 0 else 0
                mode_shares[mode.replace('mode_', '')] = mode_share * 100  # Convert to percentage
            
            stats = {
                'city': city,
                'total_trips': total_trips,
                'innovation_share': innovation_share,
                'poi_distribution': poi_shares.to_dict(),
                'mode_shares': mode_shares
            }
            
            city_stats.append(stats)
            
            # Store Beer Sheva data separately
            if city.lower() in ['beer sheva', 'be\'er sheva', 'beer-sheva']:
                beer_sheva_data = stats
        
        # Create DataFrame and sort
        results_df = pd.DataFrame(city_stats)
        results_df = results_df.sort_values('total_trips', ascending=False)
        
        return {
            'city_data': results_df,
            'narrative': self._generate_narrative(results_df, beer_sheva_data),
            'beer_sheva_stats': beer_sheva_data
        }

    def _generate_narrative(self, df: pd.DataFrame, beer_sheva_stats: Dict) -> str:
        """Generate narrative focusing on city mobility patterns"""
        top_15 = df.head(15)
        narrative = ["=== City Mobility Patterns Analysis ===\n"]
        
        # Major cities section
        narrative.append("Major Cities Trip Analysis")
        narrative.append("------------------------\n")
        
        for _, row in top_15.iterrows():
            poi_dist = row['poi_distribution']
            
            city_text = (
                f"\n{row['city']}:"
                f"\n  - Total trips: {row['total_trips']:,.1f}"
                f"\n  - POI Distribution:"
                f"\n    * BGU: {poi_dist.get('Ben-Gurion-University', 0)*100:.1f}%"
                f"\n    * Soroka: {poi_dist.get('Soroka-Medical-Center', 0)*100:.1f}%"
                f"\n    * Gav Yam: {poi_dist.get('Gav-Yam-High-Tech-Park', 0)*100:.1f}%"
                f"\n    * BIG: {poi_dist.get('BIG', 0)*100:.1f}%"
                f"\n    * HaNegev Mall: {poi_dist.get('HaNegev-Mall', 0)*100:.1f}%"
                f"\n    * Emek Sara: {poi_dist.get('Emek-Sara-Industrial-Area', 0)*100:.1f}%"
            )
            
            # Add mode split if available
            if row.get('mode_shares'):
                city_text += "\n  - Mode Split:"
                for mode, share in row['mode_shares'].items():
                    city_text += f"\n    * {mode}: {share:.1f}%"
            
            narrative.append(city_text)
        
        return "\n".join(narrative)

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
        
        # Save narrative report
        with open(self.output_dir / 'innovation_district_analysis.txt', 'w') as f:
            f.write(results['narrative'])
        
        logger.info("Analysis complete. Results saved to output directory.")
        print("\nNarrative Report:")
        print(results['narrative'])
        return results

if __name__ == "__main__":
    analyzer = InnovationDistrictAnalyzer()
    results = analyzer.run_analysis()