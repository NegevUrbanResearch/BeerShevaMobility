import pandas as pd
import geopandas as gpd
import numpy as np
import os
import logging
import json
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
POI_INFO = {
    'BGU': {
        'color': [0, 210, 255],
        'lat': 31.2614375,
        'lon': 34.7995625,
        'name': 'Ben-Gurion-University'
    },
    'Soroka Hospital': {
        'color': [255, 100, 255],
        'lat': 31.2579375,
        'lon': 34.8003125,
        'name': 'Soroka-Medical-Center'
    }
}

def get_html_template():
    """Return HTML template with proper escaping"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <title>Walking Trip Arc Visualization</title>
    <script src='https://unpkg.com/deck.gl@^8.8.0/dist.min.js'></script>
    <script src='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js'></script>
    <link href='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css' rel='stylesheet' />
    <style>
        body { margin: 0; padding: 0; }
        #container { width: 100vw; height: 100vh; position: relative; }
        .control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0, 0, 0, 0.85);
            padding: 20px;
            border-radius: 10px;
            color: #FFFFFF;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            z-index: 1;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(5px);
            width: 320px;
        }
        .control-panel h3 {
            margin: 0 0 15px 0;
            font-size: 18px;
            font-weight: 500;
            color: #ffffff;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .time-control-group {
            background: rgba(255, 255, 255, 0.1);
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
        }
        .time-slider {
            width: 100%;
            margin: 10px 0;
            -webkit-appearance: none;
            height: 4px;
            background: #4a4a4a;
            border-radius: 2px;
            outline: none;
        }
        .time-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 18px;
            height: 18px;
            background: #00d2ff;
            border-radius: 50%;
            cursor: pointer;
            transition: all 0.2s;
        }
        .time-slider::-webkit-slider-thumb:hover {
            transform: scale(1.2);
        }
        .button-group {
            display: flex;
            gap: 10px;
            margin: 15px 0;
        }
        .control-button {
            flex: 1;
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            background: #00d2ff;
            color: #000;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        .control-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 2px 4px rgba(0, 210, 255, 0.2);
        }
        .control-button.pause {
            background: #ff4b4b;
            color: white;
        }
        .speed-control {
            margin-top: 15px;
        }
        .speed-control label {
            display: block;
            margin-bottom: 8px;
            font-size: 14px;
            color: #ccc;
        }
        #currentTime {
            font-size: 24px;
            font-weight: 600;
            text-align: center;
            margin: 10px 0;
            color: #00d2ff;
            font-family: 'Courier New', monospace;
        }
        .stats-panel {
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.85);
            padding: 20px;
            border-radius: 10px;
            color: #FFFFFF;
            font-family: Arial;
            z-index: 1;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            backdrop-filter: blur(5px);
        }
        .stats-panel h3 {
            margin: 0 0 15px 0;
            font-size: 18px;
            font-weight: 500;
            letter-spacing: 1px;
        }
        .stat-row {
            margin: 10px 0;
            font-size: 16px;
        }
        .bgu-stat {
            color: #00d2ff;
        }
        .soroka-stat {
            color: #ff64ff;
        }
    </style>
</head>
<body>
    <div id="container"></div>
    <div class="control-panel">
        <h3>Time Controls</h3>
        <div class="time-control-group">
            <div id="currentTime">08:00</div>
            <input type="range" min="6" max="22" value="8" step="0.25" class="time-slider" id="timeSlider">
            <div class="button-group">
                <button id="playButton" class="control-button">▶ Play</button>
                <button id="pauseButton" class="control-button pause">⏸ Pause</button>
            </div>
            <div class="speed-control">
                <label>Animation Speed: <span id="speedValue">1x</span></label>
                <input type="range" min="0.1" max="5" step="0.1" value="1" id="speedSlider" class="time-slider">
            </div>
        </div>
    </div>
    <div class="stats-panel">
        <h3>Cumulative Statistics</h3>
        <div id="bguStats" class="stat-row bgu-stat">BGU Total Trips: 0</div>
        <div id="sorokaStats" class="stat-row soroka-stat">Soroka Total Trips: 0</div>
        <div id="totalStats" class="stat-row">Total Trips: 0</div>
    </div>
    <script>
        // Arc data
        const arcData = ARCDATA;
        
        // Time window in hours for showing active trips
        const TIME_WINDOW = 0.5;  // 30 minutes window to show active trips
        const ANIMATION_STEP = 0.002;  // Smaller step for slower time progression
        
        // Animation state
        let isPlaying = false;
        let currentTime = 8;  // Start at 8:00
        let animationSpeed = 1;
        let animationFrame;
        
        // Mapbox configuration
        const MAPBOX_TOKEN = 'MAPBOX_API_KEY_PLACEHOLDER';  // Will be replaced by Python
        
        // Initialize deck.gl
        const deckgl = new deck.DeckGL({
            container: 'container',
            mapStyle: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
            initialViewState: {
                longitude: 34.8113,
                latitude: 31.2627,
                zoom: 13,
                pitch: 45,
                bearing: 0
            },
            controller: true,
            getTooltip: ({object}) => object && {
                html: `<div>Trip to ${object.destination}</div>`,
                style: {
                    backgroundColor: '#f5f5f5',
                    fontSize: '12px'
                }
            }
        });
        
        // Add new constants for animation
        const TRAIL_LENGTH = 5;  // Length of the arc trail
        const NUM_SEGMENTS = 2000;    // Number of segments for smooth animation
        
        function getActiveArcs(time) {
            const activeArcs = arcData.filter(arc => {
                const arcTime = arc.departure_time;
                return arcTime <= time;
            }).map(arc => {
                const progress = Math.min(1, (time - arc.departure_time) / TIME_WINDOW);
                return {...arc, progress};
            });
            
            return activeArcs;
        }
        
        function updateVisualization(time) {
            const activeArcs = getActiveArcs(time);
            
            const bguTrips = activeArcs.filter(arc => arc.destination === 'Ben-Gurion-University').length;
            const sorokaTrips = activeArcs.filter(arc => arc.destination === 'Soroka-Medical-Center').length;
            
            document.getElementById('bguStats').textContent = `BGU Total Trips: ${bguTrips}`;
            document.getElementById('sorokaStats').textContent = `Soroka Total Trips: ${sorokaTrips}`;
            document.getElementById('totalStats').textContent = `Total Trips: ${activeArcs.length}`;
            
            // Create enhanced arc layer
            const arcLayer = new deck.ArcLayer({
                id: 'arc-layer',
                data: activeArcs,
                pickable: true,
                getSourcePosition: d => [d.source_lon, d.source_lat],
                getTargetPosition: d => [d.target_lon, d.target_lat],
                getSourceColor: d => {
                    const baseColor = d.destination === 'Ben-Gurion-University' ? 
                        [0, 210, 255] : [255, 100, 255];
                    return [...baseColor, 255 * (1 - d.progress)];  // Fade based on progress
                },
                getTargetColor: d => {
                    const baseColor = d.destination === 'Ben-Gurion-University' ? 
                        [0, 150, 255] : [200, 50, 255];
                    return [...baseColor, 255 * d.progress];  // Intensify based on progress
                },
                getWidth: d => 2 * (1 + d.progress),  // Reduced width for walking scale
                getHeight: d => 1,  // Constant height
                greatCircle: false,
                widthScale: 1,
                widthMinPixels: 2,
                widthMaxPixels: 2,  // Reduced maximum width
                parameters: {
                    blend: true,
                    blendFunc: [
                        WebGLRenderingContext.SRC_ALPHA,
                        WebGLRenderingContext.ONE  // Additive blending for glow effect
                    ]
                }
            });
            
            // Add a second layer for the glowing trail effect
            const trailLayer = new deck.ArcLayer({
                id: 'trail-layer',
                data: activeArcs,
                pickable: false,
                getSourcePosition: d => [d.source_lon, d.source_lat],
                getTargetPosition: d => [d.target_lon, d.target_lat],
                getSourceColor: d => {
                    const baseColor = d.destination === 'Ben-Gurion-University' ? 
                        [0, 210, 255] : [255, 100, 255];
                    return [...baseColor, 50];  // Low opacity for trail
                },
                getTargetColor: d => {
                    const baseColor = d.destination === 'Ben-Gurion-University' ? 
                        [0, 150, 255] : [200, 50, 255];
                    return [...baseColor, 50];  // Low opacity for trail
                },
                getWidth: d => 4,  // Reduced trail width
                greatCircle: false,
                widthScale: 1,
                widthMinPixels: 2,
                widthMaxPixels: 12,  // Reduced maximum trail width
                parameters: {
                    blend: true,
                    blendFunc: [
                        WebGLRenderingContext.SRC_ALPHA,
                        WebGLRenderingContext.ONE
                    ]
                }
            });
            
            deckgl.setProps({
                layers: [trailLayer, arcLayer]
            });
        }
        
        // Time controls
        const timeSlider = document.getElementById('timeSlider');
        const currentTimeDisplay = document.getElementById('currentTime');
        const playButton = document.getElementById('playButton');
        const pauseButton = document.getElementById('pauseButton');
        const speedSlider = document.getElementById('speedSlider');
        
        function formatTime(time) {
            const hours = Math.floor(time);
            const minutes = Math.round((time % 1) * 60);
            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
        }
        
        timeSlider.addEventListener('input', (e) => {
            currentTime = parseFloat(e.target.value);
            currentTimeDisplay.textContent = formatTime(currentTime);
            updateVisualization(currentTime);
        });
        
        speedSlider.addEventListener('input', (e) => {
            animationSpeed = parseFloat(e.target.value);
            document.getElementById('speedValue').textContent = animationSpeed.toFixed(1) + 'x';
        });
        
        function animate() {
            if (isPlaying) {
                currentTime += ANIMATION_STEP * animationSpeed;
                if (currentTime > 22) currentTime = 6;
                
                timeSlider.value = currentTime;
                currentTimeDisplay.textContent = formatTime(currentTime);
                updateVisualization(currentTime);
                
                animationFrame = requestAnimationFrame(animate);
            }
        }
        
        playButton.addEventListener('click', () => {
            isPlaying = true;
            animate();
        });
        
        pauseButton.addEventListener('click', () => {
            isPlaying = false;
            cancelAnimationFrame(animationFrame);
        });
        
        // Modify speed slider for finer control
        speedSlider.min = "0.1";
        speedSlider.max = "2";
        speedSlider.step = "0.1";
        speedSlider.value = "0.5";  // Start at half speed
        animationSpeed = 0.5;  // Set initial animation speed
        
        // Initial update
        updateVisualization(currentTime);
    </script>
</body>
</html>
"""

