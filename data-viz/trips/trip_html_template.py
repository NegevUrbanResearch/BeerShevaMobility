import re

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <title>Trip Animation</title>
    <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
    <script src='https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js'></script>
    <script src='https://unpkg.com/popmotion@11.0.0/dist/popmotion.js'></script>
    <link href='https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css' rel='stylesheet' />
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
        .debug-panel {
            position: absolute;
            bottom: 40px;
            left: 20px;
            background: rgba(0, 0, 0, 0.8);
            padding: 12px;
            border-radius: 5px;
            color: #FFFFFF;
            font-family: monospace;
            font-size: 12px;
            max-height: 200px;
            overflow-y: auto;
            z-index: 1000;
            width: 400px;
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
            left: 50%%;
            transform: translateX(-50%%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 12px 24px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 24px;
            z-index: 1000;
        }
        .trip-counters {
            margin-top: 10px;
            font-family: monospace;
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
    </style>
</head>
<body>
    <div id="container"></div>
    <div class="debug-panel" id="debug-panel"></div>
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
        <h3 style="margin: 0 0 10px 0;">Methodology</h3>
        <p style="margin: 0; font-size: 0.9em;">
            Represents daily trips (6:00-22:00) across Beer Sheva's road network using temporal distributions.<br>
            Total Daily Trips: %(total_trips)d<br>
            Current simulation time: <span id="current-time">06:00</span><br>
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
        </p>
    </div>
    <div class="map-attribution">
        © <a href="https://www.mapbox.com/" target="_blank">Mapbox</a>
        © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>
    </div>
    <script>
    //------------------------------------------------------------------------------
    // UTILITY FUNCTIONS
    //------------------------------------------------------------------------------
    const debugLog = {
        log: function(message, type = 'info') {
            const debugPanel = document.getElementById('debug-panel');
            if (!debugPanel) {
                console[type](message);
                return;
            }
            const timestamp = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.style.color = type === 'error' ? '#ff6b6b' : 
                            type === 'warning' ? '#ffd93d' : '#4cd137';
            entry.textContent = `[${timestamp}] ${message}`;
            debugPanel.appendChild(entry);
            debugPanel.scrollTop = debugPanel.scrollHeight;
            console[type](message);
        },
        error: function(message) { this.log(message, 'error'); },
        warn: function(message) { this.log(message, 'warning'); }
    };

    //------------------------------------------------------------------------------
    // MAPBOX INITIALIZATION
    //------------------------------------------------------------------------------
    // Set Mapbox token globally before any map operations
    mapboxgl.accessToken = 'pk.eyJ1Ijoibm9hbWpnYWwiLCJhIjoiY20zbHJ5MzRvMHBxZTJrcW9uZ21pMzMydiJ9.B_aBdP5jxu9nwTm3CoNhlg';

    document.addEventListener('DOMContentLoaded', async function() {
        try {
            debugLog.log('Initializing application...');
            debugLog.log(`Mapbox GL JS version: ${mapboxgl.version}`);
            debugLog.log(`Using token: ${mapboxgl.accessToken.substring(0, 10)}...`);
            
            //------------------------------------------------------------------------------
            // DATA INITIALIZATION
            //------------------------------------------------------------------------------
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
            const MAP_STYLE = 'mapbox://styles/mapbox/dark-v11';  // Explicitly set style
            const START_HOUR = %(start_hour)d;
            const END_HOUR = %(end_hour)d;

            // Verify data loading
            if (!TRIPS_DATA || !TRIPS_DATA.length) {
                debugLog.error('No trip data available!');
            } else {
                debugLog.log(`Loaded ${TRIPS_DATA.length} trips`);
            }
            
            if (!BUILDINGS_DATA || !BUILDINGS_DATA.length) {
                debugLog.error('No building data available!');
            } else {
                debugLog.log(`Loaded ${BUILDINGS_DATA.length} buildings`);
            }

            //------------------------------------------------------------------------------
            // MAP CONFIGURATION
            //------------------------------------------------------------------------------
            // Initial view settings
            const INITIAL_VIEW_STATE = {
                longitude: 34.8113,
                latitude: 31.2627,
                zoom: 13,
                pitch: 45,
                bearing: 0
            };

            // Create base map
            debugLog.log('Creating map instance...');
            const map = new mapboxgl.Map({
                container: 'container',
                style: MAP_STYLE,
                ...INITIAL_VIEW_STATE,
                interactive: true,
                attributionControl: false,
                maxZoom: 20,
                antialias: true
            });

            // Map event handlers
            map.on('load', () => {
                debugLog.log('Map loaded successfully');
                checkMapResources();
            });

            map.on('error', (e) => {
                debugLog.error(`Map error: ${e.error.message}`);
                if (e.error.message.includes('access token')) {
                    debugLog.error(`Current token: ${mapboxgl.accessToken.substring(0, 10)}...`);
                    debugLog.error('Token configuration failed');
                }
            });

            map.on('sourcedata', (e) => {
                if (e.isSourceLoaded && e.sourceId === 'composite') {
                    debugLog.log('Composite source loaded');
                }
            });

            //------------------------------------------------------------------------------
            // LIGHTING AND VISUAL EFFECTS
            //------------------------------------------------------------------------------
            // POI Colors
            const POI_COLORS = {
                'BGU': [0, 255, 90],
                'Gav Yam': [0, 191, 255],
                'Soroka Hospital': [170, 0, 255]
            };

            // Lighting setup
            const ambientLight = new deck.AmbientLight({
                color: [255, 255, 255],
                intensity: 1.2
            });

            const pointLight = new deck.PointLight({
                color: [255, 255, 255],
                intensity: 2.5,
                position: [34.8, 31.25, 8000]
            });

            const lightingEffect = new deck.LightingEffect({ambientLight, pointLight});

            //------------------------------------------------------------------------------
            // DECK.GL INITIALIZATION
            //------------------------------------------------------------------------------
            const deckgl = new deck.DeckGL({
                container: 'container',
                mapboxgl: map,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true,
                effects: [lightingEffect],
                onWebGLInitialized: (gl) => {
                    debugLog.log('WebGL initialized');
                    gl.enable(gl.DEPTH_TEST);
                    gl.depthFunc(gl.LEQUAL);
                }
            });

            //------------------------------------------------------------------------------
            // BUILDING LAYER FUNCTIONS
            //------------------------------------------------------------------------------
            function checkMapResources() {
                if (!map.getSource('composite')) {
                    debugLog.warn('Composite source not found - retrying in 1s...');
                    setTimeout(checkMapResources, 1000);
                    return;
                }

                if (!map.isStyleLoaded()) {
                    debugLog.warn('Style not fully loaded - retrying in 100ms...');
                    setTimeout(checkMapResources, 100);
                    return;
                }

                try {
                    addBuildingLayer();
                    debugLog.log('3D buildings layer added successfully');
                } catch (err) {
                    debugLog.error(`Failed to add building layer: ${err.message}`);
                }
            }

            function addBuildingLayer() {
                if (map.getLayer('mapbox-3d-buildings')) {
                    map.removeLayer('mapbox-3d-buildings');
                }

                map.addLayer({
                    'id': 'mapbox-3d-buildings',
                    'source': 'composite',
                    'source-layer': 'building',
                    'filter': ['==', 'extrude', 'true'],
                    'type': 'fill-extrusion',
                    'minzoom': 12,
                    'paint': {
                        'fill-extrusion-color': '#aaaaaa',
                        'fill-extrusion-height': [
                            'interpolate',
                            ['linear'],
                            ['zoom'],
                            15,
                            0,
                            15.05,
                            ['get', 'height']
                        ],
                        'fill-extrusion-base': ['get', 'min_height'],
                        'fill-extrusion-opacity': 0.4
                    }
                }, 'road-label');
            }

            //------------------------------------------------------------------------------
            // ANIMATION STATE AND CONTROLS
            //------------------------------------------------------------------------------
            let trailLength = 5;
            let animationSpeed = 2.5;
            let animation;
            let cachedActiveTrips = null;
            let lastHour = -1;

            // Counter state
            let cumulativeCounts = {
                'BGU': 0,
                'Gav Yam': 0,
                'Soroka Hospital': 0
            };

            function formatTimeString(frame) {
                const hoursElapsed = frame / (ANIMATION_DURATION / (END_HOUR - START_HOUR));
                const currentHour = Math.floor(START_HOUR + hoursElapsed);
                const minutes = Math.floor((hoursElapsed % 1) * 60);
                return `${currentHour.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            }

            function getPathColor(path, poi) {
                if (poi && POI_COLORS[poi]) {
                    return POI_COLORS[poi];
                }
                return [253, 128, 93];
            }

            function processTrips(currentFrame) {
                const currentHour = Math.floor(currentFrame / (ANIMATION_DURATION / (END_HOUR - START_HOUR)));
                
                if (currentHour < lastHour) {
                    debugLog.log('Day reset - Resetting counters');
                    cumulativeCounts = {
                        'BGU': 0,
                        'Gav Yam': 0,
                        'Soroka Hospital': 0
                    };
                }
                
                lastHour = currentHour;

                return TRIPS_DATA.map(route => {
                    const elapsedTime = (currentFrame - route.startTime) % ANIMATION_DURATION;
                    if (elapsedTime < 0 || elapsedTime > route.duration) {
                        return null;
                    }
                    
                    return {
                        path: route.path,
                        timestamps: route.path.map((_, index) => 
                            route.startTime + (index / (route.path.length - 1)) * route.duration
                        ),
                        numTrips: route.numTrips,
                        poi: route.poi
                    };
                }).filter(Boolean);
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

            //------------------------------------------------------------------------------
            // ANIMATION FUNCTION
            //------------------------------------------------------------------------------
            function animate() {
                debugLog.log('Starting animation');
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
                        
                        const activeTrips = (currentFrame % 30 === 0 || !cachedActiveTrips) 
                            ? processTrips(currentFrame) 
                            : cachedActiveTrips;
                        cachedActiveTrips = activeTrips;
                        
                        updateCounters();
                        
                        const layers = [
                            new deck.PolygonLayer({
                                id: 'poi-buildings',
                                data: BUILDINGS_DATA,
                                extruded: true,
                                wireframe: true,
                                opacity: 0.9,
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
                                jointRounded: true,
                                capRounded: true,
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
                                blend: false,
                                depthTest: true,
                                depthWrite: true
                            }
                        });
                    }
                });
            }

            //------------------------------------------------------------------------------
            // EVENT LISTENERS
            //------------------------------------------------------------------------------
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

            // Start animation
            animate();

        } catch (err) {
            debugLog.error(`Fatal error initializing map: ${err.message}`);
            console.error(err);
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