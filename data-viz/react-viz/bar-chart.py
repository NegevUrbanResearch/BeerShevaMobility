def create_react_visualization():
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Mode Share Comparison</title>
    <!-- Load React -->
    <script src="https://unpkg.com/react@17/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@17/umd/react-dom.production.min.js"></script>
    
    <!-- Load Recharts Dependencies -->
    <script src="https://unpkg.com/prop-types/prop-types.min.js"></script>
    <script src="https://unpkg.com/recharts@2.1.12/umd/Recharts.js"></script>
    
    <!-- Load Babel -->
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    
    <!-- Load Tailwind -->
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        .recharts-legend-item-text {
            font-size: 1rem !important;
            color: #e5e7eb !important;
        }
        .recharts-legend-wrapper {
            padding: 20px !important;
        }
    </style>
</head>
<body class="bg-black">
    <div id="root"></div>
    <script type="text/babel">
        // Wait for Recharts to load completely
        window.onload = function() {
            const { BarChart, CartesianGrid, XAxis, YAxis, Tooltip, Legend, Bar, ReferenceLine } = Recharts;
            
            const ModeShareChart = () => {
                const data = [
                    {
                        name: 'BGU',
                        Car: 61.89,
                        Bus: 8.83,
                        Walk: 23.61,
                        Train: 4.35
                    },
                    {
                        name: 'Soroka',
                        Car: 73.09,
                        Bus: 18.20,
                        Walk: 5.75,
                        Train: 1.72
                    }
                ];

                return (
                    <div className="bg-black p-4 flex flex-col items-center">
                        <h2 className="text-gray-100 text-2xl font-bold mb-8">Mode Share by Destination</h2>
                        <BarChart
                            width={800}
                            height={400}
                            data={data}
                            margin={{
                                top: 20,
                                right: 120,
                                left: 20,
                                bottom: 60,
                            }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                            <XAxis 
                                dataKey="name" 
                                stroke="#e5e7eb"
                                tick={{fill: '#e5e7eb', fontSize: 14}}
                            />
                            <YAxis 
                                stroke="#e5e7eb"
                                tick={{fill: '#e5e7eb', fontSize: 14}}
                                tickFormatter={(value) => `${value}%`}
                            />
                            <Tooltip 
                                contentStyle={{
                                    backgroundColor: '#111', 
                                    border: '1px solid #333',
                                    borderRadius: '4px',
                                    color: '#e5e7eb'
                                }}
                                formatter={(value) => [`${value}%`]}
                            />
                            <Legend 
                                verticalAlign="bottom" 
                                height={60}
                                wrapperStyle={{
                                    paddingTop: '20px',
                                    width: '100%',
                                    justifyContent: 'center'
                                }}
                            />
                            <Bar dataKey="Car" fill="#3b82f6" />
                            <Bar dataKey="Bus" fill="#10b981" />
                            <Bar dataKey="Walk" fill="#ec4899" />
                            <Bar dataKey="Train" fill="#8b5cf6" />
                            <ReferenceLine y={68.76} stroke="#3b82f6" strokeDasharray="5 5" 
                                label={{ value: 'Car Avg', fill: '#3b82f6', position: 'right', offset: 10 }} />
                            <ReferenceLine y={20.31} stroke="#10b981" strokeDasharray="5 5" 
                                label={{ value: 'Bus Avg', fill: '#10b981', position: 'right', offset: 10 }} />
                            <ReferenceLine y={10.38} stroke="#ec4899" strokeDasharray="5 5" 
                                label={{ value: 'Walk Avg', fill: '#ec4899', position: 'right', offset: 10 }} />
                            <ReferenceLine y={0.91} stroke="#8b5cf6" strokeDasharray="5 5" 
                                label={{ value: 'Train Avg', fill: '#8b5cf6', position: 'right', offset: 10 }} />
                        </BarChart>
                    </div>
                );
            };

            ReactDOM.render(<ModeShareChart />, document.getElementById('root'));
        };
    </script>
</body>
</html>
"""

    # Save the file
    with open('/Users/noamgal/Downloads/mode_share_visualization.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

if __name__ == "__main__":
    create_react_visualization()
    print("Visualization has been saved as '/Users/noamgal/Downloads/mode_share_visualization.html'")