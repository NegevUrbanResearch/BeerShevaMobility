import json
def create_html_template(template_data):
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'>
        <title>Hourly Trip Routes</title>
        <script src='https://unpkg.com/deck.gl@8.8.27/dist.min.js'></script>
        <script src='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js'></script>
        <link href='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css' rel='stylesheet' />
        <style>
            body { margin: 0; padding: 0; }
            #container { width: 100vw; height: 100vh; position: relative; }
            .control-panel {
                position: absolute;
                top: 20px;
                right: 20px;
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 15px;
                border-radius: 8px;
                font-family: Arial;
                width: 300px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                z-index: 1000;
            }
            .time-control {
                margin-top: 15px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
            }
            .stats-panel {
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #444;
            }
            .nav-button {
                background: #2196F3;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                cursor: pointer;
                transition: background 0.3s;
                min-width: 40px;
            }
            .nav-button:hover {
                background: #1976D2;
            }
            .nav-button:disabled {
                background: #666;
                cursor: not-allowed;
            }
            .time-display {
                font-size: 24px;
                font-family: monospace;
                min-width: 80px;
                text-align: center;
            }
            .legend-item {
                display: flex;
                align-items: center;
                margin: 8px 0;
            }
            .legend-color {
                width: 20px;
                height: 4px;
                margin-right: 8px;
                border-radius: 2px;
            }
            .slider {
                width: 100%%;
                margin: 10px 0;
                -webkit-appearance: none;
                height: 4px;
                background: #444;
                border-radius: 2px;
                outline: none;
            }
            .slider::-webkit-slider-thumb {
                -webkit-appearance: none;
                width: 16px;
                height: 16px;
                background: #2196F3;
                border-radius: 50%%;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div id="container"></div>
        
        <div class="control-panel">
            <h3 style="margin-top: 0;">Trip Visualization</h3>
            <p>Total Daily Trips: <span id="totalTrips">%(total_trips)s</span></p>
            
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color" style="background: rgb(10,20,90)"></div>
                    <span>Very Low Traffic</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: rgb(65,105,225)"></div>
                    <span>Low Traffic</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: rgb(0,191,255)"></div>
                    <span>Moderate Traffic</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: rgb(0,255,255)"></div>
                    <span>Medium Traffic</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: rgb(50,205,50)"></div>
                    <span>Medium-High Traffic</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: rgb(255,215,0)"></div>
                    <span>High Traffic</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: rgb(255,69,0)"></div>
                    <span>Very High Traffic</span>
                </div>
            </div>
            
            <div class="time-control">
                <button id="prevHour" class="nav-button">←</button>
                <span id="timeDisplay" class="time-display">06:00</span>
                <button id="nextHour" class="nav-button">→</button>
            </div>
            
            <div style="margin-top: 10px;">
                <label>Transition Speed: <span id="speedValue">1.0</span>s</label>
                <input type="range" id="transitionSpeed" class="slider" 
                       min="0.5" max="2.0" step="0.1" value="1.0">
            </div>
            
            <div class="stats-panel">
                <div>Current Hour Stats:</div>
                <div id="hourlyStats" style="font-size: 12px; margin-top: 5px;">
                    Active Segments: <span id="segmentCount">0</span><br>
                    Total Trips: <span id="tripCount">0</span>
                </div>
            </div>
        </div>

        <script>
            // Initialize data
            const lineData = %(line_data)s;
            const temporalStats = %(temporal_stats)s;
            const buildingLayers = %(building_layers)s;
            const initialViewState = %(initial_view_state)s;
            let deckgl = null;
            
            // Animation state
            let currentHour = 6;
            let transitionSpeed = 1.0;
            let isTransitioning = false;
            
            // Create map instance
            const map = new maplibregl.Map({
                container: 'container',
                style: 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
                interactive: false,
                ...initialViewState
            });

            function createBuildingLayer() {
                return new deck.PolygonLayer({
                    id: 'buildings',
                    data: buildingLayers,
                    getPolygon: d => d.polygon,
                    getFillColor: d => d.color,
                    getElevation: d => d.height,
                    extruded: true,
                    wireframe: true,
                    lineWidthMinPixels: 1,
                    opacity: 1.0,
                    material: {
                        ambient: 0.2,
                        diffuse: 0.8,
                        shininess: 32,
                        specularColor: [60, 64, 70]
                    }
                });
            }

            function createLineLayer(hour) {
                return new deck.LineLayer({
                    id: 'trip-lines',
                    data: lineData[hour.toString()] || [],
                    getSourcePosition: d => d.start,
                    getTargetPosition: d => d.end,
                    getColor: d => d.color,
                    getWidth: d => 2,
                    pickable: true,
                    opacity: 0.8
                });
            }

            function createLayers(hour) {
                return [
                    createBuildingLayer(),
                    createLineLayer(hour)
                ];
            }

            function updateVisualization(hour) {
                if (!deckgl) return;
                
                // Update layers
                deckgl.setProps({
                    layers: createLayers(hour)
                });
                
                // Update UI
                document.getElementById('timeDisplay').textContent = 
                    `${hour.toString().padStart(2, '0')}:00`;
                
                const stats = temporalStats[hour.toString()];
                if (stats) {
                    document.getElementById('segmentCount').textContent = 
                        stats.num_segments.toLocaleString();
                    document.getElementById('tripCount').textContent = 
                        stats.total_trips.toLocaleString();
                }

                // Update navigation buttons
                document.getElementById('prevHour').disabled = hour <= 6;
                document.getElementById('nextHour').disabled = hour >= 22;
            }

            async function transitionToHour(targetHour) {
                if (isTransitioning) return;
                isTransitioning = true;

                const duration = transitionSpeed * 1000; // Convert to milliseconds
                const startTime = performance.now();
                const startData = lineData[currentHour.toString()] || [];
                const endData = lineData[targetHour.toString()] || [];

                function animate(currentTime) {
                    const elapsed = currentTime - startTime;
                    const progress = Math.min(elapsed / duration, 1);

                    // Fade out then in
                    const opacity = progress < 0.5 ? 
                        1 - progress * 2 : 
                        (progress - 0.5) * 2;

                    deckgl.setProps({
                        layers: [
                            createBuildingLayer(),
                            new deck.LineLayer({
                                id: 'trip-lines',
                                data: progress < 0.5 ? startData : endData,
                                getSourcePosition: d => d.start,
                                getTargetPosition: d => d.end,
                                getColor: d => d.color,
                                getWidth: d => 2,
                                pickable: true,
                                opacity: opacity * 0.8
                            })
                        ]
                    });

                    if (progress < 1) {
                        requestAnimationFrame(animate);
                    } else {
                        currentHour = targetHour;
                        updateVisualization(currentHour);
                        isTransitioning = false;
                    }
                }

                requestAnimationFrame(animate);
            }

            // Event Listeners
            document.getElementById('prevHour').addEventListener('click', () => {
                if (currentHour > 6 && !isTransitioning) {
                    transitionToHour(currentHour - 1);
                }
            });

            document.getElementById('nextHour').addEventListener('click', () => {
                if (currentHour < 22 && !isTransitioning) {
                    transitionToHour(currentHour + 1);
                }
            });

            document.getElementById('transitionSpeed').addEventListener('input', function(e) {
                transitionSpeed = parseFloat(e.target.value);
                document.getElementById('speedValue').textContent = transitionSpeed.toFixed(1);
            });

            // Keyboard navigation
            document.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowLeft') {
                    document.getElementById('prevHour').click();
                } else if (e.key === 'ArrowRight') {
                    document.getElementById('nextHour').click();
                }
            });

            // Initialize visualization when map loads
            map.on('load', () => {
                deckgl = new deck.DeckGL({
                    container: 'container',
                    mapStyle: null,
                    initialViewState: initialViewState,
                    controller: true,
                    onViewStateChange: ({viewState}) => {
                        map.jumpTo({
                            center: [viewState.longitude, viewState.latitude],
                            zoom: viewState.zoom,
                            bearing: viewState.bearing,
                            pitch: viewState.pitch
                        });
                    }
                });
                
                // Initial visualization
                updateVisualization(currentHour);
            });
        </script>
    </body>
    </html>
    """ % {
        'total_trips': "{:,}".format(template_data['total_trips']),
        'line_data': json.dumps(template_data['line_data']),
        'temporal_stats': json.dumps(template_data['temporal_stats']),
        'building_layers': json.dumps(template_data['building_layers']),
        'initial_view_state': json.dumps(template_data['initial_view_state'])
    }