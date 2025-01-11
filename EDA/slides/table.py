import pandas as pd
from typing import Dict, List, Union
import json
from pathlib import Path

class TransportVizGenerator:
    def __init__(self):
        self.html_start = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Transportation Mode Distribution</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/lucide/0.263.1/lucide.min.js"></script>
    <style>
        body {
            margin: 0;
            padding: 2rem;
            background: linear-gradient(135deg, #000000 0%, #1a1a2e 100%);
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 16px;
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            animation: fadeIn 0.6s ease-out;
        }

        .data-note {
            background: rgba(96, 165, 250, 0.1);
            border-left: 4px solid #60A5FA;
            padding: 1rem;
            margin: 2rem 0;
            border-radius: 0 8px 8px 0;
            font-size: 1.25rem;
            line-height: 1.6;
        }

        .data-note strong {
            color: #93C5FD;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes glowPulse {
            0% { text-shadow: 0 0 10px rgba(66, 153, 225, 0.5); }
            50% { text-shadow: 0 0 20px rgba(66, 153, 225, 0.8); }
            100% { text-shadow: 0 0 10px rgba(66, 153, 225, 0.5); }
        }

        .title {
            font-size: 3rem;
            margin-bottom: 2rem;
            text-align: center;
            color: #60A5FA;
            font-weight: bold;
            animation: glowPulse 2s infinite;
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .transport-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            border-radius: 12px;
            overflow: hidden;
            background: rgba(17, 24, 39, 0.7);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }

        .transport-table th,
        .transport-table td {
            padding: 1rem;
            text-align: right;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.2s ease;
            font-size: 1.25rem;
        }

        .transport-table th {
            background: rgba(59, 130, 246, 0.2);
            font-weight: 600;
            text-transform: capitalize;
            color: #60A5FA;
            font-size: 1.25rem;
            letter-spacing: 0.5px;
        }

        .transport-table tr:hover td {
            background: rgba(59, 130, 246, 0.1);
        }

        .transport-table tr:last-child td {
            border-bottom: none;
        }

        .transport-table td:first-child,
        .transport-table th:first-child {
            text-align: left;
            padding-left: 1.5rem;
        }

        .mode-header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            justify-content: flex-end;
        }

        .mode-header i {
            width: 1.4rem;
            height: 1.4rem;
            color: #60A5FA;
            transition: transform 0.2s ease;
        }

        .mode-header:hover i {
            transform: scale(1.2);
        }

        .grand-total {
            font-weight: bold;
            background: linear-gradient(90deg, rgba(59, 130, 246, 0.1) 0%, rgba(59, 130, 246, 0.2) 100%);
        }

        .grand-total td {
            color: #60A5FA;
            font-size: 1.25rem;
        }

        .location-cell {
            font-weight: 500;
            color: #93C5FD;
            position: relative;
            padding-left: 1rem;
        }

        .location-cell::before {
            content: '';
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 4px;
            height: 70%;
            background: #3B82F6;
            border-radius: 2px;
        }

        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
            
            .transport-table th,
            .transport-table td {
                padding: 0.75rem;
                font-size: 1.25rem;
            }
            
            .title {
                font-size: 3rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="title">Summary of Inbound Trip Data</h1>
        <div class="data-note">
            <strong>Data Coverage Note:</strong> This dataset captures the majority of trips to the district. The sample was balanced in preprocessing to ensure representativity, but biases in the sample may still exist.
        </div>
        <div id="root"></div>
    </div>
'''
        
        self.script_template = '''
    <script type="text/javascript">
        const { createElement: h } = React;

        const TransportTable = () => {
            const data = DATAJSON;

            const icons = {
                'Bike': 'bike',
                'Bus': 'bus',
                'Car': 'car',
                'Walking': 'footprints',
                'Train': 'train'
            };

            const getTotal = (location) => {
                return data.values[location].reduce((a, b) => a + b, 0);
            };

            const getModeTotal = (modeIndex) => {
                return data.locations.reduce((sum, loc) => sum + data.values[loc][modeIndex], 0);
            };

            const grandTotal = data.locations.reduce((sum, loc) => sum + getTotal(loc), 0);

            return h('table', { className: 'transport-table' },
                h('thead', null,
                    h('tr', null,
                        h('th', null, 'Location'),
                        ...data.modes.map((mode, i) => 
                            h('th', null, 
                                h('div', { className: 'mode-header' },
                                    mode,
                                    h('i', { 'data-lucide': icons[mode] })
                                )
                            )
                        ),
                        h('th', null, 'Total')
                    )
                ),
                h('tbody', null,
                    [...data.locations.map(location =>
                        h('tr', null,
                            h('td', { className: 'location-cell' }, location),
                            ...data.values[location].map(value =>
                                h('td', null, value.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }))
                            ),
                            h('td', null, getTotal(location).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }))
                        )
                    ),
                    h('tr', { className: 'grand-total' },
                        h('td', null, 'Grand Total'),
                        ...data.modes.map((_, i) =>
                            h('td', null, getModeTotal(i).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }))
                        ),
                        h('td', null, grandTotal.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }))
                    )]
                )
            );
        };

        ReactDOM.render(
            h(TransportTable),
            document.getElementById('root')
        );
        
        // Initialize Lucide icons
        lucide.createIcons();
    </script>
</body>
</html>'''

    def from_dict(self, data: Dict[str, Union[List[str], Dict[str, List[float]]]]) -> None:
        self.data = data

    def generate_html(self, output_path: Union[str, Path]) -> None:
        if not hasattr(self, 'data'):
            raise ValueError("No data has been loaded. Use from_dict() first.")
        
        data_json = json.dumps(self.data)
        script_content = self.script_template.replace('DATAJSON', data_json)
        html_content = self.html_start + script_content
        
        output_path = Path(output_path)
        output_path.write_text(html_content, encoding='utf-8')


if __name__ == "__main__":
    # Example usage
    data = {
        'locations': ['BGU', 'Gev Yam', 'Soroka Hospital'],
        'modes': ['Bike', 'Bus', 'Car', 'Walking', 'Train'],
        'values': {
            'BGU': [129.2, 934.5, 6550.2, 2499.1, 460.1],
            'Gev Yam': [7.7, 325.9, 1677.9, 125.3, 21.4],
            'Soroka Hospital': [86.9, 1895.6, 7611.4, 598.5, 178.7]
        }
    }
    
    viz = TransportVizGenerator()
    viz.from_dict(data)
    viz.generate_html('transport_viz.html')
    print("Saved at transport_viz.html")