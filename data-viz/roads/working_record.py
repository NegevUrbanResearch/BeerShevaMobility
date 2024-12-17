import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import logging
from config import OUTPUT_DIR
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
import time
import io
from shapely.geometry import Point

try:
    import cv2
except ImportError:
    print("Please install OpenCV with: pip install opencv-python")
    raise

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Update the load_trip_data function to include POI information
def load_trip_data():
    """Load and process trip data with POI-based coloring"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    logger.info(f"Loading trip data from: {file_path}")
    
    # Define POIs and their colors
    POI_COLORS = {
        'BGU': [0, 255, 90],        # Bright green
        'Gav Yam': [0, 191, 255],   # Deep sky blue
        'Soroka Hospital': [170, 0, 255]  # Deep purple
    }
    
    POI_RADIUS = 0.0018  # about 200 meters in decimal degrees
    
    # Load POI polygons
    attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
    poi_polygons = attractions[attractions['ID'].isin([11, 12, 7])]
    
    # POI ID mapping
    POI_ID_MAP = {
        7: 'BGU',
        12: 'Gav Yam',
        11: 'Soroka Hospital'
    }
    
    trips_gdf = gpd.read_file(file_path)
    raw_trip_count = trips_gdf['num_trips'].sum()
    
    # Animation parameters
    fps = 30
    minutes_per_hour = 60
    hours_per_day = 24
    frames_per_hour = fps * minutes_per_hour
    animation_duration = frames_per_hour * hours_per_day
    
    routes_data = []
    processed_trips = 0
    
    for idx, row in trips_gdf.iterrows():
        try:
            coords = list(row.geometry.coords)
            num_trips = int(row['num_trips'])
            
            if num_trips <= 0 or len(coords) < 2:
                continue
            
            # Determine POI for this route
            dest_point = Point(coords[-1])
            poi_name = None
            for _, poi_polygon in poi_polygons.iterrows():
                if dest_point.distance(poi_polygon.geometry) < POI_RADIUS:
                    poi_name = POI_ID_MAP[int(poi_polygon['ID'])]
                    break
            
            path = [[float(x), float(y)] for x, y in coords]
            processed_trips += num_trips
            
            routes_data.append({
                'path': path,
                'startTime': 0,
                'numTrips': num_trips,
                'duration': len(coords) * 2,
                'poi': poi_name
            })
            
        except Exception as e:
            logger.error(f"Error processing route {idx}: {str(e)}")
            continue
    
    return routes_data, animation_duration, POI_COLORS

def create_deck_html(routes_data, animation_duration, poi_colors):
    """Create HTML with transparent background and POI-colored trips"""
    routes_json = json.dumps(routes_data)
    poi_colors_json = json.dumps(poi_colors)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
        <style>
            body, html {{ 
                margin: 0; 
                padding: 0;
                background-image: 
                    linear-gradient(45deg, #808080 25%, transparent 25%),
                    linear-gradient(-45deg, #808080 25%, transparent 25%),
                    linear-gradient(45deg, transparent 75%, #808080 75%),
                    linear-gradient(-45deg, transparent 75%, #808080 75%);
                background-size: 20px 20px;
                background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
                background-color: #666666;
            }}
            #container {{ 
                width: 100vw; 
                height: 100vh; 
                position: relative;
            }}
            canvas {{
                background: transparent !important;
            }}
            #loading {{
                position: fixed;
                top: 10px;
                left: 10px;
                background: rgba(0,0,0,0.7);
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-family: monospace;
            }}
            .progress-bar {{
                position: fixed;
                bottom: 0;
                left: 0;
                width: 100%;
                height: 4px;
                background: #333;
            }}
            .progress {{
                height: 100%;
                width: 0;
                background: #00ff00;
                transition: width 0.3s ease;
            }}
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div id="loading">Initializing...</div>
        <div class="progress-bar"><div class="progress"></div></div>
        <script>
            const ANIMATION_DURATION = {animation_duration};
            const ROUTES_DATA = {routes_json};
            const POI_COLORS = {poi_colors_json};
            const HOURS_PER_DAY = 24;
            const START_HOUR = 6;
            let isInitialized = false;
            
            const ambientLight = new deck.AmbientLight({{
                color: [255, 255, 255],
                intensity: 1.0
            }});

            const pointLight = new deck.PointLight({{
                color: [255, 255, 255],
                intensity: 2.0,
                position: [34.8, 31.25, 8000]
            }});

            const lightingEffect = new deck.LightingEffect({{ambientLight, pointLight}});
            
            const INITIAL_VIEW_STATE = {{
                longitude: 34.8113,
                latitude: 31.2627,
                zoom: 13,
                pitch: 45,
                bearing: 0
            }};
            
            const deckgl = new deck.DeckGL({{
                container: 'container',
                initialViewState: INITIAL_VIEW_STATE,
                controller: false,
                effects: [lightingEffect],
                parameters: {{
                    clearColor: [0, 0, 0, 0],
                    blend: true,
                    blendFunc: [
                        WebGLRenderingContext.SRC_ALPHA,
                        WebGLRenderingContext.ONE_MINUS_SRC_ALPHA
                    ],
                    depthTest: true,
                    depthFunc: WebGLRenderingContext.LEQUAL
                }},
                glOptions: {{
                    webgl2: true,
                    webgl1: true,
                    preserveDrawingBuffer: true
                }},
                onWebGLInitialized: (gl) => {{
                    console.log('WebGL initialized');
                    gl.enable(gl.BLEND);
                    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
                }},
                onLoad: () => {{
                    console.log('deck.gl loaded');
                    isInitialized = true;
                    document.getElementById('loading').style.display = 'none';
                    window.deckglLoaded = true;
                }}
            }});
            
            let frame = 0;
            let lastLoggedHour = -1;
            let trailLength = 5;
            
            function getPathColor(path, poi) {{
                if (poi && POI_COLORS[poi]) {{
                    return POI_COLORS[poi];
                }}
                return [253, 128, 93];
            }}
            
            function animate() {{
                if (!isInitialized) {{
                    requestAnimationFrame(animate);
                    return;
                }}
                
                const hour = Math.floor((frame / ANIMATION_DURATION) * HOURS_PER_DAY + START_HOUR) % 24;
                
                if (hour !== lastLoggedHour) {{
                    console.log(`Hour ${{hour}}:00`);
                    lastLoggedHour = hour;
                }}
                
                const trips = new deck.TripsLayer({{
                    id: 'trips',
                    data: ROUTES_DATA,
                    getPath: d => d.path,
                    getTimestamps: d => d.path.map((_, i) => d.startTime + (i * d.duration / d.path.length)),
                    getColor: d => getPathColor(d.path, d.poi),
                    getWidth: d => Math.sqrt(d.numTrips || 1),
                    opacity: 1.0,
                    widthMinPixels: 2,
                    widthMaxPixels: 10,
                    jointRounded: true,
                    capRounded: true,
                    trailLength,
                    currentTime: frame,
                    shadowEnabled: false,
                }});
                
                deckgl.setProps({{
                    layers: [trips]
                }});
                
                frame = (frame + 1) % ANIMATION_DURATION;
                requestAnimationFrame(animate);
            }}
            
            setTimeout(() => {{
                animate();
                window.animationStarted = true;
            }}, 2000);
        </script>
    </body>
    </html>
    """
