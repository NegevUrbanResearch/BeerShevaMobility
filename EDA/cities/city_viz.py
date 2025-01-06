from pathlib import Path
import json
import pandas as pd
import ast

class InnovationDistrictDashboard:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.data_dir = self.project_root / "output/analysis"
        self.output_dir = self.project_root / "output" / "id_dashboard"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_city_data(self):
        """Load and process data from CSV"""
        csv_path = self.data_dir / "top_15_cities_innovation_district.csv"
        df = pd.read_csv(csv_path)
        
        city_data = {}
        for _, row in df.iterrows():
            # Convert string representations of dictionaries to actual dictionaries
            mode_shares = ast.literal_eval(row['mode_shares'])
            
            # Rename 'link' to 'multimodal' in mode_shares
            if 'link' in mode_shares:
                mode_shares['multimodal'] = mode_shares.pop('link')
            
            city_data[row['city']] = {
                "BGU_trips": row['BGU_trips'],
                "Soroka_trips": row['Soroka_trips'],
                "GavYam_trips": row['GavYam_trips'],
                "mode_shares": mode_shares
            }
        
        return city_data

    def _get_template(self):
        return '''<!DOCTYPE html>
<html>
<head>
    <title>ID Origin Patterns</title>
    <meta charset="utf-8">
    <script src="https://unpkg.com/react@17.0.2/umd/react.development.js"></script>
    <script src="https://unpkg.com/react-dom@17.0.2/umd/react-dom.development.js"></script>
    <script src="https://unpkg.com/prop-types@15.8.1/prop-types.min.js"></script>
    <script src="https://unpkg.com/recharts@2.10.3/umd/Recharts.js"></script>
    <script src="https://unpkg.com/@babel/standalone@7.23.6/babel.min.js"></script>
    <style>
        body {
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto;
            background: #111;
            color: #fff;
            font-size: 1.5em;
        }
        .dashboard {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        .card {
            background: #1a1a1a;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .dashboard-header {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin-bottom: 20px;
            padding: 0 20px;
        }
        .city-selector {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-left: 0;
        }
        .city-button {
            background: #222;
            color: #fff;
            border: none;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1em;
        }
        .city-button:hover {
            background: #333;
        }
        .city-name {
            font-size: 1em;
            min-width: 150px;
            text-align: center;
        }
        .charts-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 0;
        }
        .chart-card {
            background: transparent;
            padding: 0;
            border-radius: 0;
            position: relative;
            height: 400px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .chart-title {
            margin: 0 0 10px 0;
            text-align: center;
        }
        @media (max-width: 768px) {
            .charts-container {
                grid-template-columns: 1fr;
            }
            .dashboard-header {
                flex-direction: column;
                gap: 20px;
            }
            .city-selector {
                margin-left: 0;
            }
        }
    </style>
</head>
<body>
    <div id="root"></div>
    
    <script type="text/babel">
        const cityData = CITY_DATA_PLACEHOLDER;

        const destinationColors = {
            BGU: '#60a5fa',
            Soroka: '#f87171',
            'Gav Yam': '#4ade80'
        };

        const modeColors = {
            car: '#ef4444',      // Red for cars
            bus: '#3b82f6',      // Blue for public transit
            bike: '#22c55e',     // Green for active transport
            ped: '#84cc16',      // Lime for active transport
            multimodal: '#f59e0b', // Orange for mixed modes
            train: '#6366f1'     // Indigo for rail transit
        };

        // Helper function to convert to proper case
        const toProperCase = (str) => {
            return str.toLowerCase().replace(/\\b\\w/g, c => c.toUpperCase());
        };

        const App = () => {
            const [selectedCity, setSelectedCity] = React.useState(Object.keys(cityData)[0]);
            const { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } = Recharts;

            const currentCity = cityData[selectedCity];
            
            const destData = [
                { name: 'BGU', value: currentCity.BGU_trips },
                { name: 'Soroka', value: currentCity.Soroka_trips },
                { name: 'Gav Yam', value: currentCity.GavYam_trips }
            ];
            
            const modeData = Object.entries(currentCity.mode_shares)
                .map(([mode, share]) => ({
                    name: toProperCase(mode),
                    value: share
                }))
                .sort((a, b) => b.value - a.value);

            const totalTrips = destData.reduce((sum, item) => sum + item.value, 0);

            const CustomTooltip = ({ active, payload }) => {
                if (active && payload && payload.length) {
                    return (
                        <div style={{
                            background: '#1a1a1a',
                            padding: '12px',
                            border: '1px solid #333',
                            borderRadius: '4px',
                            fontSize: '1em'
                        }}>
                            <p style={{margin: '0', color: '#fff'}}>
                                {`${payload[0].name}: ${payload[0].value.toLocaleString()} trips`}
                                <br />
                                {`(${((payload[0].value/totalTrips)*100).toFixed(1)}%)`}
                            </p>
                        </div>
                    );
                }
                return null;
            };

            const renderCustomizedLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent, name, fill, payload, index }) => {
                // Skip labels for very small segments (less than 0.1%)
                if (percent < 0.01) return null;

                const RADIAN = Math.PI / 180;
                const radius = outerRadius * 1.12; // Consistent radius for all labels
                
                // Calculate the base angle position
                let currentAngle = midAngle;
                
                // Adjust angles for small segments to prevent overlap
                if (percent < 0.05) {
                    // Find the angle to the next and previous segments
                    const prevAngle = index > 0 ? midAngle - 20 : midAngle;
                    const nextAngle = midAngle + 20;
                    
                    // If angles are too close, spread them out
                    if (Math.abs(prevAngle - currentAngle) < 15) {
                        currentAngle = prevAngle + 15;
                    }
                    if (Math.abs(nextAngle - currentAngle) < 15) {
                        currentAngle = nextAngle - 15;
                    }
                }
                
                // Calculate position with the adjusted angle
                const x = cx + radius * Math.cos(-currentAngle * RADIAN);
                const y = cy + radius * Math.sin(-currentAngle * RADIAN);
                
                const textAnchor = x > cx ? 'start' : 'end';
                
                const label = `${name} ${(percent * 100).toFixed(1)}%`;
                
                return (
                    <text 
                        x={x}
                        y={y}
                        fill={fill}
                        textAnchor={textAnchor}
                        dominantBaseline="central"
                        style={{ 
                            fontSize: '0.92em',
                            fontWeight: 'normal'
                        }}
                    >
                        {label}
                    </text>
                );
            };

            return (
                <div className="dashboard">
                    <div className="card">
                        <div className="dashboard-header">
                            <h1 style={{margin: 0, fontSize: '1em'}}>
                                City Origins: 
                            </h1>
                            <div className="city-selector">
                                <button 
                                    className="city-button"
                                    onClick={() => {
                                        const cities = Object.keys(cityData);
                                        const currentIndex = cities.indexOf(selectedCity);
                                        const prevIndex = (currentIndex - 1 + cities.length) % cities.length;
                                        setSelectedCity(cities[prevIndex]);
                                    }}
                                >
                                    ←
                                </button>
                                <span className="city-name">{selectedCity}</span>
                                <button 
                                    className="city-button"
                                    onClick={() => {
                                        const cities = Object.keys(cityData);
                                        const currentIndex = cities.indexOf(selectedCity);
                                        const nextIndex = (currentIndex + 1) % cities.length;
                                        setSelectedCity(cities[nextIndex]);
                                    }}
                                >
                                    →
                                </button>
                            </div>
                        </div>

                        <div className="charts-container">
                            <div className="chart-card">
                                <h3 style={{textAlign: 'center', margin: '0 0 10px', color: '#fff', fontSize: '1em'}}>
                                    Destination Split
                                </h3>
                                <ResponsiveContainer width="125%" height="125%">
                                    <PieChart>
                                        <Pie
                                            data={destData}
                                            dataKey="value"
                                            nameKey="name"
                                            cx="50%"
                                            cy="50%"
                                            outerRadius={120}
                                            label={renderCustomizedLabel}
                                            labelLine={false}
                                        >
                                            {destData.map((entry) => (
                                                <Cell 
                                                    key={entry.name}
                                                    fill={destinationColors[entry.name]}
                                                />
                                            ))}
                                        </Pie>
                                        <Tooltip content={<CustomTooltip />} />
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                            
                            <div className="chart-card">
                                <h3 style={{textAlign: 'center', margin: '0 0 20px', color: '#fff', fontSize: '1em', transform: 'translateX(-25%)'}}>
                                    Mode Split
                                </h3>
                                <ResponsiveContainer width="125%" height="125%">
                                    <PieChart>
                                        <Pie
                                            data={modeData}
                                            dataKey="value"
                                            nameKey="name"
                                            cx="45%"
                                            cy="50%"
                                            outerRadius={120}
                                            label={renderCustomizedLabel}
                                            labelLine={false}
                                        >
                                            {modeData.map((entry) => (
                                                <Cell 
                                                    key={entry.name}
                                                    fill={modeColors[entry.name.toLowerCase()]}
                                                />
                                            ))}
                                        </Pie>
                                        <Tooltip content={<CustomTooltip />} />
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
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

    def generate_dashboard(self):
        """Generate the dashboard HTML"""
        city_data = self.load_city_data()
        html_content = self._get_template()
        html_content = html_content.replace('CITY_DATA_PLACEHOLDER', 
                                          json.dumps(city_data))
        
        output_file = self.output_dir / "index.html"
        with open(output_file, 'w') as f:
            f.write(html_content)
            
        print(f"Dashboard generated at: {output_file}")

if __name__ == "__main__":
    dashboard = InnovationDistrictDashboard()
    dashboard.generate_dashboard()