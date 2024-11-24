import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import logging
from config import BUILDINGS_FILE
from shapely.geometry import Point
from pyproj import Transformer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MAPBOX_API_KEY, OUTPUT_DIR

POI_RADIUS = 0.0018  # about 200 meters in decimal degrees

# Update POI_INFO to match line_roads.py colors with higher brightness
POI_INFO = {
    'BGU': {'color': [80, 240, 80, 200], 'lat': 31.2614375, 'lon': 34.7995625},        # Bright green
    'Gav Yam': {'color': [80, 200, 255, 200], 'lat': 31.2641875, 'lon': 34.8128125},   # Bright blue
    'Soroka Hospital': {'color': [220, 220, 220, 200], 'lat': 31.2579375, 'lon': 34.8003125}  # Bright white
}

def load_trip_data():
    """Load and process trip data for animation"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    logger.info(f"Loading trip data from: {file_path}")
    
    try:
        trips_gdf = gpd.read_file(file_path)
        raw_trip_count = trips_gdf['num_trips'].sum()
        logger.info(f"Loaded {len(trips_gdf)} routes representing {raw_trip_count:,} total trips")
    except Exception as e:
        logger.error(f"Error loading trip data: {str(e)}")
        raise
    
    # Calculate center coordinates from the bounds of all trips
    total_bounds = trips_gdf.total_bounds
    center_lon = (total_bounds[0] + total_bounds[2]) / 2
    center_lat = (total_bounds[1] + total_bounds[3]) / 2
    
    # Convert to format needed for animation - keep original num_trips
    trips_data = []
    processed_trips = 0
    
    for idx, row in trips_gdf.iterrows():
        try:
            coords = list(row.geometry.coords)
            timestamps = list(range(len(coords)))
            num_trips = int(row['num_trips'])
            processed_trips += num_trips
            
            trips_data.append({
                'vendor': 0,
                'path': [[float(x), float(y)] for x, y in coords],
                'timestamps': timestamps,
                'num_trips': num_trips
            })
            
        except Exception as e:
            logger.error(f"Error processing trip {idx}: {str(e)}")
            continue
    
    logger.info(f"Verification:")
    logger.info(f"  - Raw trips from GeoDataFrame: {raw_trip_count:,}")
    logger.info(f"  - Processed trips in animation: {processed_trips:,}")
    logger.info(f"  - Number of unique routes: {len(trips_data):,}")
    
    if raw_trip_count != processed_trips:
        logger.warning(f"Trip count mismatch! Some trips may have been lost in processing.")
    
    return trips_data, center_lat, center_lon, processed_trips

def load_building_data():
    """Load building data for 3D visualization"""
    file_path = os.path.join(OUTPUT_DIR, "buildings.geojson")
    logger.info(f"Loading building data from: {file_path}")
    
    try:
        buildings_gdf = gpd.read_file(BUILDINGS_FILE)
        
        # Convert to format needed for deck.gl
        buildings_data = []
        text_features = []
        
        # Create a transformer for POI coordinates
        transformer = Transformer.from_crs("EPSG:4326", buildings_gdf.crs, always_xy=True)
        
        for idx, building in buildings_gdf.iterrows():
            building_color = [74, 80, 87, 160]  # Default color
            try:
                # Get actual height from building data, default to 20 if not found
                height = float(building.get('height', 20))
                building_height = height * 1.5  # Scale height to match line_roads.py
                
                # Check if building is within radius of main POIs
                for poi_name, info in POI_INFO.items():
                    poi_x, poi_y = transformer.transform(info['lon'], info['lat'])
                    poi_point = Point(poi_x, poi_y)
                    
                    if building.geometry.centroid.distance(poi_point) <= POI_RADIUS:
                        building_height = min(40, height * 1000)  # Match line_roads.py height scaling
                        building_color = info['color']
                        
                        # Add text label for POI
                        text_features.append({
                            "position": [poi_x, poi_y, building_height + 10],
                            "text": poi_name,
                            "color": [255, 255, 255, 255]  # Bright white text
                        })
                        break
                
                buildings_data.append({
                    "polygon": list(building.geometry.exterior.coords),
                    "height": building_height,
                    "color": building_color
                })
            except Exception as e:
                logger.error(f"Skipping building due to error: {e}")
                continue
        
        logger.info(f"Loaded {len(buildings_data)} buildings")
        return buildings_data, text_features
    except Exception as e:
        logger.error(f"Error loading building data: {str(e)}")
        raise

def create_animation():
    trips_data, center_lat, center_lon, total_trips = load_trip_data()
    buildings_data, text_features = load_building_data()
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'>
        <title>Trip Animation</title>
        <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
        <script src='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js'></script>
        <script src='https://unpkg.com/popmotion@11.0.0/dist/popmotion.js'></script>
        <link href='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css' rel='stylesheet' />
        <style>
            body { margin: 0; padding: 0; }
            #container { width: 100vw; height: 100vh; position: relative; }
            .control-panel {
                position: absolute;
                top: 20px;
                left: 20px;
                background: #000000;
                padding: 12px;
                border-radius: 5px;
                color: #FFFFFF;
                font-family: Arial;
            }
            .methodology-container {
                position: fixed;
                top: 20px;
                right: 20px;
                background: #000000;
                padding: 12px;
                border-radius: 5px;
                color: #FFFFFF;
                font-family: Arial;
                max-width: 300px;
            }
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div class="control-panel">
            <div>
                <label>Trail Length: <span id="trail-value">5</span></label>
                <input type="range" min="1" max="100" value="5" id="trail-length" style="width: 200px">
            </div>
            <div>
                <label>Animation Speed: <span id="speed-value">2.5</span></label>
                <input type="range" min="0.1" max="5" step="0.1" value="2.5" id="animation-speed" style="width: 200px">
            </div>
        </div>
        <div class="methodology-container">
            <h3 style="margin: 0 0 10px 0;">Methodology</h3>
            <p style="margin: 0; font-size: 0.9em;">
                This visualization represents individual trips across Beer Sheva's road network.
                Total Daily Trips: %d<br><br>
                Colors indicate destinations:<br>
                • BGU (Green)<br>
                • Gav Yam (Blue)<br>
                • Soroka Hospital (White)
            </p>
        </div>
        <script>
            const TRIPS_DATA = %s;
            const BUILDINGS_DATA = %s;
            
            const ambientLight = new deck.AmbientLight({
                color: [255, 255, 255],
                intensity: 1.0
            });

            const pointLight = new deck.PointLight({
                color: [255, 255, 255],
                intensity: 2.0,
                position: [34.8, 31.25, 8000]  // Adjusted for Beer Sheva coordinates
            });

            const lightingEffect = new deck.LightingEffect({ambientLight, pointLight});
            
            const INITIAL_VIEW_STATE = {
                longitude: 34.8113,  // Ben Gurion University
                latitude: 31.2627,   // Ben Gurion University
                zoom: 13,
                pitch: 60,          // Increased pitch for better 3D view
                bearing: 0
            };
            
            const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json';
            
            let trailLength = 5;
            let animationSpeed = 2.5;
            const loopLength = 1800;
            let animation;
            
            const deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: MAP_STYLE,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true,
                effects: [lightingEffect]
            });
            
            function getPathColor(path) {
                const endPoint = path[path.length - 1];
                const isNearPOI = (point, poi) => {
                    const dx = point[0] - poi.lon;
                    const dy = point[1] - poi.lat;
                    return Math.sqrt(dx*dx + dy*dy) <= %f;
                };
                
                if (isNearPOI(endPoint, %s)) return [80, 240, 80];  // Bright green for BGU
                if (isNearPOI(endPoint, %s)) return [80, 200, 255]; // Bright blue for Gav Yam
                if (isNearPOI(endPoint, %s)) return [220, 220, 220]; // Bright white for Soroka
                
                return [253, 128, 93];  // Default color
            }
            
            function animate() {
                animation = popmotion.animate({
                    from: 0,
                    to: loopLength,
                    duration: (loopLength * 60) / animationSpeed,
                    repeat: Infinity,
                    onUpdate: time => {
                        const layers = [
                            new deck.PolygonLayer({
                                id: 'buildings',
                                data: BUILDINGS_DATA,
                                extruded: true,
                                wireframe: true,
                                opacity: 0.8,
                                getPolygon: d => d.polygon,
                                getElevation: d => d.height,
                                getFillColor: d => d.color,
                                getLineColor: [255, 255, 255, 50],
                                lineWidthMinPixels: 1,
                                material: {
                                    ambient: 0.2,
                                    diffuse: 0.8,
                                    shininess: 32,
                                    specularColor: [60, 64, 70]
                                }
                            }),
                            new deck.TripsLayer({
                                id: 'trips',
                                data: TRIPS_DATA,
                                getPath: d => d.path,
                                getTimestamps: d => d.timestamps,
                                getColor: d => getPathColor(d.path),
                                opacity: 0.8,
                                widthMinPixels: 2,
                                rounded: true,
                                trailLength,
                                currentTime: time,
                                getWidth: d => Math.sqrt(d.num_trips),
                                parameters: {
                                    depthTest: true,
                                    blend: false  // Disable blending
                                }
                            })
                        ];
                        
                        deckgl.setProps({
                            layers,
                            parameters: {
                                blend: false  // Disable blending at deck.gl level
                            }
                        });
                    }
                });
            }
            
            // Control panel handlers
            document.getElementById('trail-length').oninput = function() {
                trailLength = Number(this.value);
                document.getElementById('trail-value').textContent = this.value;
            };
            
            document.getElementById('animation-speed').oninput = function() {
                animationSpeed = Number(this.value);
                document.getElementById('speed-value').textContent = this.value;
                if (animation) {
                    animation.stop();
                }
                animate();
            };
            
            animate();
        </script>
    </body>
    </html>
    """
    
    # Generate the HTML file
    output_path = os.path.join(OUTPUT_DIR, "trip_animation.html")
    try:
        with open(output_path, 'w') as f:
            formatted_html = html_template % (
                total_trips,                             # Total trips count
                json.dumps(trips_data),                  # Trips data with num_trips
                json.dumps(buildings_data),              # Buildings data
                POI_RADIUS,                              # %f - POI radius as float
                json.dumps(POI_INFO['BGU']),             # %s - BGU POI info
                json.dumps(POI_INFO['Gav Yam']),         # %s - Gav Yam POI info
                json.dumps(POI_INFO['Soroka Hospital'])   # %s - Soroka POI info
            )
            f.write(formatted_html)
        logger.info(f"Animation saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error writing HTML file: {str(e)}")
        raise
    
    return output_path

if __name__ == "__main__":
    try:
        output_file = create_animation()
        print(f"Animation saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to create animation: {str(e)}")
        sys.exit(1) 