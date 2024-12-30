import geopandas as gpd
import os
import sys
import json
from collections import defaultdict
import numpy as np

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR

def load_road_usage():
    """Load the trips data"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    trips = gpd.read_file(file_path)
    print(f"Loaded {len(trips)} unique trip routes")
    return trips

def prepare_line_data(trips_data, bounds):
    """Prepare the line data for visualization"""
    segments = defaultdict(float)
    
    # Aggregate trip counts for segments
    for _, row in trips_data.iterrows():
        coords = list(row.geometry.coords)
        num_trips = row['num_trips']
        
        for i in range(len(coords) - 1):
            segment = tuple(sorted([coords[i], coords[i + 1]]))
            segments[segment] += num_trips
    
    max_trips = max(segments.values())
    line_data = []
    
    # Create visualization data
    for (start_coord, end_coord), trip_count in segments.items():
        trip_ratio = trip_count / max_trips
        line_data.append({
            "start": [float(start_coord[0]), float(start_coord[1]), 0],
            "end": [float(end_coord[0]), float(end_coord[1]), 0],
            "trips": int(trip_count),
            "ratio": float(trip_ratio)
        })

    return line_data, max_trips

def create_html_file(trips_data, bounds, output_prefix):
    """Create the HTML file with the visualization"""
    # Prepare data
    line_data, max_trips = prepare_line_data(trips_data, bounds)
    
    # Calculate view state
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    
    # Create the HTML content
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Route Intensity Visualization</title>
        <script src="https://unpkg.com/deck.gl@latest/dist.min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 0;
                width: 100vw;
                height: 100vh;
                overflow: hidden;
                background: black;
            }}
            #deck-container {{
                width: 100%;
                height: 100%;
                position: absolute;
            }}
            .controls {{
                position: fixed;
                top: 20px;
                left: 20px;
                background: rgba(0,0,0,0.8);
                padding: 12px;
                border-radius: 5px;
                color: white;
                font-family: Arial;
                z-index: 2;
            }}
            .legend-container {{
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: rgba(0,0,0,0.8);
                padding: 12px;
                border-radius: 5px;
                color: white;
                font-family: Arial;
            }}
            .methodology-container {{
                position: fixed;
                top: 20px;
                right: 20px;
                background: rgba(0,0,0,0.8);
                padding: 12px;
                border-radius: 5px;
                color: white;
                font-family: Arial;
                max-width: 300px;
            }}
        </style>
    </head>
    <body>
        <div id="deck-container"></div>
        <div class="controls">
            <div class="slider-container">
                <label for="intensity">Intensity Threshold:</label>
                <input type="range" id="intensity" min="0" max="100" value="0" step="1" style="width: 150px;">
                <span id="intensity-value">0%</span>
            </div>
            <div id="stats" style="margin-top: 10px;">
                Road Segments shown: <span id="route-count">0</span>
            </div>
        </div>
        <div class="legend-container">
            <h3 style="margin: 0 0 10px 0;">Trip Intensity</h3>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 4px; background: rgb(20,42,120); margin-right: 8px;"></div>
                <span>Low intensity</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 4px; background: rgb(65,182,196); margin-right: 8px;"></div>
                <span>Medium intensity</span>
            </div>
            <div style="display: flex; align-items: center;">
                <div style="width: 20px; height: 4px; background: rgb(255,255,0); margin-right: 8px;"></div>
                <span>High intensity</span>
            </div>
        </div>
        <div class="methodology-container">
            <h3 style="margin: 0 0 10px 0;">Methodology</h3>
            <p style="margin: 0 0 10px 0;">
                This visualization represents estimated intensity of inbound automobile trips to BGU or Soroka Medical Center 
                across road segments in the road network generated by shortest path analysis.
            </p>
            <p style="margin: 0;">
                Colors indicate trip intensity using a cube root scale to differentiate lower intensity routes.
            </p>
        </div>
        <script type="text/javascript">
            const lineData = {json.dumps(line_data)};
            
            function interpolateColor(t) {{
                // Apply cube root scaling to compress high values
                t = Math.cbrt(t);
                
                // Color stops (from low to high intensity)
                const colorStops = {{
                    0.0: [20, 42, 120],     // Dark blue
                    0.2: [40, 80, 180],     // Medium blue
                    0.4: [65, 182, 196],    // Light blue
                    0.6: [120, 200, 150],   // Blue-green
                    0.8: [200, 220, 100],   // Yellow-green
                    1.0: [255, 255, 0]      // Bright yellow
                }};
                
                // Find the two colors to interpolate between
                const stops = Object.keys(colorStops).map(Number);
                const lowerStop = Math.max(...stops.filter(s => s <= t));
                const upperStop = Math.min(...stops.filter(s => s >= t));
                
                const c1 = colorStops[lowerStop];
                const c2 = colorStops[upperStop];
                
                // Calculate interpolation ratio
                const ratio = (upperStop === lowerStop) ? 0 : 
                    (t - lowerStop) / (upperStop - lowerStop);
                
                // Interpolate RGB values
                return [
                    Math.round(c1[0] + (c2[0] - c1[0]) * ratio),
                    Math.round(c1[1] + (c2[1] - c1[1]) * ratio),
                    Math.round(c1[2] + (c2[2] - c1[2]) * ratio),
                    200  // Fixed opacity
                ];
            }}
            
            function createLineLayer(threshold) {{
                const filteredData = lineData.filter(d => d.ratio >= threshold);
                document.getElementById('route-count').textContent = filteredData.length.toLocaleString();
                
                return new deck.LineLayer({{
                    id: 'routes',
                    data: filteredData,
                    getSourcePosition: d => d.start,
                    getTargetPosition: d => d.end,
                    getColor: d => interpolateColor(d.ratio),
                    getWidth: 3,
                    pickable: true
                }});
            }}

            // Initialize deck.gl
            const deckgl = new deck.DeckGL({{
                container: 'deck-container',
                initialViewState: {{
                    longitude: {center_lon},
                    latitude: {center_lat},
                    zoom: 12,
                    pitch: 0,
                    bearing: 0
                }},
                controller: true,
                layers: [createLineLayer(0)]
            }});

            // Set up slider interaction
            const slider = document.getElementById('intensity');
            const value = document.getElementById('intensity-value');
            
            slider.addEventListener('input', function() {{
                const threshold = this.value / 100;
                value.textContent = this.value + '%';
                deckgl.setProps({{ layers: [createLineLayer(threshold)] }});
            }});
        </script>
    </body>
    </html>
    """
    
    # Save the HTML file
    output_file = os.path.join(OUTPUT_DIR, f"{output_prefix}.html")
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    return output_file

def main():
    print("\nStarting intensity-controlled route visualization...")
    trips_data = load_road_usage()
    
    # Filter to the Beer Sheva area
    bounds = (34.65, 31.15, 34.95, 31.35)
    trips_data = trips_data.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    
    # Create visualization
    output_file = create_html_file(trips_data, bounds, "route_intensity_interactive")
    
    print(f"\nVisualization saved to: {output_file}")
    print("\nVisualization completed!")

if __name__ == "__main__":
    main()