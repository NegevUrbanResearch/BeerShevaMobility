import sys
from pathlib import Path
# Add the project root to Python path
sys.path.append(str(Path(__file__).parent.parent.parent))

from EDA.statistics.analyze_patterns import MobilityPatternAnalyzer
import json
import pandas as pd
import numpy as np


class TemporalVisualizationGenerator:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.output_dir = self.project_root / "output" / "visualizations"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_template(self):
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Temporal Trip Patterns</title>
    <meta charset="utf-8">
    <!-- Core React -->
    <script src="https://unpkg.com/react@17.0.2/umd/react.development.js"></script>
    <script src="https://unpkg.com/react-dom@17.0.2/umd/react-dom.development.js"></script>
    <!-- Recharts Dependencies -->
    <script src="https://unpkg.com/prop-types@15.8.1/prop-types.min.js"></script>
    <script src="https://unpkg.com/recharts@2.10.3/umd/Recharts.js"></script>
    <!-- Babel -->
    <script src="https://unpkg.com/@babel/standalone@7.23.6/babel.min.js"></script>
    <style>
        body {
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
            background: #111;
            color: #fff;
        }
        .card {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            max-width: 900px;
            margin: 0 auto;
        }
        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            margin-top: 10px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            font-size: 0.85em;
        }
        .legend-color {
            width: 12px;
            height: 12px;
            margin-right: 4px;
            border-radius: 2px;
        }
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
        const { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } = Recharts;
        
        const temporalData = DATA_PLACEHOLDER;
        
        const poiColors = {
            'Ben-Gurion-University': '#FF6B6B',
            'Soroka-Medical-Center': '#4ECDC4',
            'Gav-Yam-High-Tech-Park': '#FFE66D',
            'Beer-Sheva-Comparisons': '#96CEB4'
        };

        const CustomTooltip = ({ active, payload, label }) => {
            if (active && payload && payload.length) {
                return (
                    <div style={{
                        background: '#1a1a1a',
                        border: '1px solid #333',
                        padding: '8px',
                        fontSize: '0.85em'
                    }}>
                        <p style={{ margin: '0 0 5px' }}><strong>{label}</strong></p>
                        {payload.map((entry, index) => (
                            <p key={index} style={{ 
                                margin: '2px 0',
                                color: entry.color
                            }}>
                                {entry.name.replace(/-/g, ' ')}: {entry.value.toFixed(1)}%
                            </p>
                        ))}
                    </div>
                );
            }
            return null;
        };

        const App = () => {
            return (
                <div className="card">
                    <h2 style={{ textAlign: 'center', marginBottom: '20px' }}>
                        Temporal Trip Patterns
                    </h2>
                    <ResponsiveContainer width="100%" height={400}>
                        <LineChart
                            data={temporalData}
                            margin={{
                                top: 5,
                                right: 30,
                                left: 20,
                                bottom: 45  // Increased bottom margin further
                            }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                            <XAxis 
                                dataKey="hour"
                                stroke="#fff"
                                tick={{ fill: '#fff' }}
                                label={{
                                    value: 'Hour of Day',
                                    position: 'bottom',
                                    fill: '#fff',
                                    offset: 10  // Increased offset from x-axis
                                }}
                            />
                            <YAxis
                                stroke="#fff"
                                tick={{ fill: '#fff' }}
                                label={{
                                    value: 'Trip Distribution (%)',
                                    angle: -90,
                                    position: 'insideLeft',
                                    fill: '#fff',
                                    offset: 0
                                }}
                            />
                            <Tooltip content={<CustomTooltip />} />
                            {Object.entries(poiColors).map(([poi, color]) => (
                                <Line
                                    key={poi}
                                    type="monotone"
                                    dataKey={poi}
                                    stroke={color}
                                    strokeWidth={2}
                                    dot={false}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                    <div className="legend">
                        {Object.entries(poiColors).map(([poi, color]) => (
                            <div key={poi} className="legend-item">
                                <div className="legend-color" style={{ background: color }} />
                                <span>{poi.replace(/-/g, ' ')}</span>
                            </div>
                        ))}
                    </div>
                </div>
            );
        };

        ReactDOM.render(<App />, document.getElementById('root'));
    </script>
</body>
</html>'''

    def process_temporal_data(self, analyzer):
        """Process temporal data for visualization"""
        print("\nProcessing temporal data for visualization...")
        temporal_data = []
        
        # Get all possible hours
        hours = [f"{i:02d}:00" for i in range(24)]
        
        # Get list of all temporal data files
        data_files = list(analyzer.data_dir.glob("*_inbound_temporal.csv"))
        if not data_files:
            raise FileNotFoundError("No temporal data files found")
        
        # Get focus POI file names for exclusion
        focus_poi_files = {f"{poi.lower().replace('-', '_')}_inbound_temporal.csv" 
                          for poi in analyzer.focus_pois}
        
        # Filter out focus POIs from the general POI list
        general_poi_files = [f for f in data_files if f.name not in focus_poi_files]
        print(f"\nFound {len(data_files)} total temporal files:")
        print(f"- {len(focus_poi_files)} focus POIs: {', '.join(focus_poi_files)}")
        print(f"- {len(general_poi_files)} general POIs: {', '.join(f.name for f in general_poi_files)}")
        
        # Process each hour
        for hour in hours:
            hour_data = {'hour': hour}
            hour_idx = int(hour.split(':')[0])
            
            # Process focus POIs first
            for poi in analyzer.focus_pois:
                try:
                    file_name = f"{poi.lower().replace('-', '_')}_inbound_temporal.csv"
                    file_path = analyzer.data_dir / file_name
                    
                    if file_path.exists():
                        temporal_df = pd.read_csv(file_path)
                        row = temporal_df.loc[temporal_df['hour'] == hour_idx]
                        
                        if not row.empty:
                            # Use the 'all' distribution column
                            percentage = row['all_dist'].iloc[0]
                            print(f"Focus POI: {poi}, Hour: {hour}, Percentage: {percentage:.3f}")
                        else:
                            percentage = 0.0
                    else:
                        percentage = 0.0
                        print(f"No temporal file found for {poi}")
                    
                    hour_data[poi] = float(percentage)
                    
                except Exception as e:
                    print(f"Error processing {poi} for hour {hour}: {str(e)}")
                    hour_data[poi] = 0.0
            
            # Process general POIs for city-wide average
            general_poi_percentages = []
            for file_path in general_poi_files:
                try:
                    temporal_df = pd.read_csv(file_path)
                    row = temporal_df.loc[temporal_df['hour'] == hour_idx]
                    
                    if not row.empty:
                        percentage = row['all_dist'].iloc[0]
                        general_poi_percentages.append(percentage)
                        print(f"General POI: {file_path.stem}, Hour: {hour}, Percentage: {percentage:.3f}")
                except Exception as e:
                    print(f"Error processing general POI {file_path.stem} for hour {hour}: {str(e)}")
            
            # Calculate Beer Sheva Average
            if general_poi_percentages:
                hour_data['Beer-Sheva-Comparisons'] = float(np.mean(general_poi_percentages))
                print(f"Hour {hour} - City Average: {hour_data['Beer-Sheva-Comparisons']:.3f} "
                      f"(from {len(general_poi_percentages)} general POIs)")
            else:
                hour_data['Beer-Sheva-Comparisons'] = 0.0
            
            temporal_data.append(hour_data)
        
        # Verify distributions sum to 1.0 (100%)
        print("\nVerifying distributions:")
        for poi in analyzer.focus_pois + ['Beer-Sheva-Comparisons']:
            total = sum(hour_data[poi] for hour_data in temporal_data)
            print(f"{poi} total: {total:.3f}")
            if not np.isclose(total, 1.0, atol=0.01):
                print(f"Warning: {poi} distribution sum ({total:.3f}) is not close to 1.0")
        
        # Convert to percentages for visualization
        for hour_data in temporal_data:
            for key in hour_data:
                if key != 'hour':
                    hour_data[key] *= 100
        
        print(f"\nProcessed {len(temporal_data)} hourly data points")
        if temporal_data:
            print("\nSample data points:")
            for i in range(min(3, len(temporal_data))):
                print(f"Hour {temporal_data[i]['hour']}:")
                for key, value in temporal_data[i].items():
                    if key != 'hour':
                        print(f"  {key}: {value:.1f}%")
        
        return temporal_data

    def generate_visualization(self, analyzer):
        """Generate temporal pattern visualization"""
        print("\nGenerating temporal visualization...")
        
        try:
            # Process the data
            temporal_data = self.process_temporal_data(analyzer)
            
            # Generate HTML with processed data
            html_content = self._get_template()
            html_content = html_content.replace('DATA_PLACEHOLDER', json.dumps(temporal_data))
            
            output_file = self.output_dir / "temporal_visualization.html"
            print(f"Writing visualization to: {output_file}")
            
            with open(output_file, 'w') as f:
                f.write(html_content)
                
            print(f"Successfully generated temporal visualization")
            
        except Exception as e:
            print(f"Error generating visualization: {str(e)}")
            raise
        
    def export_temporal_analysis(self, temporal_data):
        """
        Export temporal data with additional analysis metrics for LLM annotation.
        
        Args:
            temporal_data (list): List of dictionaries containing hourly temporal patterns
        """
        print("\nExporting temporal analysis for LLM annotation...")
        
        # Convert temporal_data to DataFrame for easier analysis
        df = pd.DataFrame(temporal_data)
        
        # Add time period labels
        def get_time_period(hour):
            hour = int(hour.split(':')[0])
            if 5 <= hour < 9:
                return 'Morning Rush'
            elif 9 <= hour < 12:
                return 'Morning'
            elif 12 <= hour < 14:
                return 'Lunch'
            elif 14 <= hour < 17:
                return 'Afternoon'
            elif 17 <= hour < 20:
                return 'Evening Rush'
            elif 20 <= hour < 23:
                return 'Evening'
            else:
                return 'Night'
        
        df['time_period'] = df['hour'].apply(get_time_period)
        
        # Calculate additional metrics
        pois = [col for col in df.columns if col not in ['hour', 'time_period']]
        
        analysis_rows = []
        for idx, row in df.iterrows():
            hour = row['hour']
            time_period = row['time_period']
            
            # Basic data
            analysis_row = {
                'hour': hour,
                'time_period': time_period
            }
            
            # Add raw percentages for each POI
            for poi in pois:
                analysis_row[f'{poi}_pct'] = row[poi]
            
            # Find dominant POI for this hour
            max_poi = max(pois, key=lambda x: row[x])
            analysis_row['dominant_poi'] = max_poi
            analysis_row['dominant_poi_pct'] = row[max_poi]
            
            # Calculate relative activity level
            hour_total = sum(row[poi] for poi in pois)
            analysis_row['total_activity'] = hour_total
            
            # Calculate activity ratios compared to city average
            for poi in pois:
                if poi != 'Beer-Sheva-Comparisons' and row['Beer-Sheva-Comparisons'] != 0:
                    ratio = row[poi] / row['Beer-Sheva-Comparisons']
                    analysis_row[f'{poi}_vs_city_ratio'] = ratio
            
            analysis_rows.append(analysis_row)
        
        # Convert to DataFrame
        analysis_df = pd.DataFrame(analysis_rows)
        
        # Add hour-over-hour changes
        for poi in pois:
            analysis_df[f'{poi}_change'] = analysis_df[f'{poi}_pct'].pct_change()
        
        # Calculate peak hours for each POI
        for poi in pois:
            peak_hour = analysis_df.loc[analysis_df[f'{poi}_pct'].idxmax(), 'hour']
            peak_pct = analysis_df[f'{poi}_pct'].max()
            print(f"Peak hour for {poi}: {peak_hour} ({peak_pct:.1f}%)")
        
        # Export to CSV
        output_file = self.output_dir / "temporal_analysis.csv"
        analysis_df.to_csv(output_file, index=False)
        print(f"\nExported temporal analysis to: {output_file}")
        
        # Print sample of the analysis
        print("\nSample of exported analysis:")
        print(analysis_df[['hour', 'time_period', 'dominant_poi', 'total_activity']].head())
        
        return output_file    

def main():
    """Main function to run temporal pattern analysis"""
    try:
        print("Starting temporal pattern analysis...")
        
        # Initialize analyzer and generator
        analyzer = MobilityPatternAnalyzer()
        generator = TemporalVisualizationGenerator()
        
        # Generate visualization and get temporal data
        temporal_data = generator.process_temporal_data(analyzer)
        generator.generate_visualization(analyzer)
        
        # Export temporal analysis to CSV
        analysis_file = generator.export_temporal_analysis(temporal_data)
        print(f"\nAnalysis exported to: {analysis_file}")
        
        print("\nProcess completed successfully!")
        
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        raise


if __name__ == "__main__":
    main()