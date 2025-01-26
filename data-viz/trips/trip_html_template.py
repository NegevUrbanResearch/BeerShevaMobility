import re

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <title>Car Trip Animation</title>
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
            z-index: 1000;
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
            z-index: 1000;
        }
        .time-display {
            position: absolute;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 12px 24px;
            border-radius: 5px;
            font-family: Arial;
            font-size: 24px;
            z-index: 1000;
        }
        .trip-counters {
            margin-top: 15px;
            font-family: Arial;
            font-size: 14px;
        }
        .counter-row {
            margin: 5px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .map-attribution {
            position: absolute;
            bottom: 0;
            right: 0;
            background: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 5px;
            font-size: 12px;
            z-index: 1000;
        }
        .loading-screen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.9);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            color: white;
            font-family: Arial;
            z-index: 2000;
        }
        .loading-spinner {
            width: 50px;
            height: 50px;
            border: 5px solid #f3f3f3;
            border-top: 5px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .loading-progress {
            margin-top: 10px;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="loading-screen" class="loading-screen">
        <div class="loading-spinner"></div>
        <h2>Preparing Visualization</h2>
        <div class="loading-progress">Initializing...</div>
    </div>
    <div class="control-panel">
        <div>
            <label>Trail Length: <span id="trail-value">5</span></label>
            <input type="range" min="1" max="20" value="5" id="trail-length" style="width: 200px">
        </div>
        <div>
            <label>Animation Speed: <span id="speed-value">2.5</span></label>
            <input type="range" min="0.5" max="5" step="0.5" value="2.5" id="animation-speed" style="width: 200px">
        </div>
    </div>
    <div class="time-display">06:00</div>
    <div class="methodology-container">
        <h3 style="margin: 0 0 10px 0;">Legend</h3>
        <p style="margin: 0; font-size: 14px;">
            %(total_trips)d car trips simulated to BGU, Gav Yam, and Soroka Hospital.<br><br>
            Current simulation time: <span id="current-time">06:00</span>
        </p>
        <div class="trip-counters">
            Cumulative Trips (Updated Hourly):<br>
            <div class="counter-row">
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 255, 90); vertical-align: middle;"></span>
                BGU: <span id="bgu-counter">0</span>
            </div>
            <div class="counter-row">
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 191, 255); vertical-align: middle;"></span>
                Gav Yam: <span id="gav-yam-counter">0</span>
            </div>
            <div class="counter-row">
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(170, 0, 255); vertical-align: middle;"></span>
                Soroka: <span id="soroka-hospital-counter">0</span>
            </div>
        </div>
    </div>
    <div class="map-attribution">
        © <a href="https://www.maptiler.com/copyright/" target="_blank">MapTiler</a>
        © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', async function() {
            const loadingScreen = document.getElementById('loading-screen');
            const loadingProgress = loadingScreen.querySelector('.loading-progress');

            // Constants
            const TRIPS_DATA = %(trips_data)s;
            const BUILDINGS_DATA = %(buildings_data)s;
            const POI_BORDERS = %(poi_borders)s;
            const POI_FILLS = %(poi_fills)s;
            const POI_RADIUS = %(poi_radius)f;
            const BGU_INFO = %(bgu_info)s;
            const GAV_YAM_INFO = %(gav_yam_info)s;
            const SOROKA_INFO = %(soroka_info)s;
            const ANIMATION_DURATION = %(animation_duration)d;
            const LOOP_LENGTH = %(loopLength)d;
            
            // POI Colors
            const POI_COLORS = {
                'BGU': [0, 255, 90],
                'Gav Yam': [0, 191, 255],
                'Soroka Hospital': [170, 0, 255]
            };
            
            // Animation constants
            const START_HOUR = 6;
            const END_HOUR = 22;
            const HOURS_PER_DAY = END_HOUR - START_HOUR;
            const FRAMES_PER_HOUR = ANIMATION_DURATION / HOURS_PER_DAY;

            // Precomputed state
            let precomputedTrips = new Map();
            let hourlyTripTotals = [];
            
            // Animation state
            let trailLength = 5;
            let animationSpeed = 2.5;
            let animation;
            let lastHour = -1;
            let cumulativeCounts = {
                'BGU': 0,
                'Gav Yam': 0,
                'Soroka Hospital': 0
            };

            // Lighting setup
            const ambientLight = new deck.AmbientLight({
                color: [255, 255, 255],
                intensity: 1.0
            });

            const pointLight = new deck.PointLight({
                color: [255, 255, 255],
                intensity: 2.0,
                position: [34.8, 31.25, 8000]
            });

            const lightingEffect = new deck.LightingEffect({ambientLight, pointLight});

            // Initial view setup
            const INITIAL_VIEW_STATE = {
                longitude: 34.8113,
                latitude: 31.2627,
                zoom: 13,
                pitch: 45,
                bearing: 0
            };

            const MAP_STYLE = '%(map_style)s';

            // Precompute data structures
            loadingProgress.textContent = 'Preprocessing trip data...';
            await new Promise(resolve => setTimeout(resolve, 0)); // Allow UI to update

            // Precompute hourly trip totals
            hourlyTripTotals = Array(HOURS_PER_DAY).fill(null).map(() => ({
                'BGU': 0,
                'Gav Yam': 0,
                'Soroka Hospital': 0
            }));

            TRIPS_DATA.forEach(trip => {
                if (trip.poi) {
                    const hour = Math.floor(trip.startTime / FRAMES_PER_HOUR);
                    if (hour >= 0 && hour < HOURS_PER_DAY) {
                        hourlyTripTotals[hour][trip.poi] += trip.numTrips;
                    }
                }
            });

            // Precompute trip timestamps
            TRIPS_DATA.forEach(route => {
                const timestamps = route.path.map((_, index) => 
                    route.startTime + (index / (route.path.length - 1)) * route.duration
                );
                
                precomputedTrips.set(route, {
                    timestamps,
                    numTrips: route.numTrips,
                    poi: route.poi,
                    path: route.path,
                    startTime: route.startTime,
                    duration: route.duration
                });
            });

            loadingProgress.textContent = 'Initializing map...';
            await new Promise(resolve => setTimeout(resolve, 0));

            const deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: MAP_STYLE,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true,
                effects: [lightingEffect]
            });

            function formatTimeString(frame) {
                const hoursElapsed = frame / FRAMES_PER_HOUR;
                const currentHour = Math.floor(START_HOUR + hoursElapsed);
                const minutes = Math.floor((hoursElapsed % 1) * 60);
                return `${currentHour.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            }

            function getPathColor(path, poi) {
                return POI_COLORS[poi] || [253, 128, 93];
            }

            function processTrips(currentFrame) {
                const currentHour = Math.floor(currentFrame / FRAMES_PER_HOUR);
                
                if (currentHour < lastHour) {
                    cumulativeCounts = {
                        'BGU': 0,
                        'Gav Yam': 0,
                        'Soroka Hospital': 0
                    };
                } else if (currentHour > lastHour) {
                    Object.keys(cumulativeCounts).forEach(poi => {
                        if (lastHour >= 0 && lastHour < hourlyTripTotals.length) {
                            cumulativeCounts[poi] += hourlyTripTotals[lastHour][poi];
                        }
                    });
                }
                lastHour = currentHour;

                return Array.from(precomputedTrips.values()).filter(trip => {
                    const elapsedTime = (currentFrame - trip.startTime) % ANIMATION_DURATION;
                    return elapsedTime >= 0 && elapsedTime <= trip.duration;
                });
            }

            function updateCounters() {
                Object.entries(cumulativeCounts).forEach(([poi, count]) => {
                    const id = poi.toLowerCase()
                                .replace(/\s+/g, '-')
                                .replace(/[^a-z0-9-]/g, '')
                                + '-counter';
                    const element = document.getElementById(id);
                    if (element) {
                        element.textContent = Math.round(count).toLocaleString();
                    }
                });
            }

            function animate() {
                animation = popmotion.animate({
                    from: 0,
                    to: LOOP_LENGTH,
                    duration: (LOOP_LENGTH * 30) / animationSpeed,
                    repeat: Infinity,
                    onUpdate: time => {
                        const currentFrame = Math.floor(time % ANIMATION_DURATION);
                        const currentTime = formatTimeString(currentFrame);
                        
                        document.querySelector('.time-display').textContent = currentTime;
                        document.getElementById('current-time').textContent = currentTime;
                        
                        const activeTrips = processTrips(currentFrame);
                        updateCounters();
                        
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
                                data: activeTrips,
                                getPath: d => d.path,
                                getTimestamps: d => d.timestamps,
                                getColor: d => getPathColor(d.path, d.poi),
                                opacity: 0.8,
                                widthMinPixels: 2,
                                rounded: true,
                                trailLength,
                                currentTime: currentFrame,
                                getWidth: d => Math.sqrt(d.numTrips || 1)
                            }),
                            new deck.PolygonLayer({
                                id: 'poi-borders',
                                data: POI_BORDERS,
                                getPolygon: d => d.polygon,
                                getFillColor: [0, 0, 0, 0],
                                getLineColor: d => d.color,
                                getLineWidth: 3,
                                lineWidthUnits: 'pixels',
                                wireframe: true,
                                filled: false,
                                opacity: 1
                            })
                        ];

                        deckgl.setProps({
                            layers,
                            parameters: {
                                blend: false
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

            // Wait a bit to ensure everything is ready
            await new Promise(resolve => setTimeout(resolve, 500));
            
            // Remove loading screen and start animation
            loadingProgress.textContent = 'Starting animation...';
            await new Promise(resolve => setTimeout(resolve, 200));
            
            loadingScreen.style.opacity = '0';
            loadingScreen.style.transition = 'opacity 0.5s ease-out';
            
            setTimeout(() => {
                loadingScreen.style.display = 'none';
                // Initialize animation
                animate();
            }, 600);

            // Map style handling
            if (deckgl.props.map) {
                deckgl.props.map.on('style.load', () => {
                    // Remove country borders for dark_nolabels style
                    if (MAP_STYLE.includes('dark-v11')) {
                        deckgl.props.map.setLayoutProperty('admin-0-boundary', 'visibility', 'none');
                        deckgl.props.map.setLayoutProperty('admin-0-boundary-bg', 'visibility', 'none');
                        deckgl.props.map.setLayoutProperty('admin-1-boundary', 'visibility', 'none');
                    }
                });
            }
        });
    </script>
</body>
</html>
"""

# Fix JavaScript modulo operations
HTML_TEMPLATE = re.sub(
    r'(?<![%])%(?![(%sd])',  # Match single % not followed by formatting specifiers
    '%%',                     # Replace with %%
    HTML_TEMPLATE
)