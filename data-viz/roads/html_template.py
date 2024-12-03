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
        </style>
    </head>
    <body>
        <div id="container"></div>
        <div class="control-panel">
            <div>
                <label>Trail Length: <span id="trail-value">4</span></label>
                <input type="range" min="1" max="100" value="4" id="trail-length" style="width: 200px">
            </div>
            <div>
                <label>Animation Speed: <span id="speed-value">2</span></label>
                <input type="range" min="0.5" max="10" step="0.5" value="2" id="animation-speed" style="width: 200px">
            </div>
        </div>
        <div class="time-display">06:00</div>
        <div class="methodology-container">
            <h3 style="margin: 0 0 10px 0;">Methodology</h3>
            <p style="margin: 0; font-size: 0.9em;">
                Represents daily trips (6:00-22:00) across Beer Sheva's road network using temporal distributions.<br>
                Total Daily Trips: %(total_trips)d<br>
                Current simulation time: <span id="current-time">06:00</span><br><br>
                Colors indicate destinations:<br>
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 255, 90); vertical-align: middle;"></span> BGU <br>
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 191, 255); vertical-align: middle;"></span> Gav Yam <br>
                <span style="display: inline-block; width: 20px; height: 10px; background: rgb(170, 0, 255); vertical-align: middle;"></span> Soroka Hospital<br><br>
                Note: The base map darkness can be adjusted by modifying the OVERLAY_OPACITY constant in the code.
            </p>
        </div>
        <script>
            // Define WebGL constants
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
            
            // Update map style to CARTO dark matter (no labels)
            const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json';
            
            let trailLength = 4;
            let animationSpeed = 2;
            let animation;
            
            // Add a new constant for the overlay opacity
            const OVERLAY_OPACITY = 0.5; // Adjust this value to control darkness (0 to 1)
            
            // Add new constants for time simulation
            const HOURS_PER_DAY = 17; // 6:00-22:00
            const START_HOUR = 6;
            const END_HOUR = 22;
            const FRAMES_PER_HOUR = ANIMATION_DURATION / HOURS_PER_DAY;
            
            // Add time formatting function
            function formatTimeString(frame) {
                const hoursElapsed = frame / FRAMES_PER_HOUR;
                const currentHour = Math.floor(START_HOUR + hoursElapsed);
                const minutes = Math.floor((hoursElapsed % 1) * 60);
                return `${currentHour.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            }
            
            const deckgl = new deck.DeckGL({
                container: 'container',
                mapStyle: MAP_STYLE,
                initialViewState: INITIAL_VIEW_STATE,
                controller: true,
                effects: [lightingEffect],
                parameters: {
                    clearColor: [0, 0, 0, 1]  // Black background
                }
            });
            
            // Update color function for higher contrast
            const getPathColor = (path) => {
                const destination = path[path.length - 1];
                const [destLon, destLat] = destination;
                
                const distToBGU = Math.hypot(destLon - BGU_INFO.lon, destLat - BGU_INFO.lat);
                const distToGavYam = Math.hypot(destLon - GAV_YAM_INFO.lon, destLat - GAV_YAM_INFO.lat);
                const distToSoroka = Math.hypot(destLon - SOROKA_INFO.lon, destLat - SOROKA_INFO.lat);
                
                if (distToBGU < POI_RADIUS) return [0, 255, 90];      // Brighter neon green
                if (distToGavYam < POI_RADIUS) return [0, 191, 255];  // Deep sky blue
                if (distToSoroka < POI_RADIUS) return [170, 0, 255];  // Deep purple
                
                return [253, 128, 93];  // Default color
            };
            
            // Update TripsLayer configuration
            const tripsLayer = new deck.TripsLayer({
                id: 'trips',
                data: TRIPS_DATA,
                getPath: d => d.path,
                getTimestamps: d => d.timestamps.flat(),
                getColor: getPathColor,
                opacity: 0.8,
                widthMinPixels: 2,
                jointRounded: true,
                capRounded: true,
                trailLength,
                currentTime: 0
            });

            // Add a new PolygonLayer for POI borders
            const poiBordersLayer = new deck.PolygonLayer({
                id: 'poi-borders',
                data: POI_BORDERS,
                getPolygon: d => d.polygon,
                getLineColor: d => d.color,
                lineWidthMinPixels: 2,
                extruded: false,
                pickable: false,
                opacity: 1,
                zIndex: 1 // Ensure this layer is above others
            });

            // Add a new PolygonLayer for POI fills
            const poiFillsLayer = new deck.PolygonLayer({
                id: 'poi-fills',
                data: POI_FILLS,
                getPolygon: d => d.polygon,
                getFillColor: d => d.color,
                extruded: false,
                pickable: false,
                opacity: 0.5,
                zIndex: 0 // Ensure this layer is below others
            });

            // Update the buildings layer for better visibility of POI buildings
            new deck.PolygonLayer({
                id: 'buildings',
                data: BUILDINGS_DATA,
                extruded: true,
                wireframe: true,
                opacity: 0.9,  // Increased opacity for better visibility
                getPolygon: d => d.polygon,
                getElevation: d => d.height,
                getFillColor: d => d.color[3] === 200 ? d.color : [20, 20, 25, 160],
                getLineColor: [255, 255, 255, 30],
                lineWidthMinPixels: 1,
                material: {
                    ambient: 0.2,
                    diffuse: 0.8,
                    shininess: 32,
                    specularColor: [60, 64, 70]
                }
            })

            // Update the animation function
            function animate() {
                console.log('Animation Configuration:', {
                    totalFrames: LOOP_LENGTH,
                    baseSpeed: animationSpeed,
                    actualDurationSeconds: (LOOP_LENGTH * 60) / animationSpeed / 60,
                    trailLength,
                    hoursSimulated: HOURS_PER_DAY,
                    framesPerHour: FRAMES_PER_HOUR
                });

                let lastTime = 0;
                let lastHour = -1;
                let hourlyStats = {};
                
                animation = popmotion.animate({
                    from: 0,
                    to: LOOP_LENGTH,
                    duration: (LOOP_LENGTH * 60) / animationSpeed,
                    repeat: Infinity,
                    onUpdate: time => {
                        const currentFrame = time % ANIMATION_DURATION;
                        const currentTime = formatTimeString(currentFrame);
                        const currentHour = Math.floor(START_HOUR + (currentFrame / FRAMES_PER_HOUR));
                        
                        // Update time display
                        document.querySelector('.time-display').textContent = currentTime;
                        document.getElementById('current-time').textContent = currentTime;
                        
                        // Log stats when hour changes
                        if (currentHour !== lastHour) {
                            console.log('Hour Change:', {
                                hour: currentHour,
                                time: currentTime,
                                stats: hourlyStats[lastHour] || {}
                            });
                            
                            // Reset hourly stats
                            hourlyStats[currentHour] = {
                                totalTrips: 0,
                                activeTrips: 0
                            };
                            
                            lastHour = currentHour;
                        }
                        
                        if (Math.floor(time) % 60 === 0 && lastTime !== Math.floor(time)) {
                            lastTime = Math.floor(time);
                            
                            // Count active trips for this time period
                            const activeTripsCount = TRIPS_DATA.reduce((sum, route) => {
                                const validTimestamps = route.timestamps[0].filter(t => 
                                    t <= currentFrame && 
                                    t > currentFrame - trailLength
                                );
                                return sum + validTimestamps.length;
                            }, 0);
                            
                            // Update hourly stats
                            if (hourlyStats[currentHour]) {
                                hourlyStats[currentHour].totalTrips += activeTripsCount;
                                hourlyStats[currentHour].activeTrips = activeTripsCount;
                            }
                            
                            console.log('Animation Status:', {
                                frame: Math.floor(currentFrame),
                                time: currentTime,
                                hour: currentHour,
                                activeTrips: activeTripsCount,
                                currentTrailLength: trailLength,
                                currentSpeed: animationSpeed
                            });
                        }
                        
                        // Update layers with current frame...
                        const layers = [
                            // Base dark overlay (should not cover POI areas)
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
                            
                            // POI area fills
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
                            
                            // Buildings
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
                                    return d.timestamps.map(times => {
                                        const validTimes = times.filter(t => 
                                            t <= currentFrame && 
                                            t > currentFrame - trailLength
                                        );
                                        return validTimes.length > 0 ? validTimes[0] : null;
                                    });
                                },
                                getColor: d => getPathColor(d.path),
                                opacity: 0.8,
                                widthMinPixels: 2,
                                jointRounded: true,
                                capRounded: true,
                                trailLength,
                                currentTime: currentFrame,
                                updateTriggers: {
                                    getTimestamps: [currentFrame, trailLength]
                                }
                            }),
                            poiBordersLayer 
                        ];
                        
                        deckgl.setProps({
                            layers,
                            parameters: {
                                blend: true,
                                blendFunc: [GL.SRC_ALPHA, GL.ONE_MINUS_SRC_ALPHA],
                                blendEquation: GL.FUNC_ADD
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
    
# First, let's fix the JavaScript modulo operations by replacing % with %%
HTML_TEMPLATE = re.sub(
    r'(?<![%])%(?![(%sd])',  # Match single % not followed by formatting specifiers
    '%%',                     # Replace with %%
    HTML_TEMPLATE
)