def create_arc_visualization(input_file, output_dir):
    """Create arc visualization from pre-processed temporal data"""
    logger.info(f"Loading temporal data from: {input_file}")
    
    try:
        # Load temporal arc data
        gdf = gpd.read_file(input_file)
        
        # Convert GeoDataFrame to arc format
        arc_data = []
        for _, row in gdf.iterrows():
            # Convert departure_time to hours since midnight
            departure_time = pd.to_datetime(row['departure_time'])
            # Add random minutes within the hour
            random_minutes = np.random.uniform(0, 60)
            hours = departure_time.hour + (departure_time.minute + random_minutes) / 60
            
            # Extract coordinates from geometry
            coords = list(row['geometry'].coords)
            source_coords = coords[0]
            target_coords = coords[-1]
            
            # Validate coordinates
            if not (isinstance(source_coords[0], (int, float)) and 
                   isinstance(source_coords[1], (int, float)) and
                   isinstance(target_coords[0], (int, float)) and
                   isinstance(target_coords[1], (int, float))):
                logger.warning(f"Invalid coordinates found: {source_coords}, {target_coords}")
                continue
                
            arc_data.append({
                'source_lon': float(source_coords[0]),  # Ensure float
                'source_lat': float(source_coords[1]),
                'target_lon': float(target_coords[0]),
                'target_lat': float(target_coords[1]),
                'departure_time': float(hours),  # Ensure float
                'destination': str(row['destination'])  # Ensure string
            })
        
        logger.info(f"Processed {len(arc_data)} temporal arcs")
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get template and replace placeholders
        template = get_html_template()
        html_content = template.replace('ARCDATA', json.dumps(arc_data))
        
        # Save visualization
        output_file = os.path.join(output_dir, "walking_arc_visualization.html")
        with open(output_file, 'w') as f:
            f.write(html_content)
            
        logger.info(f"Visualization saved to: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Failed to create visualization: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Example usage
    input_file = os.path.join(OUTPUT_DIR, "temporal_arcs.json")
    output_dir = OUTPUT_DIR
    
    try:
        output_file = create_arc_visualization(input_file, output_dir)
        print(f"Arc visualization saved to: {output_file}")
    except Exception as e:
        logger.error(f"Error creating visualization: {str(e)}")
        raise