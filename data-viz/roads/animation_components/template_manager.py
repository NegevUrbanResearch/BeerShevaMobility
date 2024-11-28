import os
from .js_modules import get_animation_core_js, get_layer_definitions_js, get_utility_functions_js
from .animation_helpers import get_debug_panel_html, get_debug_js
from .animation_styles import get_base_styles, get_animation_constants

class AnimationTemplate:
    def __init__(self):
        self.template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        
    def get_html_template(self):
        """Returns the complete HTML template with all components"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset='utf-8'>
            <title>Trip Animation</title>
            {self._get_dependencies()}
            <style>
                {get_base_styles()}
                {get_debug_panel_html()}
            </style>
        </head>
        <body>
            {self._get_html_body()}
            <script>
                // Data variables
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
                
                {get_animation_constants()}
                {get_debug_js()}
                {get_animation_core_js()}
                {get_layer_definitions_js()}
                {get_utility_functions_js()}
                {self._get_event_handlers()}
            </script>
        </body>
        </html>
        """

    def _get_dependencies(self):
        return """
            <script src='https://unpkg.com/deck.gl@latest/dist.min.js'></script>
            <script src='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.js'></script>
            <script src='https://unpkg.com/popmotion@11.0.0/dist/popmotion.js'></script>
            <link href='https://unpkg.com/maplibre-gl@2.4.0/dist/maplibre-gl.css' rel='stylesheet' />
        """

    def _get_html_body(self):
        return """
            <div id="container"></div>
            <div class="control-panel">
                <div>
                    <label>Trail Length: <span id="trail-value">2</span></label>
                    <input type="range" min="1" max="100" value="2" id="trail-length" style="width: 200px">
                </div>
                <div>
                    <label>Animation Speed: <span id="speed-value">4</span></label>
                    <input type="range" min="0.1" max="5" step="0.1" value="4" id="animation-speed" style="width: 200px">
                </div>
            </div>
            <div class="time-display">
                <span id="current-time">00:00</span>
            </div>
            <div class="methodology-container">
                <h3 style="margin: 0 0 10px 0;">Methodology</h3>
                <p style="margin: 0; font-size: 0.9em;">
                    Represents individual trips across Beer Sheva's road network to POI in the Innovation District.<br>
                    Total Daily Trips: %(total_trips)d
                </p>
            </div>
        """

    def _get_event_handlers(self):
        return """
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
        """ 