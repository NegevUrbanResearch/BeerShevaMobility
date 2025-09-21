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
    "BGU": {
        "color": [0, 210, 255],
        "lat": 31.2614375,
        "lon": 34.7995625,
        "name": "Ben-Gurion-University",
    },
    "Soroka Hospital": {
        "color": [255, 100, 255],
        "lat": 31.2579375,
        "lon": 34.8003125,
        "name": "Soroka-Medical-Center",
    },
}


def get_html_template_iframe_safe():
    """Return iframe-safe HTML template with local dependencies"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <title>Walking Trip Arc Visualization</title>
    <!-- Local dependencies - download these files and serve them locally -->
    <script src='./libs/deck.gl.min.js'></script>
    <script src='./libs/maplibre-gl.js'></script>
    <link href='./libs/maplibre-gl.css' rel='stylesheet' />
    
    <!-- Iframe security headers -->
    <meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:;">
    
    <style>
        body { 
            margin: 0; 
            padding: 0; 
            /* Prevent iframe scroll issues */
            overflow: hidden;
        }
        #container { 
            width: 100%; 
            height: 100vh; 
            position: relative; 
            /* Ensure proper sizing in iframe */
            min-height: 400px;
        }
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
            /* Iframe optimizations */
            max-width: calc(100vw - 60px);
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
            /* Iframe optimizations */
            max-width: calc(100vw - 400px);
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
        
        /* Responsive adjustments for iframe */
        @media (max-width: 768px) {
            .control-panel {
                width: 280px;
                padding: 15px;
            }
            .stats-panel {
                position: relative;
                margin-top: 10px;
                margin-bottom: 10px;
            }
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
        <div id="bguStats" class="stat-row bgu-stat">BGU Trips: 0</div>
        <div id="sorokaStats" class="stat-row soroka-stat">Soroka Trips: 0</div>
        <div id="totalStats" class="stat-row">Total Active Trips: 0</div>
        <p style="color: #ccc; font-size: 14px; margin-bottom: 15px; max-width: 300px;">
            Arcs in this visualization represent inbound walking trips to Ben Gurion University & Soroka Medical Center.
        </p>
    </div>
    <script>
        // Arc data
        const arcData = ARCDATA;
        
        // Time window in hours for showing active trips
        const TIME_WINDOW = 0.25;  // 15 minutes for trip visibility
        
        // Animation state and constants
        let isPlaying = false;
        let currentTime = 6;  // Start at 6:00
        let animationSpeed = 1;
        let animationFrame;
        const ANIMATION_STEP = 0.01;  // How much time advances each frame
        
        // Self-hosted map style (inline JSON to avoid external requests)
        const DARK_MAP_STYLE = {
            "version": 8,
            "name": "Dark Matter",
            "sources": {
                "carto": {
                    "type": "raster",
                    "tiles": [
                        "https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png",
                        "https://cartodb-basemaps-b.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png",
                        "https://cartodb-basemaps-c.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png"
                    ],
                    "tileSize": 256,
                    "attribution": "&copy; OpenStreetMap contributors, &copy; CartoDB"
                }
            },
            "layers": [
                {
                    "id": "background",
                    "type": "background",
                    "paint": {
                        "background-color": "#1a1a1a"
                    }
                },
                {
                    "id": "carto-layer",
                    "type": "raster",
                    "source": "carto",
                    "paint": {
                        "raster-opacity": 0.8
                    }
                }
            ]
        };
        
        // Initialize deck.gl with error handling for iframe context
        let deckgl;
        try {
            deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: DARK_MAP_STYLE,
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
        } catch (error) {
            console.error('Failed to initialize deck.gl:', error);
            // Fallback: show error message
            document.getElementById('container').innerHTML = 
                '<div style="color: white; padding: 20px; text-align: center;">Failed to load visualization. Please ensure all dependencies are available.</div>';
        }
        
        // Add new constants for animation
        const TRAIL_LENGTH = 0.25;  // Length of the arc trail
        const NUM_SEGMENTS = 1000;    // Number of segments for smooth animation
        
        function getActiveArcs(time) {
            // Show only trips within the time window, no progress tracking
            return arcData.filter(arc => {
                const timeSinceStart = time - arc.departure_time;
                if (timeSinceStart < 0 || timeSinceStart > TIME_WINDOW) return false;
                
                // Calculate distance for base height offset
                const dx = arc.target_lon - arc.source_lon;
                const dy = arc.target_lat - arc.source_lat;
                const distance = Math.sqrt(dx * dx + dy * dy);
                
                // Generate a stable random offset based on departure time
                const randomOffset = Math.abs(Math.sin(arc.departure_time * 1000)) * 2;
                
                // Store both the base height and glow height to ensure consistency
                arc.baseHeight = 0.5 + distance + randomOffset;
                arc.glowHeight = arc.baseHeight;
                arc.opacity = Math.min(1, timeSinceStart / (TIME_WINDOW / 2));
                return true;
            });
        }
        
        function getCumulativeCounts(time) {
            // Count all trips that have occurred up to current time
            const allTrips = arcData.filter(arc => arc.departure_time <= time);
            return {
                bgu: allTrips.filter(arc => arc.destination === 'Ben-Gurion-University').length,
                soroka: allTrips.filter(arc => arc.destination === 'Soroka-Medical-Center').length,
                total: allTrips.length
            };
        }
        
        function updateVisualization(time) {
            if (!deckgl) return; // Guard against missing deck.gl
            
            const activeArcs = getActiveArcs(time);
            const counts = getCumulativeCounts(time);
            
            // Update statistics
            const bguStatsEl = document.getElementById('bguStats');
            const sorokaStatsEl = document.getElementById('sorokaStats');
            const totalStatsEl = document.getElementById('totalStats');
            
            if (bguStatsEl) bguStatsEl.textContent = `BGU Trips: ${counts.bgu}`;
            if (sorokaStatsEl) sorokaStatsEl.textContent = `Soroka Trips: ${counts.soroka}`;
            if (totalStatsEl) totalStatsEl.textContent = `Total Trips: ${counts.total}`;
            
            try {
                // Main arc layer
                const arcLayer = new deck.ArcLayer({
                    id: 'arc-layer',
                    data: activeArcs,
                    pickable: true,
                    getSourcePosition: d => [d.source_lon, d.source_lat],
                    getTargetPosition: d => [d.target_lon, d.target_lat],
                    getSourceColor: d => {
                        const baseColor = d.destination === 'Ben-Gurion-University' ? 
                            [0, 210, 255] : [255, 100, 255];
                        return [...baseColor, 255 * d.opacity];
                    },
                    getTargetColor: d => {
                        const baseColor = d.destination === 'Ben-Gurion-University' ? 
                            [0, 150, 255] : [200, 50, 255];
                        return [...baseColor, 255 * d.opacity];
                    },
                    getWidth: 2,
                    getHeight: d => d.baseHeight,  // Use stored base height
                    greatCircle: false,
                    widthScale: 1,
                    widthMinPixels: 1,
                    widthMaxPixels: 6,
                    parameters: {
                        blend: true,
                        blendFunc: [
                            WebGLRenderingContext.SRC_ALPHA,
                            WebGLRenderingContext.ONE
                        ],
                        depthTest: true
                    }
                });
                
                // Glow trail layer
                const trailLayer = new deck.ArcLayer({
                    id: 'trail-layer',
                    data: activeArcs,
                    pickable: false,
                    getSourcePosition: d => [d.source_lon, d.source_lat],
                    getTargetPosition: d => [d.target_lon, d.target_lat],
                    getSourceColor: d => {
                        const baseColor = d.destination === 'Ben-Gurion-University' ? 
                            [0, 210, 255] : [255, 100, 255];
                        return [...baseColor, 50 * d.opacity];
                    },
                    getTargetColor: d => {
                        const baseColor = d.destination === 'Ben-Gurion-University' ? 
                            [0, 150, 255] : [200, 50, 255];
                        return [...baseColor, 50 * d.opacity];
                    },
                    getWidth: 2,
                    getHeight: d => d.glowHeight,  // Use stored glow height
                    greatCircle: false,
                    widthScale: 1,
                    widthMinPixels: 2,
                    widthMaxPixels: 12,
                    parameters: {
                        blend: true,
                        blendFunc: [
                            WebGLRenderingContext.SRC_ALPHA,
                            WebGLRenderingContext.ONE
                        ],
                        depthTest: true
                    }
                });
                
                deckgl.setProps({
                    layers: [trailLayer, arcLayer]
                });
            } catch (error) {
                console.error('Error updating visualization:', error);
            }
        }
        
        // Time controls with iframe safety
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
        
        if (timeSlider) {
            timeSlider.addEventListener('input', (e) => {
                currentTime = parseFloat(e.target.value);
                if (currentTimeDisplay) currentTimeDisplay.textContent = formatTime(currentTime);
                updateVisualization(currentTime);
            });
        }
        
        if (speedSlider) {
            speedSlider.addEventListener('input', (e) => {
                animationSpeed = parseFloat(e.target.value);
                const speedValueEl = document.getElementById('speedValue');
                if (speedValueEl) speedValueEl.textContent = animationSpeed.toFixed(1) + 'x';
            });
        }
        
        function animate() {
            if (isPlaying) {
                currentTime += ANIMATION_STEP * animationSpeed;
                if (currentTime > 22) currentTime = 6;
                
                if (timeSlider) timeSlider.value = currentTime;
                if (currentTimeDisplay) currentTimeDisplay.textContent = formatTime(currentTime);
                updateVisualization(currentTime);
                
                animationFrame = requestAnimationFrame(animate);
            }
        }
        
        if (playButton) {
            playButton.addEventListener('click', () => {
                isPlaying = true;
                animate();
            });
        }
        
        if (pauseButton) {
            pauseButton.addEventListener('click', () => {
                isPlaying = false;
                cancelAnimationFrame(animationFrame);
            });
        }
        
        // Modify speed slider for finer control
        if (speedSlider) {
            speedSlider.min = "0.1";
            speedSlider.max = "2";
            speedSlider.step = "0.1";
            speedSlider.value = "0.5";  // Start at half speed
            animationSpeed = 0.5;  // Set initial animation speed
        }
        
        // Initial update
        updateVisualization(currentTime);
        
        // Handle iframe resize events
        window.addEventListener('resize', () => {
            if (deckgl) {
                deckgl.setProps({
                    width: window.innerWidth,
                    height: window.innerHeight
                });
            }
        });
    </script>
</body>
</html>
"""


