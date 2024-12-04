import re

HTML_TEMPLATE = """
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
            .time-display {
                position: absolute;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
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
                <label>Trail Length: <span id="trail-value">2</span></label>
                <input type="range" min="1" max="20" value="2" id="trail-length" style="width: 200px">
            </div>
            <div>
                <label>Animation Speed: <span id="speed-value">6</span></label>
                <input type="range" min="0.5" max="10" step="0.5" value="6" id="animation-speed" style="width: 200px">
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
                    Cumulative Trips:<br>
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
                        Soroka: <span id="soroka-counter">0</span>
                    </div>
                </div>
            </p>
        </div>
        <script>
            // Global constants
            const GL = {
                SRC_ALPHA: 0x0302,
                ONE_MINUS_SRC_ALPHA: 0x0303,
                FUNC_ADD: 0x8006
            };
            
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
            
            // Add this after TRIPS_DATA is defined
            console.log('Trip Data Summary:', {
                totalRoutes: TRIPS_DATA.length,
                totalTrips: TRIPS_DATA.reduce((sum, route) => sum + route.num_trips, 0),
                tripsByPOI: TRIPS_DATA.reduce((acc, route) => {
                    if (route.poi) {
                        acc[route.poi] = (acc[route.poi] || 0) + route.num_trips;
                    }
                    return acc;
                }, {})
            });

            // Optional: Validate timestamps
            console.log('Timestamp Distribution:', TRIPS_DATA.reduce((acc, route) => {
                if (route.timestamps && route.timestamps[0]) {
                    acc.minTime = Math.min(acc.minTime, Math.min(...route.timestamps[0]));
                    acc.maxTime = Math.max(acc.maxTime, Math.max(...route.timestamps[0]));
                    acc.totalTimestamps += route.timestamps[0].length;
                }
                return acc;
            }, { minTime: Infinity, maxTime: -Infinity, totalTimestamps: 0 }));

            // Animation constants
            const HOURS_PER_DAY = 17;
            const START_HOUR = 6;
            const END_HOUR = 22;
            const FRAMES_PER_HOUR = ANIMATION_DURATION / HOURS_PER_DAY;
            const OVERLAY_OPACITY = 0.5;
            
            // Animation state
            let trailLength = 2;
            let animationSpeed = 6;
            let animation;
            let cumulativeTrips = {
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
                pitch: 60,
                bearing: 0
            };
            
            const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json';
            
            // Initialize deck.gl
            const deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: MAP_STYLE,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true,
                effects: [lightingEffect],
                parameters: {
                    clearColor: [0, 0, 0, 1]
                }
            });
            
            // Utility functions
            function formatTimeString(frame) {
                const hoursElapsed = frame / FRAMES_PER_HOUR;
                const currentHour = Math.floor(START_HOUR + hoursElapsed);
                const minutes = Math.floor((hoursElapsed % 1) * 60);
                return `${currentHour.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            }
            
            function getPathColor(path) {
                const destination = path[path.length - 1];
                const [destLon, destLat] = destination;
                
                const distToBGU = Math.hypot(destLon - BGU_INFO.lon, destLat - BGU_INFO.lat);
                const distToGavYam = Math.hypot(destLon - GAV_YAM_INFO.lon, destLat - GAV_YAM_INFO.lat);
                const distToSoroka = Math.hypot(destLon - SOROKA_INFO.lon, destLat - SOROKA_INFO.lat);
                
                if (distToBGU < POI_RADIUS) return [0, 255, 90];
                if (distToGavYam < POI_RADIUS) return [0, 191, 255];
                if (distToSoroka < POI_RADIUS) return [170, 0, 255];
                
                return [253, 128, 93];
            }
                
            function animate() {
                // Persistent trip counters
                let poiTripCounts = {
                    'BGU': 0,
                    'Gav Yam': 0,
                    'Soroka Hospital': 0
                };

                // Calculate hourly trip distributions directly from TRIPS_DATA
                const hourlyDistribution = {};
                for (let hour = START_HOUR; hour < END_HOUR; hour++) {
                    hourlyDistribution[hour] = {
                        'BGU': 0,
                        'Gav Yam': 0,
                        'Soroka Hospital': 0
                    };
                }

                // Count trips using the pre-calculated timestamps
                TRIPS_DATA.forEach(route => {
                    if (!route.poi) return;
                    
                    // Look at first point's timestamps (starting points)
                    route.timestamps[0].forEach(timestamp => {
                        const hour = Math.floor(timestamp / FRAMES_PER_HOUR) + START_HOUR;
                        if (hour >= START_HOUR && hour < END_HOUR) {
                            // Each timestamp represents one trip instance
                            hourlyDistribution[hour][route.poi]++;
                        }
                    });
                });

                let lastProcessedTime = '';

                animation = popmotion.animate({
                    from: 0,
                    to: LOOP_LENGTH,
                    duration: (LOOP_LENGTH * 60) / animationSpeed,
                    repeat: Infinity,
                    onUpdate: time => {
                        const currentFrame = Math.floor(time % ANIMATION_DURATION);
                        const currentTime = formatTimeString(currentFrame);
                        const [currentHour, currentMinute] = currentTime.split(':').map(Number);
                        
                        // Update time displays
                        document.querySelector('.time-display').textContent = currentTime;
                        document.getElementById('current-time').textContent = currentTime;

                        // Update counters every 6 minutes of simulation time
                        if (currentMinute % 6 === 0 && currentTime !== lastProcessedTime) {
                            lastProcessedTime = currentTime;
                            
                            // Reset counts at 6:00
                            if (currentHour === 6 && currentMinute === 0) {
                                poiTripCounts = {
                                    'BGU': 0,
                                    'Gav Yam': 0,
                                    'Soroka Hospital': 0
                                };
                                console.log('Starting new day at 06:00');
                            }

                            // Add proportional trips for this time interval
                            if (hourlyDistribution[currentHour]) {
                                Object.entries(hourlyDistribution[currentHour]).forEach(([poi, hourlyTrips]) => {
                                    // Add 1/10th of the hourly trips (6-minute increment)
                                    poiTripCounts[poi] += Math.round(hourlyTrips / 10);
                                });
                            }

                            // Update counter displays
                            document.getElementById('bgu-counter').textContent = 
                                Math.round(poiTripCounts['BGU']).toLocaleString();
                            document.getElementById('gav-yam-counter').textContent = 
                                Math.round(poiTripCounts['Gav Yam']).toLocaleString();
                            document.getElementById('soroka-counter').textContent = 
                                Math.round(poiTripCounts['Soroka Hospital']).toLocaleString();
                        }


                        // Update deck.gl layers
                        deckgl.setProps({
                            layers: [
                                new deck.PolygonLayer({
                                    id: 'dark-overlay',
                                    data: [{
                                        contour: [
                                            [INITIAL_VIEW_STATE.longitude - 1, INITIAL_VIEW_STATE.latitude - 1],
                                            [INITIAL_VIEW_STATE.longitude + 1, INITIAL_VIEW_STATE.latitude - 1],
                                            [INITIAL_VIEW_STATE.longitude + 1, INITIAL_VIEW_STATE.latitude + 1],
                                            [INITIAL_VIEW_STATE.longitude - 1, INITIAL_VIEW_STATE.latitude + 1]
                                        ]
                                    }],
                                    getPolygon: d => d.contour,
                                    getFillColor: [0, 0, 0, 255 * OVERLAY_OPACITY],
                                    getLineColor: [0, 0, 0, 0],
                                    extruded: false,
                                    pickable: false,
                                    opacity: 1,
                                    zIndex: 0
                                }),
                                new deck.PolygonLayer({
                                    id: 'poi-fills',
                                    data: POI_FILLS,
                                    getPolygon: d => d.polygon,
                                    getFillColor: d => d.color,
                                    getLineColor: [0, 0, 0, 0],
                                    extruded: false,
                                    pickable: false,
                                    opacity: 0.3,
                                    zIndex: 1
                                }),
                                new deck.PolygonLayer({
                                    id: 'buildings',
                                    data: BUILDINGS_DATA,
                                    extruded: true,
                                    wireframe: true,
                                    opacity: 0.9,
                                    getPolygon: d => d.polygon,
                                    getElevation: d => d.height,
                                    getFillColor: d => d.color,
                                    getLineColor: [255, 255, 255, 30],
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
                                    getTimestamps: d => {
                                        return d.timestamps.map((pointTimes, i) => {
                                            const validTimes = pointTimes.filter(t => 
                                                t <= currentFrame && 
                                                t > currentFrame - trailLength * 4  // Shorter trail length
                                            );
                                            return validTimes.length > 0 ? Math.max(...validTimes) : null;
                                        });
                                    },
                                    getColor: d => getPathColor(d.path),
                                    opacity: 0.8,
                                    widthMinPixels: 2,
                                    jointRounded: true,
                                    capRounded: true,
                                    trailLength: trailLength * 2,  // Shorter trail for clearer visualization
                                    fadeTrail: true,
                                    currentTime: currentFrame,
                                    updateTriggers: {
                                        getTimestamps: [currentFrame, trailLength]
                                    }
                                }),
                                new deck.PolygonLayer({
                                    id: 'poi-borders',
                                    data: POI_BORDERS,
                                    getPolygon: d => d.polygon,
                                    getLineColor: d => d.color,
                                    lineWidthMinPixels: 2,
                                    extruded: false,
                                    pickable: false,
                                    opacity: 1,
                                    zIndex: 2
                                })
                            ],
                            parameters: {
                                blend: true,
                                blendFunc: [GL.SRC_ALPHA, GL.ONE_MINUS_SRC_ALPHA],
                                blendEquation: GL.FUNC_ADD
                            }
                        });
                    }
                });
            }

            // Initial settings
            const INITIAL_SETTINGS = {
                trailLength: 1,
                animationSpeed: 3
            };

            // Control panel handlers with updated ranges
            document.getElementById('trail-length').min = 0.5;
            document.getElementById('trail-length').max = 4;
            document.getElementById('trail-length').step = 0.5;
            document.getElementById('trail-length').value = INITIAL_SETTINGS.trailLength;
            document.getElementById('trail-value').textContent = INITIAL_SETTINGS.trailLength;

            document.getElementById('trail-length').oninput = function() {
                trailLength = Number(this.value);
                document.getElementById('trail-value').textContent = this.value;
            };

            document.getElementById('animation-speed').value = INITIAL_SETTINGS.animationSpeed;
            document.getElementById('speed-value').textContent = INITIAL_SETTINGS.animationSpeed;

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