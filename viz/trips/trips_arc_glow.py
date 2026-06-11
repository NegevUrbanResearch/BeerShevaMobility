import json
import logging
import os
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from mobility.config import OUTPUT_DIR, OUTPUT_ROOT
from mobility.utils.walk_work_trips import (
    build_work_share_lookup,
    compute_work_hourly_distributions,
    get_work_share,
)

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

def get_theme_config(light_theme: bool) -> dict:
    if light_theme:
        return {
            "map_style": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            "panel_bg": "rgba(255, 255, 255, 0.92)",
            "panel_color": "#1a1a1a",
            "panel_shadow": "0 1px 4px rgba(0, 0, 0, 0.15)",
            "group_bg": "rgba(0, 0, 0, 0.05)",
            "slider_bg": "#d1d5db",
            "speed_label_color": "#4b5563",
            "time_color": "#0369a1",
            "button_bg": "#0284c7",
            "button_color": "#ffffff",
            "pause_bg": "#dc2626",
            "pause_color": "#ffffff",
            "stats_note_color": "#4b5563",
            "tooltip_bg": "#ffffff",
            "title": "Work Trip Arc Visualization",
            "description": (
                "Inbound work-purpose walking trips to Ben-Gurion University "
                "and Soroka Medical Center."
            ),
            "bgu_arc": "[0, 200, 90]",
            "bgu_arc_target": "[0, 150, 70]",
            "soroka_arc": "[170, 0, 255]",
            "soroka_arc_target": "[130, 0, 200]",
        }
    return {
        "map_style": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        "panel_bg": "rgba(0, 0, 0, 0.85)",
        "panel_color": "#FFFFFF",
        "panel_shadow": "0 4px 6px rgba(0, 0, 0, 0.1)",
        "group_bg": "rgba(255, 255, 255, 0.1)",
        "slider_bg": "#4a4a4a",
        "speed_label_color": "#ccc",
        "time_color": "#00d2ff",
        "button_bg": "#00d2ff",
        "button_color": "#000",
        "pause_bg": "#ff4b4b",
        "pause_color": "#ffffff",
        "stats_note_color": "#ccc",
        "tooltip_bg": "#f5f5f5",
        "title": "Walking Trip Arc Visualization",
        "description": (
            "Arcs in this visualization represent inbound walking trips to "
            "Ben Gurion University & Soroka Medical Center."
        ),
        "bgu_arc": "[0, 210, 255]",
        "bgu_arc_target": "[0, 150, 255]",
        "soroka_arc": "[255, 100, 255]",
        "soroka_arc_target": "[200, 50, 255]",
    }


def apply_theme_to_template(template: str, light_theme: bool) -> str:
    theme = get_theme_config(light_theme)
    replacements = {
        "THEME_TITLE": theme["title"],
        "THEME_MAP_STYLE": theme["map_style"],
        "THEME_PANEL_BG": theme["panel_bg"],
        "THEME_PANEL_COLOR": theme["panel_color"],
        "THEME_PANEL_SHADOW": theme["panel_shadow"],
        "THEME_GROUP_BG": theme["group_bg"],
        "THEME_SLIDER_BG": theme["slider_bg"],
        "THEME_SPEED_LABEL_COLOR": theme["speed_label_color"],
        "THEME_TIME_COLOR": theme["time_color"],
        "THEME_BUTTON_BG": theme["button_bg"],
        "THEME_BUTTON_COLOR": theme["button_color"],
        "THEME_PAUSE_BG": theme["pause_bg"],
        "THEME_PAUSE_COLOR": theme["pause_color"],
        "THEME_STATS_NOTE_COLOR": theme["stats_note_color"],
        "THEME_TOOLTIP_BG": theme["tooltip_bg"],
        "THEME_DESCRIPTION": theme["description"],
        "THEME_BGU_ARC": theme["bgu_arc"],
        "THEME_BGU_ARC_TARGET": theme["bgu_arc_target"],
        "THEME_SOROKA_ARC": theme["soroka_arc"],
        "THEME_SOROKA_ARC_TARGET": theme["soroka_arc_target"],
    }
    for key, value in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        template = template.replace(key, value)
    return template