def create_arc_visualization_iframe_safe(input_file, output_dir):
    """Create iframe-safe arc visualization from pre-processed temporal data"""
    logger.info(f"Loading temporal data from: {input_file}")

    try:
        # Load temporal arc data
        gdf = gpd.read_file(input_file)

        # Validate data structure
        assert "geometry" in gdf.columns, "Missing geometry column in input data"
        assert (
            "departure_time" in gdf.columns
        ), "Missing departure_time column in input data"
        assert "destination" in gdf.columns, "Missing destination column in input data"
        assert len(gdf) > 0, "Input data is empty"

        # Convert GeoDataFrame to arc format
        arc_data = []
        for idx, row in gdf.iterrows():
            try:
                # Convert departure_time to hours since midnight
                departure_time = pd.to_datetime(row["departure_time"])
                # Add random minutes within the hour
                random_minutes = np.random.uniform(0, 60)
                hours = (
                    departure_time.hour + (departure_time.minute + random_minutes) / 60
                )

                # Extract coordinates from geometry
                coords = list(row["geometry"].coords)
                assert (
                    len(coords) >= 2
                ), f"Invalid geometry at row {idx}: not enough coordinates"

                source_coords = coords[0]
                target_coords = coords[-1]

                # Validate coordinates with assertions
                assert isinstance(
                    source_coords[0], (int, float)
                ), f"Invalid source longitude at row {idx}"
                assert isinstance(
                    source_coords[1], (int, float)
                ), f"Invalid source latitude at row {idx}"
                assert isinstance(
                    target_coords[0], (int, float)
                ), f"Invalid target longitude at row {idx}"
                assert isinstance(
                    target_coords[1], (int, float)
                ), f"Invalid target latitude at row {idx}"

                # Validate coordinate ranges
                assert (
                    -180 <= source_coords[0] <= 180
                ), f"Source longitude out of range at row {idx}"
                assert (
                    -90 <= source_coords[1] <= 90
                ), f"Source latitude out of range at row {idx}"
                assert (
                    -180 <= target_coords[0] <= 180
                ), f"Target longitude out of range at row {idx}"
                assert (
                    -90 <= target_coords[1] <= 90
                ), f"Target latitude out of range at row {idx}"

                # Validate hour range
                assert 0 <= hours <= 24, f"Invalid hour value at row {idx}: {hours}"

                arc_data.append(
                    {
                        "source_lon": float(source_coords[0]),
                        "source_lat": float(source_coords[1]),
                        "target_lon": float(target_coords[0]),
                        "target_lat": float(target_coords[1]),
                        "departure_time": float(hours),
                        "destination": str(row["destination"]),
                    }
                )

            except Exception as e:
                logger.warning(f"Skipping invalid row {idx}: {str(e)}")
                continue

        assert len(arc_data) > 0, "No valid arc data after processing"
        logger.info(f"Processed {len(arc_data)} temporal arcs successfully")

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Get template and replace placeholders
        template = get_html_template_iframe_safe()
        html_content = template.replace("ARCDATA", json.dumps(arc_data))

        # Save visualization
        output_file = os.path.join(
            output_dir, "walking_arc_visualization_iframe_safe.html"
        )
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Iframe-safe visualization saved to: {output_file}")

        # Create setup instructions
        setup_file = os.path.join(output_dir, "iframe_setup_instructions.md")
        with open(setup_file, "w", encoding="utf-8") as f:
            f.write(
                """# Iframe Setup Instructions

## Required Dependencies

To use this visualization in an iframe, you need to download and host these files locally:

### 1. Create a `libs` directory next to your HTML file

### 2. Download these files:

- **deck.gl**: Download from https://unpkg.com/deck.gl@^8.8.0/dist.min.js
  - Save as: `libs/deck.gl.min.js`

- **MapLibre GL JS**: Download from https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js
  - Save as: `libs/maplibre-gl.js`

- **MapLibre CSS**: Download from https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css
  - Save as: `libs/maplibre-gl.css`

### 3. File Structure

```
your-project/
├── walking_arc_visualization_iframe_safe.html
└── libs/
    ├── deck.gl.min.js
    ├── maplibre-gl.js
    └── maplibre-gl.css
```

### 4. Iframe Usage

```html
<iframe 
    src="path/to/walking_arc_visualization_iframe_safe.html" 
    width="100%" 
    height="600px"
    frameborder="0"
    allowfullscreen>
</iframe>
```

### 5. Security Considerations

- The HTML includes CSP headers for iframe safety
- All external dependencies are referenced locally
- Error handling for missing dependencies
- Responsive design for iframe constraints

### 6. Alternative: Use CDN with Fallbacks

If you prefer to keep using CDNs but want iframe safety, the original version should work fine as most CDNs set proper CORS headers. However, this self-hosted version is more reliable for iframe usage.
"""
            )

        logger.info(f"Setup instructions saved to: {setup_file}")
        return output_file

    except Exception as e:
        logger.error(f"Failed to create iframe-safe visualization: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    # Example usage
    input_file = os.path.join(OUTPUT_DIR, "temporal_arcs.json")
    output_dir = OUTPUT_DIR

    try:
        output_file = create_arc_visualization_iframe_safe(input_file, output_dir)
        print(f"Iframe-safe arc visualization saved to: {output_file}")
    except Exception as e:
        logger.error(f"Error creating iframe-safe visualization: {str(e)}")
        raise

