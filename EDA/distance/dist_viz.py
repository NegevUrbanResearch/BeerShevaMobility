from pathlib import Path
import json

class VisualizationGenerator:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.data_dir = self.project_root / "output" / "distance_histograms"
        self.output_dir = self.project_root / "output" / "visualizations"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_template(self):
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Trip Distance Distribution Analysis</title>
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
        .selector-group {
            margin-bottom: 20px;
            padding: 15px;
            background: #222;
            border-radius: 8px;
        }
        .selector-label {
            display: block;
            margin-bottom: 10px;
            color: #999;
            font-size: 14px;
        }
        #error-message {
            background: #ff000033;
            color: #ff6b6b;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
            display: none;
        }
        .loading {
            color: #fff;
            text-align: center;
            padding: 20px;
        }
    </style>
</head>
<body>
    <div id="error-message"></div>
    <div id="root">
        <div class="loading">Loading visualization...</div>
    </div>
    <script>
        // Global error handler
        window.onerror = function(msg, url, lineNo, columnNo, error) {
            const errorDiv = document.getElementById('error-message');
            errorDiv.style.display = 'block';
            errorDiv.innerHTML = `<strong>Error:</strong> ${msg}<br>
                                <small>Line: ${lineNo}, Column: ${columnNo}</small>`;
            console.error('Error:', error);
            return false;
        };
    </script>
    <script type="text/babel">
        // Wait for all dependencies to load
        const checkDependencies = () => {
            return new Promise((resolve, reject) => {
                const interval = setInterval(() => {
                    if (window.Recharts) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 100);

                // Timeout after 5 seconds
                setTimeout(() => {
                    clearInterval(interval);
                    reject(new Error('Timeout loading dependencies'));
                }, 5000);
            });
        };

        const allData = DATA_PLACEHOLDER;
        
        const modeColors = {
            walk: '#45B7D1',
            bike: '#96CEB4',
            car: '#FF6B6B',
            transit: '#4ECDC4'
        };

        const modeNames = {
            walk: 'Walking',
            bike: 'Biking',
            car: 'Car',
            transit: 'Transit'
        };

        const locationNames = {
            bgu: 'BGU',
            soroka_hospital: 'Soroka Hospital',
            gev_yam: 'Gev Yam'
        };

        const processData = (data) => {
            const total = data.reduce((sum, item) => sum + item.trips, 0);
            let cumulative = 0;
            return data.map(item => {
                const percentage = (item.trips / total) * 100;
                cumulative += percentage;
                return {
                    ...item,
                    percentage: Math.round(percentage * 10) / 10,
                    cumulative: Math.round(cumulative * 10) / 10
                };
            });
        };

        const CustomTooltip = ({ active, payload, label }) => {
            if (active && payload && payload.length) {
                return (
                    <div style={{
                        background: '#1a1a1a',
                        border: '1px solid #333',
                        padding: '10px',
                        borderRadius: '4px'
                    }}>
                        <p style={{color: '#fff', margin: '0 0 5px'}}>
                            Distance: {label} km
                        </p>
                        <p style={{color: '#fff', margin: '0 0 5px'}}>
                            Trips: {payload[0].payload.trips}
                        </p>
                        <p style={{color: '#fff', margin: '0 0 5px'}}>
                            Percentage: {payload[0].payload.percentage}%
                        </p>
                        <p style={{color: '#fff', margin: '0'}}>
                            Cumulative: {payload[0].payload.cumulative}%
                        </p>
                    </div>
                );
            }
            return null;
        };

        const App = () => {
            const [selectedLocation, setSelectedLocation] = React.useState('bgu');
            const [selectedMode, setSelectedMode] = React.useState('walk');
            const [isLoading, setIsLoading] = React.useState(true);
            const [error, setError] = React.useState(null);

            React.useEffect(() => {
                checkDependencies()
                    .then(() => setIsLoading(false))
                    .catch(err => setError(err.message));
            }, []);

            if (error) {
                return <div style={{color: '#ff6b6b'}}>Error: {error}</div>;
            }

            if (isLoading) {
                return <div className="loading">Loading dependencies...</div>;
            }

            const {
                ComposedChart, Bar, Line, XAxis, YAxis,
                CartesianGrid, Tooltip
            } = window.Recharts;

            const currentData = allData[selectedLocation]?.[selectedMode] || [];
            const processedData = processData(currentData);

            return (
                <div className="card">
                    <h2 style={{
                        color: '#fff',
                        marginTop: 0,
                        marginBottom: '20px',
                        textAlign: 'center',
                        fontSize: '32px'
                    }}>
                        Trip Distance Distribution Analysis
                    </h2>
                    
                    <div className="selector-group">
                        <span className="selector-label">Location:</span>
                        <div style={{
                            display: 'flex',
                            gap: '10px',
                            marginBottom: '15px'
                        }}>
                            {Object.entries(locationNames).map(([key, name]) => (
                                <button
                                    key={key}
                                    onClick={() => setSelectedLocation(key)}
                                    style={{
                                        padding: '8px 16px',
                                        borderRadius: '6px',
                                        border: 'none',
                                        background: selectedLocation === key ? '#333' : '#222',
                                        color: selectedLocation === key ? '#fff' : '#999',
                                        cursor: 'pointer',
                                        transition: 'all 0.2s'
                                    }}
                                >
                                    {name}
                                </button>
                            ))}
                        </div>

                        <span className="selector-label">Transport Mode:</span>
                        <div style={{
                            display: 'flex',
                            gap: '10px'
                        }}>
                            {Object.entries(modeNames).map(([mode, name]) => (
                                <button
                                    key={mode}
                                    onClick={() => setSelectedMode(mode)}
                                    style={{
                                        padding: '8px 16px',
                                        borderRadius: '6px',
                                        border: 'none',
                                        background: selectedMode === mode ? '#333' : '#222',
                                        color: selectedMode === mode ? modeColors[mode] : '#999',
                                        cursor: 'pointer',
                                        transition: 'all 0.2s'
                                    }}
                                >
                                    {name}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div style={{height: '400px'}}>
                        <ComposedChart
                            width={800}
                            height={400}
                            data={processedData}
                            margin={{
                                top: 20,
                                right: 30,
                                left: 20,
                                bottom: 5
                            }}
                        >
                            <CartesianGrid
                                strokeDasharray="3 3"
                                stroke="#333"
                                vertical={false}
                            />
                            <XAxis
                                dataKey="range"
                                stroke="#999"
                                label={{
                                    value: 'Distance (km)',
                                    position: 'bottom',
                                    fill: '#999'
                                }}
                                tickFormatter={value => `${value} km`}
                            />
                            <YAxis
                                stroke="#999"
                                tickFormatter={value => `${value}%`}
                            />
                            <Tooltip content={<CustomTooltip />} />
                            <Bar
                                dataKey="percentage"
                                fill={modeColors[selectedMode]}
                                radius={[4, 4, 0, 0]}
                                maxBarSize={80}
                            />
                            <Line
                                type="monotone"
                                dataKey="cumulative"
                                stroke="#fff"
                                strokeWidth={2}
                                dot={false}
                                opacity={0.6}
                            />
                        </ComposedChart>
                    </div>
                    <div style={{
                        textAlign: 'center',
                        color: '#666',
                        marginTop: '10px',
                        fontSize: '14px'
                    }}>
                        Bars show distribution percentage, line shows cumulative percentage
                    </div>
                </div>
            );
        };

        ReactDOM.render(
            <React.StrictMode>
                <App />
            </React.StrictMode>,
            document.getElementById('root')
        );
    </script>
</body>
</html>'''

    def generate_merged_visualization(self):
        """Generate a single visualization with all POI data"""
        print("\nGenerating merged visualization")
        
        try:
            # Load data for all POIs
            all_data = {}
            poi_names = ['BGU', 'Soroka_Hospital', 'Gev_Yam']
            
            for poi_name in poi_names:
                data_file = self.data_dir / f"{poi_name.lower()}_distance_dist.json"
                print(f"Reading data from: {data_file}")
                
                with open(data_file) as f:
                    poi_data = json.load(f)
                    all_data[poi_name.lower()] = poi_data
            
            print(f"Successfully loaded data for all POIs")
            
            # Generate single HTML with all data
            html_content = self._get_template()
            html_content = html_content.replace('DATA_PLACEHOLDER', json.dumps(all_data))
            
            output_file = self.output_dir / "merged_distance_viz.html"
            print(f"Writing merged visualization to: {output_file}")
            
            with open(output_file, 'w') as f:
                f.write(html_content)
                
            print(f"Successfully generated merged visualization")
            
        except Exception as e:
            print(f"Error generating merged visualization: {str(e)}")
            raise

if __name__ == "__main__":
    generator = VisualizationGenerator()
    generator.generate_merged_visualization()