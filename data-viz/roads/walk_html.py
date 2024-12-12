import re

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <title>Walking Trip Animation</title>
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
            background: rgba(0, 0, 0, 0.8);
            padding: 12px;
            border-radius: 5px;
            color: #FFFFFF;
            font-family: Arial;
        }
        .methodology-container {
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.8);
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
        #tooltip {
            position: absolute;
            z-index: 1;
            pointer-events: none;
            background: rgba(0, 0, 0, 0.8);
            padding: 8px;
            color: #fff;
            border-radius: 4px;
            display: none;
        }
    </style>
</head>
<body>
    <div id="container"></div>
    <div id="tooltip"></div>
    <div class="time-display">06:00</div>
    <div class="control-panel">
        <div>
            <label>Trail Length: <span id="trail-value">5</span></label>
            <input type="range" min="1" max="20" value="5" id="trail-length" style="width: 200px">
        </div>
        <div>
            <label>Animation Speed: <span id="speed-value">1</span></label>
            <input type="range" min="0.1" max="5" step="0.1" value="1" id="animation-speed" style="width: 200px">
        </div>
    </div>
    <div class="methodology-container">
        <h3 style="margin: 0 0 10px 0;">Methodology</h3>
        <p style="margin: 0; font-size: 0.9em;">
            Represents individual walking trips to POIs using approximate origin locations.<br>
            Total Daily Trips: %(total_trips)d<br>
            Current Time: <span id="current-time">06:00</span><br>
            <div class="trip-counters">
                Colors indicate destinations:<br>
                <div style="margin-top: 5px;">
                    <span style="display: inline-block; width: 20px; height: 10px; background: rgb(0, 255, 90); vertical-align: middle;"></span>
                    Ben-Gurion University
                </div>
                <div style="margin-top: 5px;">
                    <span style="display: inline-block; width: 20px; height: 10px; background: rgb(170, 0, 255); vertical-align: middle;"></span>
                    Soroka Medical Center
                </div>
            </div>
        </p>
    </div>
    <script>
        const DEBUG = true;
        
        function log(...args) {
            if (DEBUG) {
                console.log(...args);
            }
        }

        // POI information
        const POI_INFO = {
            'Ben-Gurion-University': {
                color: [0, 255, 90, 200],
                lat: 31.2614375,
                lon: 34.7995625
            },
            'Soroka-Medical-Center': {
                color: [170, 0, 255, 200],
                lat: 31.2579375,
                lon: 34.8003125
            }
        };

        // Data constants
        const TRIPS_DATA = %(trips_data)s;
        const BUILDINGS_DATA = %(buildings_data)s;
        const ENTRANCE_FEATURES = %(entrance_features)s;
        const POI_BORDERS = %(poi_borders)s;
        const POI_FILLS = %(poi_fills)s;
        const POI_RADIUS = %(poi_radius)f;

        // Animation constants
        const START_HOUR = 6;
        const END_HOUR = 22;
        const HOURS_PER_DAY = END_HOUR - START_HOUR;
        const ANIMATION_DURATION = 60000; // 60 seconds in milliseconds
        const LOOP_LENGTH = ANIMATION_DURATION;
        const MS_PER_HOUR = ANIMATION_DURATION / HOURS_PER_DAY;

        // Animation state
        let trailLength = 5;
        let animationSpeed = 1;
        let animation;
        let lastLoggedHour = -1;

        const INITIAL_VIEW_STATE = {
            longitude: 34.8113,
            latitude: 31.2627,
            zoom: 14,
            pitch: 45,
            bearing: 0
        };

        log('Animation Constants:', {
            START_HOUR,
            END_HOUR,
            HOURS_PER_DAY,
            ANIMATION_DURATION,
            MS_PER_HOUR,
            'Total Trips': TRIPS_DATA.length
        });

        // Tooltip setup
        const tooltip = document.getElementById('tooltip');
        const updateTooltip = ({x, y, object}) => {
            if (object) {
                tooltip.style.display = 'block';
                tooltip.style.left = x + 'px';
                tooltip.style.top = y + 'px';
                tooltip.innerHTML = object.name || 'Entrance';
            } else {
                tooltip.style.display = 'none';
            }
        };

        const deckgl = new deck.DeckGL({
            container: 'container',
            mapStyle: 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
            initialViewState: INITIAL_VIEW_STATE,
            controller: true
        });

        function formatTimeString(ms) {
            const hoursElapsed = ms / MS_PER_HOUR;
            const currentHour = Math.floor(START_HOUR + hoursElapsed);
            const minutes = Math.floor((hoursElapsed % 1) * 60);
            return `${currentHour.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
        }

        function getPathColor(path) {
            const destination = path.destination;
            return POI_INFO[destination]?.color.slice(0, 3) || [255, 255, 255];
        }

        function animate() {
            log('Starting animation with speed:', animationSpeed);
            
            if (animation) {
                animation.stop();
            }

            animation = popmotion.animate({
                from: 0,
                to: LOOP_LENGTH,
                duration: LOOP_LENGTH / animationSpeed,
                repeat: Infinity,
                onUpdate: time => {
                    const currentFrame = time % ANIMATION_DURATION;
                    const currentHour = Math.floor((currentFrame / MS_PER_HOUR) + START_HOUR);
                    
                    // Log hour transitions
                    if (currentHour !== lastLoggedHour) {
                        log(`Hour transition: ${lastLoggedHour} -> ${currentHour}`);
                        lastLoggedHour = currentHour;
                    }

                    const currentTime = formatTimeString(currentFrame);
                    
                    // Update time displays
                    document.querySelector('.time-display').textContent = currentTime;
                    document.getElementById('current-time').textContent = currentTime;

                    // Debug timing every second
                    if (currentFrame % 1000 < 16) {  // Check approximately every second
                        log('Animation Status:', {
                            time: currentTime,
                            frame: Math.round(currentFrame),
                            hour: currentHour,
                            'active trips': TRIPS_DATA.filter(trip => {
                                const timestamps = trip.timestamps.flat();
                                return timestamps[0] <= currentFrame && 
                                       timestamps[timestamps.length - 1] >= currentFrame;
                            }).length
                        });
                    }

                    const layers = [
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
                            lineWidthMinPixels: 1
                        }),
                        new deck.TripsLayer({
                            id: 'trips',
                            data: TRIPS_DATA,
                            getPath: d => d.path,
                            getTimestamps: d => d.timestamps.flat(),
                            getColor: d => getPathColor(d),
                            opacity: 0.8,
                            widthMinPixels: 2,
                            jointRounded: true,
                            capRounded: true,
                            trailLength: trailLength * 5,
                            currentTime: currentFrame
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
                        }),
                        new deck.ScatterplotLayer({
                            id: 'entrances',
                            data: ENTRANCE_FEATURES,
                            getPosition: d => d.position,
                            getFillColor: [255, 255, 255, 200],
                            getRadius: 5,
                            pickable: true,
                            onHover: updateTooltip
                        })
                    ];

                    deckgl.setProps({layers});
                }
            });
        }

        // Control panel handlers
        document.getElementById('trail-length').oninput = function() {
            trailLength = Number(this.value);
            document.getElementById('trail-value').textContent = this.value;
            log('Trail length changed:', trailLength);
        };

        document.getElementById('animation-speed').oninput = function() {
            animationSpeed = Number(this.value);
            document.getElementById('speed-value').textContent = this.value;
            log('Animation speed changed:', animationSpeed);
            animate();
        };

        // Start animation
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