def save_frames_as_images(html_path, output_dir, duration_seconds=60):
    """Save individual frames as PNG images with robust progress tracking"""
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    from selenium.webdriver.common.by import By
    
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=1920')
    firefox_options.add_argument('--height=1080')
    # Enable WebGL
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info("Starting Firefox WebDriver...")
    driver = webdriver.Firefox(options=firefox_options)
    
    try:
        logger.info(f"Loading page: file://{html_path}")
        driver.get(f'file://{html_path}')
        
        # Wait for initialization with improved checks
        logger.info("Waiting for animation to initialize...")
        max_wait_time = 60
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                # Check for canvas
                deck_canvas = driver.find_element(By.CSS_SELECTOR, 'canvas')
                if not deck_canvas:
                    logger.info("Canvas element not found yet...")
                    time.sleep(1)
                    continue
                
                # Check WebGL context
                webgl_status = driver.execute_script("""
                    const canvas = document.querySelector('canvas');
                    if (!canvas) return 'No canvas found';
                    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                    if (!gl) return 'No WebGL context';
                    return 'WebGL available';
                """)
                logger.info(f"WebGL status: {webgl_status}")
                
                initialized = driver.execute_script("""
                    if (typeof deck === 'undefined') {
                        return 'deck.gl not loaded';
                    }
                    if (!window.deckglLoaded) {
                        return 'deck.gl not initialized';
                    }
                    if (!window.animationStarted) {
                        return 'animation not started';
                    }
                    return true;
                """)
                
                logger.info(f"Initialization check: {initialized}")
                
                if initialized is True:
                    break
                    
            except Exception as e:
                logger.warning(f"Initialization check error: {str(e)}")
                
            time.sleep(1)
        
        if time.time() - start_time >= max_wait_time:
            logger.error("Initialization timeout - Debug info:")
            logger.error(f"Page title: {driver.title}")
            logger.error(f"Page source preview: {driver.page_source[:500]}...")
            raise TimeoutError("Animation failed to initialize within timeout period")
        
        logger.info("Animation initialized successfully!")
        frames_to_capture = duration_seconds * 30
        
        # Clear existing frames
        for file in os.listdir(output_dir):
            if file.startswith('frame_'):
                os.remove(os.path.join(output_dir, file))
        
        for i in range(frames_to_capture):
            current_frame = i + 1
            progress = (current_frame * 100) / frames_to_capture
            
            # Take screenshot
            screenshot = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            
            # Convert to RGBA if needed
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Save frame
            frame_path = os.path.join(output_dir, f'frame_{i:05d}.png')
            image.save(frame_path, 'PNG')
            
            # Print progress
            if current_frame % 30 == 0 or current_frame == frames_to_capture:
                logger.info(f"Progress: {progress:.1f}% ({current_frame}/{frames_to_capture} frames)")
            
            # Update progress bar in browser
            driver.execute_script(f"document.querySelector('.progress').style.width = '{progress}%'")
            
            time.sleep(1/30)  # Maintain 30 FPS
        
        logger.info("Frame capture completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during frame capture: {str(e)}")
        raise
    
    finally:
        driver.quit()

