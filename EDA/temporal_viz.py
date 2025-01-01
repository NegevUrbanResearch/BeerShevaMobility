from pathlib import Path
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
            'Beer-Sheva-Average': '#96CEB4'
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
                hour_data['Beer-Sheva-Average'] = float(np.mean(general_poi_percentages))
                print(f"Hour {hour} - City Average: {hour_data['Beer-Sheva-Average']:.3f} "
                      f"(from {len(general_poi_percentages)} general POIs)")
            else:
                hour_data['Beer-Sheva-Average'] = 0.0
            
            temporal_data.append(hour_data)
        
        # Verify distributions sum to 1.0 (100%)
        print("\nVerifying distributions:")
        for poi in analyzer.focus_pois + ['Beer-Sheva-Average']:
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

if __name__ == "__main__":
    from analyze_patterns import MobilityPatternAnalyzer
    
    analyzer = MobilityPatternAnalyzer()
    generator = TemporalVisualizationGenerator()
    generator.generate_visualization(analyzer)