import sys
from pathlib import Path
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from config import OUTPUT_DIR, DATA_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MobilityPatternAnalyzer:
    """Simplified analyzer class for temporal visualizations"""
    def __init__(self, data_dir: Optional[Path] = None):
        # Use OUTPUT_DIR from config instead of local data directory
        self.data_dir = data_dir or Path(OUTPUT_DIR)
        self.focus_pois = [
            'Ben-Gurion-University',
            'Soroka-Medical-Center',
            'Gav-Yam-High-Tech-Park'
        ]

class TemporalVisualizationGenerator:
    def __init__(self):
        self.project_root = Path(__file__).parent
        # Use OUTPUT_DIR for both input and output
        self.output_dir = Path(OUTPUT_DIR) / "visualizations"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Expected column names
        self.required_columns = ['hour', 'all_dist']
        
        # Validation thresholds
        self.distribution_sum_tolerance = 0.01  # 1% tolerance for sum to 1.0
        self.midnight_threshold = 0.05  # 5% threshold for midnight values

    def validate_temporal_data(self, df: pd.DataFrame, poi_name: str) -> bool:
        """Validate loaded temporal data for a POI."""
        try:
            # Check required columns
            missing_cols = [col for col in self.required_columns if col not in df.columns]
            if missing_cols:
                logger.error(f"Missing required columns for {poi_name}: {missing_cols}")
                return False
            
            # Validate distribution sum
            total = df['all_dist'].sum()
            if not np.isclose(total, 1.0, atol=self.distribution_sum_tolerance):
                logger.error(f"Distribution sum for {poi_name} is {total:.3f}, expected 1.0")
                return False
            
            # Check midnight values
            midnight_value = df.loc[df['hour'] == 0, 'all_dist'].iloc[0]
            if midnight_value > self.midnight_threshold:
                logger.warning(f"High midnight value ({midnight_value:.1%}) for {poi_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating data for {poi_name}: {str(e)}")
            return False

    def load_temporal_data(self, data_dir: Path, poi_name: str, trip_type: str) -> Optional[pd.DataFrame]:
        """Load and validate temporal data for a POI."""
        try:
            file_name = f"{poi_name.lower().replace('-', '_')}_{trip_type}_temporal.csv"
            file_path = data_dir / file_name
            
            if not file_path.exists():
                logger.error(f"No {trip_type} temporal file found for {poi_name}: {file_path}")
                return None
            
            df = pd.read_csv(file_path)
            
            if self.validate_temporal_data(df, poi_name):
                return df
            return None
            
        except Exception as e:
            logger.error(f"Error loading {trip_type} data for {poi_name}: {str(e)}")
            return None

    def calculate_city_average(self, data_dir: Path, focus_pois: List[str], 
                             trip_type: str) -> Optional[pd.DataFrame]:
        """Calculate weighted city-wide average excluding focus POIs."""
        try:
            # Get all temporal data files
            all_files = list(data_dir.glob(f"*_{trip_type}_temporal.csv"))
            
            # Exclude focus POI files
            focus_poi_files = {f"{poi.lower().replace('-', '_')}_{trip_type}_temporal.csv" 
                             for poi in focus_pois}
            general_files = [f for f in all_files if f.name not in focus_poi_files]
            
            if not general_files:
                logger.error("No general POI files found for city average")
                return None
            
            # Load and validate all general POI data
            valid_dfs = []
            for file_path in general_files:
                poi_name = file_path.stem.replace(f"_{trip_type}_temporal", "")
                df = pd.read_csv(file_path)
                
                if self.validate_temporal_data(df, poi_name):
                    valid_dfs.append(df)
            
            if not valid_dfs:
                logger.error("No valid POI data found for city average")
                return None
            
            # Calculate weighted average
            avg_df = pd.concat(valid_dfs).groupby('hour')['all_dist'].mean().reset_index()
            
            # Normalize to ensure sum is 1.0
            avg_df['all_dist'] = avg_df['all_dist'] / avg_df['all_dist'].sum()
            
            return avg_df
            
        except Exception as e:
            logger.error(f"Error calculating city average: {str(e)}")
            return None

    def process_temporal_data(self, analyzer) -> Dict:
        """Process temporal data for both inbound and outbound trips."""
        logger.info("Processing temporal data for visualization...")
        
        result = {
            'inbound': [],
            'outbound': []
        }
        
        # Process data for each trip type
        for trip_type in ['inbound', 'outbound']:
            # Process each hour
            for hour in range(24):
                # Create time bin label (e.g., "7:00-8:00")
                next_hour = (hour + 1) % 24
                time_label = f"{hour:02d}:00-{next_hour:02d}:00"
                
                hour_data = {
                    'hour': f"{hour:02d}:00",  # Keep original hour format for axis
                    'displayHour': time_label,  # Add display format for tooltip
                    'x': hour + 0.5  # Add midpoint for line placement
                }
                
                # Process focus POIs
                for poi in analyzer.focus_pois:
                    df = self.load_temporal_data(analyzer.data_dir, poi, trip_type)
                    if df is not None:
                        hour_value = df.loc[df['hour'] == hour, 'all_dist'].iloc[0]
                        hour_data[poi] = float(hour_value) * 100  # Convert to percentage
                    else:
                        hour_data[poi] = 0.0
                
                # Add city-wide average
                avg_df = self.calculate_city_average(analyzer.data_dir, analyzer.focus_pois, trip_type)
                if avg_df is not None:
                    city_value = avg_df.loc[avg_df['hour'] == hour, 'all_dist'].iloc[0]
                    hour_data['Beer-Sheva-Comparisons'] = float(city_value) * 100
                else:
                    hour_data['Beer-Sheva-Comparisons'] = 0.0
                
                result[trip_type].append(hour_data)
        
        return result

    def _get_template(self) -> str:
        """Get HTML template with React components."""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Temporal Trip Distributions</title>
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
        .toggle-button {
            background: #333;
            color: #fff;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 16px;
        }
        .toggle-button:hover {
            background: #444;
        }
        .mode-toggle {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 20px;
        }
        .mode-toggle button {
            background: transparent;
            color: #fff;
            border: 1px solid #444;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        .mode-toggle button.active {
            background: #444;
            border-color: #666;
        }
        .mode-toggle button:hover {
            background: #333;
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

        const CustomTooltip = ({ active, payload, label, currentTripType }) => {
            if (active && payload && payload.length) {
                // Find the full data point to get the display hour
                const dataPoint = temporalData[currentTripType].find(d => d.hour === label);
                return (
                    <div style={{
                        background: '#1a1a1a',
                        border: '1px solid #333',
                        padding: '8px',
                        fontSize: '0.85em'
                    }}>
                        <p style={{ margin: '0 0 5px' }}><strong>{dataPoint.displayHour}</strong></p>
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
            const [tripType, setTripType] = React.useState('inbound');
            
            return (
                <div className="card">
                    <h2 style={{ textAlign: 'center', marginBottom: '20px' }}>
                        Temporal Trip Patterns
                    </h2>
                    <div className="mode-toggle">
                        <button 
                            className={tripType === 'inbound' ? 'active' : ''}
                            onClick={() => setTripType('inbound')}
                        >
                            Inbound Trips
                        </button>
                        <button 
                            className={tripType === 'outbound' ? 'active' : ''}
                            onClick={() => setTripType('outbound')}
                        >
                            Outbound Trips
                        </button>
                    </div>
                    <ResponsiveContainer width="100%" height={400}>
                        <LineChart
                            data={temporalData[tripType]}
                            margin={{
                                top: 5,
                                right: 30,
                                left: 20,
                                bottom: 45
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
                                    offset: 10
                                }}
                            />
                            <YAxis
                                stroke="#fff"
                                tick={{ fill: '#fff' }}
                                label={{
                                    value: `${tripType.charAt(0).toUpperCase() + tripType.slice(1)} Trips (%)`,
                                    angle: -90,
                                    position: 'insideLeft',
                                    fill: '#fff',
                                    offset: 0
                                }}
                            />
                            <Tooltip content={<CustomTooltip currentTripType={tripType} />} />
                            {Object.entries(poiColors).map(([poi, color]) => (
                                <Line
                                    key={poi}
                                    type="monotone"
                                    dataKey={poi}
                                    stroke={color}
                                    strokeWidth={2}
                                    dot={false}
                                    xAxisId="x"
                                />
                            ))}
                            <XAxis 
                                dataKey="x"
                                type="number"
                                domain={[0, 23]}
                                hide={true}
                                xAxisId="x"
                            />
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

    def generate_visualization(self, analyzer):
        """Generate temporal pattern visualization for both inbound and outbound data."""
        logger.info("Generating temporal visualization...")
        
        try:
            # Process both inbound and outbound data
            temporal_data = self.process_temporal_data(analyzer)
            
            # Validate we have data for at least one trip type
            if not temporal_data['inbound'] and not temporal_data['outbound']:
                raise ValueError("No valid temporal data found for any trip type")
            
            # Generate HTML with processed data
            html_content = self._get_template()
            html_content = html_content.replace('DATA_PLACEHOLDER', json.dumps(temporal_data))
            
            output_file = self.output_dir / "temporal_visualization.html"
            logger.info(f"Writing visualization to: {output_file}")
            
            with open(output_file, 'w') as f:
                f.write(html_content)
                
            logger.info("Successfully generated temporal visualization")
            
        except Exception as e:
            logger.error(f"Error generating visualization: {str(e)}")
            raise


def main():
    """Main function to run temporal pattern analysis"""
    try:
        logger.info("Starting temporal pattern analysis...")
        
        # Initialize analyzer with OUTPUT_DIR
        data_dir = Path(OUTPUT_DIR)
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")
            
        analyzer = MobilityPatternAnalyzer(data_dir)
        generator = TemporalVisualizationGenerator()
        
        # Generate visualization
        generator.generate_visualization(analyzer)
        
        logger.info("Process completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
        raise

if __name__ == "__main__":
    main()