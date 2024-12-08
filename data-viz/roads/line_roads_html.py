import json

def create_html_description(template_data):
    """Create the HTML template for the visualization"""
    
    base_description = """
    <style>
        .control-panel {{
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
        }}
        .time-control {{
            margin-top: 15px;
        }}
        .slider {{
            width: 100%;
            margin: 10px 0;
            -webkit-appearance: none;
            height: 4px;
            background: #444;
            border-radius: 2px;
            outline: none;
        }}
        .slider::-webkit-slider-thumb {{
            -webkit-appearance: none;
            width: 16px;
            height: 16px;
            background: #2196F3;
            border-radius: 50%;
            cursor: pointer;
        }}
        .time-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: #ccc;
        }}
        .stats-panel {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #444;
        }}
        .play-button {{
            background: #2196F3;
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            transition: background 0.3s;
        }}
        .play-button:hover {{
            background: #1976D2;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 8px 0;
        }}
        .legend-color {{
            width: 20px;
            height: 4px;
            margin-right: 8px;
            border-radius: 2px;
        }}
    </style>
    
    <div class="control-panel">
        <h3 style="margin-top: 0;">Trip Visualization</h3>
        <p>Total Daily Trips: {total_trips:,}</p>
        
        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: rgb(20,42,120)"></div>
                <span>Low Traffic (<{low_trips:.0f} trips)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgb(65,182,196)"></div>
                <span>Medium Traffic ({low_trips:.0f}-{med_trips:.0f})</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgb(255,255,0)"></div>
                <span>High Traffic (>{med_trips:.0f} trips)</span>
            </div>
        </div>
        
        <div class="time-control">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <button id="playButton" class="play-button">Play</button>
                <span id="timeDisplay" style="font-size: 24px; font-family: monospace;">06:00</span>
            </div>
            <input type="range" id="hourSlider" class="slider" min="6" max="22" value="6" step="0.25">
            <div class="time-labels">
                <span>6:00</span>
                <span>14:00</span>
                <span>22:00</span>
            </div>
        </div>
        
        <div style="margin-top: 10px;">
            <label>Animation Speed: <span id="speedValue">1.0</span>x</label>
            <input type="range" id="speedSlider" class="slider" min="0.5" max="5" step="0.5" value="1">
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
        // Store data and state
        const lineData = {line_data};
        const temporalStats = {temporal_stats};
        let currentHour = 6;
        let isPlaying = false;
        let animationSpeed = 1;
        let animationFrame;
        
        // Update visualization with interpolation
        function updateVisualization(hour) {{
            // Calculate base hour and interpolation factor
            const baseHour = Math.floor(hour);
            const nextHour = Math.min(22, baseHour + 1);
            const factor = hour - baseHour;
            
            // Get data for current and next hour
            const currentData = lineData[baseHour] || [];
            const nextData = lineData[nextHour] || [];
            
            // Interpolate between hours
            const interpolatedData = currentData.map((segment, index) => {{
                const nextSegment = nextData[index];
                if (!nextSegment) return segment;
                
                return {{
                    ...segment,
                    color: segment.color.map((c, i) => 
                        Math.round(c + (nextSegment.color[i] - c) * factor)
                    )
                }};
            }});
            
            // Update deck.gl layer
            if (window.deck) {{
                window.deck.setProps({{
                    layers: [
                        ...window.deck.props.layers.filter(l => l.id !== 'LineLayer'),
                        new deck.LineLayer({{
                            id: 'LineLayer',
                            data: interpolatedData,
                            getSourcePosition: d => d.start,
                            getTargetPosition: d => d.end,
                            getColor: d => d.color,
                            getWidth: 3,
                            pickable: true,
                            opacity: 0.8,
                            transitions: {{
                                getColor: 300,
                                getWidth: 300
                            }}
                        }})
                    ]
                }});
            }}
            
            // Update UI
            const minutes = Math.round((hour % 1) * 60);
            const timeString = `${{Math.floor(hour).toString().padStart(2, '0')}}:${{minutes.toString().padStart(2, '0')}}`;
            document.getElementById('timeDisplay').textContent = timeString;
            document.getElementById('hourSlider').value = hour;
            
            // Update stats
            const stats = temporalStats[Math.floor(hour)];
            if (stats) {{
                document.getElementById('segmentCount').textContent = stats.num_segments.toLocaleString();
                document.getElementById('tripCount').textContent = stats.total_trips.toLocaleString();
            }}
        }}

        function animate() {{
            if (!isPlaying) return;
            
            currentHour += 0.25 * animationSpeed / 60;  // Smooth animation
            if (currentHour > 22) currentHour = 6;
            
            updateVisualization(currentHour);
            animationFrame = requestAnimationFrame(animate);
        }}

        // Event Listeners
        document.getElementById('playButton').addEventListener('click', function() {{
            isPlaying = !isPlaying;
            this.textContent = isPlaying ? 'Pause' : 'Play';
            if (isPlaying) {{
                animate();
            }} else {{
                cancelAnimationFrame(animationFrame);
            }}
        }});

        document.getElementById('hourSlider').addEventListener('input', function(e) {{
            currentHour = parseFloat(e.target.value);
            updateVisualization(currentHour);
            isPlaying = false;
            document.getElementById('playButton').textContent = 'Play';
            cancelAnimationFrame(animationFrame);
        }});

        document.getElementById('speedSlider').addEventListener('input', function(e) {{
            animationSpeed = parseFloat(e.target.value);
            document.getElementById('speedValue').textContent = animationSpeed.toFixed(1);
        }});

        // Initialize
        updateVisualization(currentHour);
    </script>
    """.format(
        total_trips=template_data['total_trips'],
        low_trips=template_data['low_trips'],
        med_trips=template_data['med_trips'],
        line_data=json.dumps(template_data['line_data']),
        temporal_stats=json.dumps(template_data['temporal_stats'])
    )
    
    return base_description