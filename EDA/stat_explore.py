import pandas as pd
import numpy as np
from pathlib import Path
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from scipy import stats
import json

@dataclass
class POIData:
    inbound: pd.DataFrame
    outbound: pd.DataFrame
    name: str
    
class BasicMobilityAnalyzer:
    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.poi_data: Dict[str, POIData] = {}
        
    def load_all_data(self, poi_names: List[str]) -> None:
        """Load data once for all POIs"""
        for poi in poi_names:
            inbound = pd.read_csv(self.data_dir / f"{poi}_inbound_trips.csv")
            outbound = pd.read_csv(self.data_dir / f"{poi}_outbound_trips.csv")
            self.poi_data[poi] = POIData(inbound=inbound, outbound=outbound, name=poi)

    def analyze_temporal_patterns(self) -> Dict:
        """Analyze temporal patterns including:
        - Peak hours
        - Temporal distributions
        - POI correlations
        """
        patterns = {}
        
        for poi_name, data in self.poi_data.items():
            print(f"\nAnalyzing temporal patterns for {poi_name}")
            
            time_cols = [col for col in data.inbound.columns if col.startswith('arrival_')]
            if not time_cols:
                print(f"No temporal data found for {poi_name}")
                continue
            
            # Calculate temporal distributions
            inbound_dist = self._calculate_temporal_distribution(
                data.inbound, time_cols
            )
            outbound_dist = self._calculate_temporal_distribution(
                data.outbound, time_cols
            )
            
            # Find peaks
            patterns[poi_name] = {
                'inbound': {
                    'distribution': inbound_dist.to_dict(),
                    'peaks': self._find_peaks(inbound_dist)
                },
                'outbound': {
                    'distribution': outbound_dist.to_dict(),
                    'peaks': self._find_peaks(outbound_dist)
                }
            }
        
        # Calculate correlations between POIs
        patterns['correlations'] = self._calculate_poi_correlations()
        
        return patterns
    
    def analyze_mode_patterns(self) -> Dict:
        """Analyze transportation mode patterns including:
        - Mode shares
        - Mode preferences by time of day
        - Mode choice correlations with distance
        """
        patterns = {}
        for poi_name, data in self.poi_data.items():
            mode_cols = [col for col in data.inbound.columns if col.startswith('mode_')]
            
            # Calculate basic mode shares
            in_modes = self._calculate_mode_shares(data.inbound, mode_cols)
            out_modes = self._calculate_mode_shares(data.outbound, mode_cols)
            
            # Analyze mode choices by time period
            time_cols = [col for col in data.inbound.columns if col.startswith('arrival_')]
            mode_temporal = self._analyze_mode_temporal_patterns(data.inbound, mode_cols, time_cols)
            
            patterns[poi_name] = {
                'mode_shares': {
                    'inbound': in_modes,
                    'outbound': out_modes
                },
                'mode_temporal_patterns': mode_temporal,
                'mode_diversity': self._calculate_mode_diversity(data.inbound, mode_cols)
            }
        
        return patterns
    
    def analyze_trip_purposes(self) -> Dict:
        """Analyze trip purpose patterns including:
        - Purpose distributions
        - Purpose-mode relationships
        - Purpose-time relationships
        """
        patterns = {}
        for poi_name, data in self.poi_data.items():
            purpose_cols = [col for col in data.inbound.columns if col.startswith('purpose_')]
            mode_cols = [col for col in data.inbound.columns if col.startswith('mode_')]
            
            # Calculate purpose distributions
            purpose_dist = self._calculate_purpose_distribution(data.inbound, purpose_cols)
            
            # Analyze purpose-mode relationships
            purpose_mode = self._analyze_purpose_mode_relationship(
                data.inbound, purpose_cols, mode_cols
            )
            
            patterns[poi_name] = {
                'purpose_distribution': purpose_dist,
                'purpose_mode_relationship': purpose_mode,
                'purpose_temporal': self._analyze_purpose_temporal_patterns(data.inbound)
            }
            
        return patterns

    def _calculate_temporal_distribution(self, df: pd.DataFrame, time_cols: List[str]) -> pd.Series:
        """Calculate weighted temporal distribution"""
        print("\nCalculating temporal distribution")
        print("Time columns:", time_cols)
        
        try:
            # Get raw counts by multiplying percentages by total trips
            hourly_counts = df[time_cols].multiply(df['total_trips'], axis=0)
            
            # Sum up total trips for each hour
            total_by_hour = hourly_counts.sum()
            
            # Calculate the distribution (ensure it sums to 100%)
            if total_by_hour.sum() > 0:
                distribution = total_by_hour / total_by_hour.sum()
                
                print("\nTemporal distribution summary:")
                print(f"Total trips processed: {total_by_hour.sum():.1f}")
                print("\nTop 5 peak hours:")
                top_hours = distribution.sort_values(ascending=False).head()
                for hour, value in top_hours.items():
                    print(f"{hour}: {value*100:.1f}%")
                    
                return distribution
            else:
                print("Warning: No trips found in temporal data")
                return pd.Series(0, index=time_cols)
                
        except Exception as e:
            print(f"Error in temporal distribution calculation: {str(e)}")
            print("Input data sample:")
            print(df[time_cols + ['total_trips']].head())
            return pd.Series(0, index=time_cols)

    def _find_peaks(self, distribution: pd.Series, threshold: float = 0.1) -> List[Dict]:
        """Find primary and secondary peaks in temporal distribution"""
        peaks = []
        if distribution.empty:
            return peaks
            
        sorted_dist = distribution.sort_values(ascending=False)
        primary_peak = sorted_dist.iloc[0]
        
        for hour, value in sorted_dist.items():
            if value >= threshold * primary_peak:  # Within threshold of primary peak
                peaks.append({
                    'hour': hour.replace('arrival_', ''),
                    'percentage': float(value)  # Convert numpy float to Python float for JSON
                })
        
        return peaks

    def _calculate_poi_correlations(self) -> Dict:
        """Calculate temporal correlations between POIs"""
        correlations = {}
        poi_names = list(self.poi_data.keys())
        
        for i, poi1 in enumerate(poi_names):
            for poi2 in poi_names[i+1:]:
                time_cols = [col for col in self.poi_data[poi1].inbound.columns 
                           if col.startswith('arrival_')]
                
                if not time_cols:
                    print(f"Warning: No time columns found for {poi1} or {poi2}")
                    continue
                    
                try:
                    dist1 = self._calculate_temporal_distribution(
                        self.poi_data[poi1].inbound, time_cols
                    )
                    dist2 = self._calculate_temporal_distribution(
                        self.poi_data[poi2].inbound, time_cols
                    )
                    
                    if not dist1.empty and not dist2.empty:
                        correlation = dist1.corr(dist2)
                        correlations[f"{poi1}_vs_{poi2}"] = float(correlation)  # Convert numpy float to Python float
                except Exception as e:
                    print(f"Error calculating correlation between {poi1} and {poi2}: {str(e)}")
                    continue
        
        return correlations

    def generate_report(self):
        """Generate comprehensive analysis report"""
        temporal = self.analyze_temporal_patterns()
        mode = self.analyze_mode_patterns()
        purpose = self.analyze_trip_purposes()
        
        report = {
            'temporal_patterns': temporal,
            'mode_patterns': mode,
            'trip_purposes': purpose
        }
        
        # Save to JSON
        with open(self.output_dir / 'basic_analysis_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        return report

    def _calculate_mode_shares(self, df: pd.DataFrame, mode_cols: List[str]) -> Dict:
        """Calculate the share of each transportation mode"""
        # Debug print
        print("Calculating mode shares")
        print("Mode columns:", mode_cols)
        print("Sample data:", df[mode_cols].head())
        
        try:
            # Ensure we're using the correct mode column names
            valid_mode_cols = [col for col in mode_cols if col in df.columns]
            if not valid_mode_cols:
                print("Warning: No valid mode columns found")
                return {}
                
            mode_totals = df[valid_mode_cols].multiply(df['total_trips'], axis=0).sum()
            total_trips = df['total_trips'].sum()
            
            # Convert to standard format
            mode_shares = (mode_totals / total_trips).to_dict()
            return {key.replace('mode_', ''): value for key, value in mode_shares.items()}
        except Exception as e:
            print(f"Error in mode share calculation: {str(e)}")
            return {}

    def _analyze_mode_temporal_patterns(self, df: pd.DataFrame, 
                                     mode_cols: List[str], 
                                     time_cols: List[str]) -> Dict:
        """Analyze how mode choices vary by time of day"""
        patterns = {}
        for time in time_cols:
            time_slice = df[df[time] > 0]
            if len(time_slice) > 0:
                mode_shares = self._calculate_mode_shares(time_slice, mode_cols)
                patterns[time.replace('arrival_', '')] = mode_shares
        return patterns

    def _calculate_mode_diversity(self, df: pd.DataFrame, mode_cols: List[str]) -> float:
        """Calculate mode choice diversity using Shannon entropy"""
        mode_shares = self._calculate_mode_shares(df, mode_cols)
        shares = np.array(list(mode_shares.values()))
        # Remove zero shares to avoid log(0)
        shares = shares[shares > 0]
        return float(stats.entropy(shares))

    def _calculate_purpose_distribution(self, df: pd.DataFrame, purpose_cols: List[str]) -> Dict:
        """Calculate the distribution of trip purposes"""
        purpose_totals = df[purpose_cols].multiply(df['total_trips'], axis=0).sum()
        total_trips = df['total_trips'].sum()
        return (purpose_totals / total_trips).to_dict()

    def _analyze_purpose_mode_relationship(self, df: pd.DataFrame, 
                                         purpose_cols: List[str], 
                                         mode_cols: List[str]) -> Dict:
        """Analyze the relationship between trip purposes and mode choices"""
        relationships = {}
        for purpose in purpose_cols:
            purpose_trips = df[df[purpose] > 0]
            if len(purpose_trips) > 0:
                mode_shares = self._calculate_mode_shares(purpose_trips, mode_cols)
                relationships[purpose.replace('purpose_', '')] = mode_shares
        return relationships

    def _analyze_purpose_temporal_patterns(self, df: pd.DataFrame) -> Dict:
        """Analyze how trip purposes vary by time of day"""
        time_cols = [col for col in df.columns if col.startswith('arrival_')]
        purpose_cols = [col for col in df.columns if col.startswith('purpose_')]
        
        patterns = {}
        for time in time_cols:
            time_slice = df[df[time] > 0]
            if len(time_slice) > 0:
                purpose_dist = self._calculate_purpose_distribution(time_slice, purpose_cols)
                patterns[time.replace('arrival_', '')] = purpose_dist
        return patterns

if __name__ == "__main__":
    current_dir = Path(__file__).parent
    data_dir = current_dir / "output/dashboard_data"
    output_dir = current_dir / "output/analysis"
    
    analyzer = BasicMobilityAnalyzer(data_dir, output_dir)
    analyzer.load_all_data(['BGU', 'Soroka_Hospital'])
    report = analyzer.generate_report()