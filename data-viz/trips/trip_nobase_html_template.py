import re

HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'>
        <title>Trip Animation</title>
        <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
        <script src='https://unpkg.com/popmotion@11.0.0/dist/popmotion.js'></script>
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
        </style>
    </head>
    <body>
        <div id="container"></div>
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
        <script>
            document.addEventListener('DOMContentLoaded', function() {
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
                
                // Animation state
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

                // Pre-calculate hourly trip totals
                let hourlyTripTotals = Array(HOURS_PER_DAY).fill(null).map(() => ({
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
                
                // Initial view setup
                const INITIAL_VIEW_STATE = {
                    longitude: 34.8113,
                    latitude: 31.2627,
                    zoom: 13,
                    pitch: 45,
                    bearing: 0
                };
                
                const deckgl = new deck.DeckGL({
                    container: 'container',
                    initialViewState: INITIAL_VIEW_STATE,
                    controller: true,
                    effects: [lightingEffect],
                    style: {background: 'white'},
                    parameters: {
                        clearColor: [1, 1, 1, 1]
                    }
                });
                
                function formatTimeString(frame) {
                    const hoursElapsed = frame / FRAMES_PER_HOUR;
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
                    // Calculate current hour
                    const currentHour = Math.floor(currentFrame / FRAMES_PER_HOUR);
                    
                    // Reset counters if we've gone back to the start
                    if (currentHour < lastHour) {
                        console.log('Day reset detected - Resetting counters');
                        cumulativeCounts = {
                            'BGU': 0,
                            'Gav Yam': 0,
                            'Soroka Hospital': 0
                        };
                    } else if (currentHour > lastHour) {
                        // Add hourly totals to cumulative counts
                        Object.keys(cumulativeCounts).forEach(poi => {
                            if (lastHour >= 0 && lastHour < hourlyTripTotals.length) {
                                cumulativeCounts[poi] += hourlyTripTotals[lastHour][poi];
                                console.log(`Hour ${lastHour + START_HOUR}: Added ${hourlyTripTotals[lastHour][poi]} trips to ${poi}`);
                            }
                        });
                    }
                    lastHour = currentHour;

                    // Process active trips
                    return TRIPS_DATA.map(route => {
                        const elapsedTime = (currentFrame - route.startTime) % ANIMATION_DURATION;
                        if (elapsedTime < 0 || elapsedTime > route.duration) {
                            return null;
                        }
                        
                        const timestamps = route.path.map((_, index) => 
                            route.startTime + (index / (route.path.length - 1)) * route.duration
                        );
                        
                        return {
                            path: route.path,
                            timestamps,
                            numTrips: route.numTrips,
                            poi: route.poi
                        };
                    }).filter(Boolean);
                }

                function updateCounters() {
                    // Update counter displays
                    Object.entries(cumulativeCounts).forEach(([poi, count]) => {
                        const id = poi.toLowerCase()
                                    .replace(/\\s+/g, '-')
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
                            
                            // Update time displays
                            document.querySelector('.time-display').textContent = currentTime;
                            document.getElementById('current-time').textContent = currentTime;
                            
                            // Process active trips with caching
                            const activeTrips = (currentFrame % 30 === 0 || !cachedActiveTrips) 
                                ? processTrips(currentFrame) 
                                : cachedActiveTrips;
                            cachedActiveTrips = activeTrips;
                            
                            // Update counters
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

                // Initialize animation
                animate();
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