def get_html_template(light_theme: bool = False):
    """Return HTML template with proper escaping"""
    template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <title>THEME_TITLE</title>
    <script src='https://unpkg.com/deck.gl@^8.8.0/dist.min.js'></script>
    <script src='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js'></script>
    <link href='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css' rel='stylesheet' />
    <style>
        body { margin: 0; padding: 0; }
        #container { width: 100vw; height: 100vh; position: relative; }
        
        /* Basic RTL support - let the RTL plugin handle map labels */
        
        .control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            background: THEME_PANEL_BG;
            padding: 20px;
            border-radius: 10px;
            color: THEME_PANEL_COLOR;
            font-family: 'Helvetica Neue', Arial, sans-serif;
            z-index: 1;
            box-shadow: THEME_PANEL_SHADOW;
            backdrop-filter: blur(5px);
            width: 320px;
        }
        .control-panel h3 {
            margin: 0 0 15px 0;
            font-size: 18px;
            font-weight: 500;
            color: THEME_PANEL_COLOR;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .time-control-group {
            background: THEME_GROUP_BG;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
        }
        .time-slider {
            width: 100%;
            margin: 10px 0;
            -webkit-appearance: none;
            height: 4px;
            background: THEME_SLIDER_BG;
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
            background: THEME_BUTTON_BG;
            color: THEME_BUTTON_COLOR;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        .control-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 2px 4px rgba(0, 210, 255, 0.2);
        }
        .control-button.pause {
            background: THEME_PAUSE_BG;
            color: THEME_PAUSE_COLOR;
        }
        .speed-control {
            margin-top: 15px;
        }
        .speed-control label {
            display: block;
            margin-bottom: 8px;
            font-size: 14px;
            color: THEME_SPEED_LABEL_COLOR;
        }
        #currentTime {
            font-size: 24px;
            font-weight: 600;
            text-align: center;
            margin: 10px 0;
            color: THEME_TIME_COLOR;
            font-family: 'Courier New', monospace;
        }
        .stats-panel {
            position: absolute;
            top: 20px;
            right: 20px;
            background: THEME_PANEL_BG;
            padding: 20px;
            border-radius: 10px;
            color: THEME_PANEL_COLOR;
            font-family: Arial;
            z-index: 1;
            box-shadow: THEME_PANEL_SHADOW;
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
            color: #059669;
        }
        .soroka-stat {
            color: #9333ea;
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
        <p style="color: THEME_STATS_NOTE_COLOR; font-size: 14px; margin-bottom: 15px; max-width: 300px;">
            THEME_DESCRIPTION
        </p>
    </div>
    <script>
        const BGU_ARC_COLOR = THEME_BGU_ARC;
        const BGU_ARC_TARGET = THEME_BGU_ARC_TARGET;
        const SOROKA_ARC_COLOR = THEME_SOROKA_ARC;
        const SOROKA_ARC_TARGET = THEME_SOROKA_ARC_TARGET;

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
        
        // Mapbox configuration  
        const MAPBOX_TOKEN = 'MAPBOX_API_KEY_PLACEHOLDER';  // Will be replaced by Python
        
        // Initialize RTL text plugin for Hebrew support
        if (typeof maplibregl !== 'undefined' && maplibregl.setRTLTextPlugin) {
            maplibregl.setRTLTextPlugin(
                'https://unpkg.com/@mapbox/mapbox-gl-rtl-text@0.3.0/dist/mapbox-gl-rtl-text.js',
                true // Lazy load the plugin
            );
        }
        
        // Initialize deck.gl
        const deckgl = new deck.DeckGL({
            container: 'container',
            mapStyle: 'THEME_MAP_STYLE',
            initialViewState: {
                longitude: 34.8113,
                latitude: 31.2627,
                zoom: 13,
                pitch: 45,
                bearing: 0
            },
            controller: true,
            getTooltip: ({object}) => object && {
                html: `<div style="direction: ltr; text-align: left;">Trip to ${object.destination}</div>`,
                style: {
                    backgroundColor: 'THEME_TOOLTIP_BG',
                    fontSize: '12px',
                    direction: 'ltr',
                    textAlign: 'left'
                }
            }
        });
        
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
            const activeArcs = getActiveArcs(time);
            const counts = getCumulativeCounts(time);
            
            // Update statistics
            document.getElementById('bguStats').textContent = `BGU Trips: ${counts.bgu}`;
            document.getElementById('sorokaStats').textContent = `Soroka Trips: ${counts.soroka}`;
            document.getElementById('totalStats').textContent = `Total Trips: ${counts.total}`;
            
            // Main arc layer
            const arcLayer = new deck.ArcLayer({
                id: 'arc-layer',
                data: activeArcs,
                pickable: true,
                getSourcePosition: d => [d.source_lon, d.source_lat],
                getTargetPosition: d => [d.target_lon, d.target_lat],
                getSourceColor: d => {
                    const baseColor = d.destination === 'Ben-Gurion-University' ?
                        BGU_ARC_COLOR : SOROKA_ARC_COLOR;
                    return [...baseColor, 255 * d.opacity];
                },
                getTargetColor: d => {
                    const baseColor = d.destination === 'Ben-Gurion-University' ?
                        BGU_ARC_TARGET : SOROKA_ARC_TARGET;
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
                        BGU_ARC_COLOR : SOROKA_ARC_COLOR;
                    return [...baseColor, 50 * d.opacity];
                },
                getTargetColor: d => {
                    const baseColor = d.destination === 'Ben-Gurion-University' ?
                        BGU_ARC_TARGET : SOROKA_ARC_TARGET;
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
    return apply_theme_to_template(template, light_theme)


def load_arc_data_from_temporal(input_file) -> list:
    gdf = gpd.read_file(input_file)
    arc_data = []
    for _, row in gdf.iterrows():
        departure_time = pd.to_datetime(row["departure_time"])
        random_minutes = np.random.uniform(0, 60)
        hours = departure_time.hour + (departure_time.minute + random_minutes) / 60
        coords = list(row["geometry"].coords)
        source_coords = coords[0]
        target_coords = coords[-1]
        if not all(isinstance(value, (int, float)) for value in (*source_coords, *target_coords)):
            logger.warning(f"Invalid coordinates found: {source_coords}, {target_coords}")
            continue
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
    return arc_data


def build_work_arc_data(routes_file: Path, seed: int = 42) -> list:
    np.random.seed(seed)
    routes_gdf = gpd.read_file(routes_file)
    work_lookup = build_work_share_lookup()
    hourly_dists = compute_work_hourly_distributions()
    arc_data = []

    for _, row in routes_gdf.iterrows():
        num_trips = int(round(float(row["num_trips"]) * get_work_share(row, work_lookup)))
        if num_trips <= 0:
            continue

        destination = row["destination"]
        if destination not in hourly_dists:
            continue

        hours = list(hourly_dists[destination].keys())
        probs = list(hourly_dists[destination].values())
        coords = list(row.geometry.coords)
        source_coords = coords[0]
        target_coords = coords[-1]

        for _ in range(num_trips):
            hour = np.random.choice(hours, p=probs)
            arc_data.append(
                {
                    "source_lon": float(source_coords[0]),
                    "source_lat": float(source_coords[1]),
                    "target_lon": float(target_coords[0]),
                    "target_lat": float(target_coords[1]),
                    "departure_time": float(hour + np.random.uniform(0, 1)),
                    "destination": str(destination),
                }
            )
    return arc_data


def create_arc_visualization(
    input_file=None,
    output_dir=None,
    work_trips_only: bool = False,
    light_theme: bool = False,
    output_filename: str = "walking_arc_visualization_glow.html",
):
    """Create arc visualization from temporal arcs or work-filtered walk routes."""
    output_dir = Path(output_dir or OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if work_trips_only:
            routes_file = OUTPUT_DIR / "walk_routes_inbound.geojson"
            logger.info("Building work-trip arcs from %s", routes_file)
            arc_data = build_work_arc_data(routes_file)
        else:
            input_file = Path(input_file or OUTPUT_DIR / "temporal_arcs.json")
            logger.info("Loading temporal data from: %s", input_file)
            arc_data = load_arc_data_from_temporal(input_file)

        logger.info("Processed %s arcs", len(arc_data))
        template = get_html_template(light_theme=light_theme)
        html_content = template.replace("ARCDATA", json.dumps(arc_data))

        output_file = output_dir / output_filename
        output_file.write_text(html_content)
        logger.info("Visualization saved to: %s", output_file)
        return output_file

    except Exception as e:
        logger.error("Failed to create visualization: %s", str(e))
        raise


if __name__ == "__main__":
    create_arc_visualization(
        output_dir=OUTPUT_ROOT / "working_trips",
        work_trips_only=True,
        light_theme=True,
        output_filename="walking_arc_visualization.html",
    )