def create_video_from_frames(frame_dir, output_path, fps=30):
    """Create video from frames with improved codec handling"""
    frame_files = sorted([f for f in os.listdir(frame_dir) if f.startswith('frame_')])
    if not frame_files:
        raise ValueError("No frames found in directory")
    
    logger.info(f"Found {len(frame_files)} frames to process")
    first_frame = cv2.imread(os.path.join(frame_dir, frame_files[0]), cv2.IMREAD_UNCHANGED)
    height, width = first_frame.shape[:2]
    
    # Try different codecs in order of preference
    codecs = [
        ('avc1', '.mp4'),
        ('mp4v', '.mp4'),
        ('vp09', '.webm')
    ]
    
    for codec, ext in codecs:
        try:
            output_file = output_path.rsplit('.', 1)[0] + ext
            fourcc = cv2.VideoWriter_fourcc(*codec)
            out = cv2.VideoWriter(output_file, fourcc, fps, (width, height), True)
            
            if not out.isOpened():
                logger.warning(f"Failed to initialize VideoWriter with codec {codec}")
                continue
            
            logger.info(f"Creating video with codec {codec}")
            total_frames = len(frame_files)
            
            for idx, frame_file in enumerate(frame_files, 1):
                if idx % 30 == 0:
                    progress = (idx * 100) / total_frames
                    logger.info(f"Video encoding progress: {progress:.1f}% ({idx}/{total_frames} frames)")
                
                frame_path = os.path.join(frame_dir, frame_file)
                frame = cv2.imread(frame_path, cv2.IMREAD_UNCHANGED)
                
                if frame.shape[2] == 4:  # RGBA
                    bgr = frame[:, :, :3]
                    alpha = frame[:, :, 3]
                    white_bg = np.ones_like(bgr) * 255
                    alpha_3d = np.stack([alpha, alpha, alpha], axis=2) / 255.0
                    blended = (bgr * alpha_3d + white_bg * (1 - alpha_3d)).astype(np.uint8)
                    out.write(blended)
                else:
                    out.write(frame)
            
            out.release()
            logger.info(f"Video successfully created at: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Failed with codec {codec}: {str(e)}")
            continue
    
    raise RuntimeError("Failed to create video with any available codec")
def main():
    # Load trip data with POI colors
    routes_data, animation_duration, poi_colors = load_trip_data()
    
    # Create HTML file
    html_path = os.path.join(OUTPUT_DIR, "projection_animation.html")
    html_content = create_deck_html(routes_data, animation_duration, poi_colors)
    
    with open(html_path, "w") as f:
        f.write(html_content)
    
    print(f"\nHTML file created at: {html_path}")
    
    # Create frames directory
    frames_dir = os.path.join(OUTPUT_DIR, "animation_frames")
    
    # Save frames as images
    save_frames_as_images(os.path.abspath(html_path), frames_dir)
    
    # Create video from frames
    output_path = os.path.join(OUTPUT_DIR, "projection_animation.mp4")
    create_video_from_frames(frames_dir, output_path)
    
    logger.info(f"Video saved to: {output_path}")

if __name__ == "__main__":
    main()