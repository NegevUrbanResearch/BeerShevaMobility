from pathlib import Path
import jinja2
import shutil

class CatchmentDashboard:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.maps_dir = self.project_root / "output" / "catchment_maps"
        self.output_dir = self.project_root / "output" / "dashboard"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Define POIs with display names and file names
        self.poi_info = {
            'BGU': {
                'display': 'Ben Gurion University',
                'file': 'bgu'
            },
            'Soroka_Hospital': {
                'display': 'Soroka Hospital',
                'file': 'soroka_hospital'
            },
            'Gev_Yam': {
                'display': 'Gav Yam High-Tech Park',
                'file': 'gev_yam'
            }
        }
        
        # Define modes with display names and colors
        self.mode_info = {
            'all': {'display': 'All Modes', 'color': '#FFEEAD'},
            'car': {'display': 'Car', 'color': '#FF6B6B'},
            'transit': {'display': 'Public Transit', 'color': '#4ECDC4'},
            'walk': {'display': 'Walking', 'color': '#45B7D1'},
            'bike': {'display': 'Bicycle', 'color': '#96CEB4'}
        }
        
        # Copy all map files to dashboard directory
        self._copy_maps()

    def _copy_maps(self):
        """Copy all map HTML files to dashboard directory"""
        for map_file in self.maps_dir.glob("*.html"):
            shutil.copy2(map_file, self.output_dir)

    def generate_dashboard(self):
        """Generate the main dashboard HTML"""
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Beer Sheva Catchment Areas Dashboard</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 0; 
                    padding: 0;
                    background: #1a1a1a;
                    color: #ffffff;
                }
                .controls { 
                    position: fixed;
                    top: 20px;
                    left: 60px;
                    background: rgba(33, 33, 33, 0.9);
                    padding: 12px;
                    border-radius: 8px;
                    box-shadow: 0 0 15px rgba(0,0,0,0.3);
                    z-index: 1000;
                    width: 160px;
                }
                .controls h3 {
                    margin: 0 0 12px 0;
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    color: #ffffff;
                    border-bottom: 1px solid #444;
                    padding-bottom: 8px;
                }
                .btn-group { 
                    margin-bottom: 12px;
                }
                .btn-group p {
                    margin: 0 0 4px 0;
                    font-size: 12px;
                    color: #999;
                }
                button {
                    display: block;
                    width: 100%;
                    padding: 6px 8px;
                    margin: 2px 0;
                    border: 1px solid #444;
                    border-radius: 4px;
                    cursor: pointer;
                    background: #333;
                    color: #fff;
                    font-size: 12px;
                    text-align: left;
                    transition: all 0.2s ease;
                }
                button:hover {
                    background: #444;
                }
                button.active {
                    background: #0066cc;
                    border-color: #0077ee;
                }
                #map-container {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                }
                #map-frame {
                    width: 100%;
                    height: 100%;
                    border: none;
                }
                .methods-note {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    background: rgba(33, 33, 33, 0.9);
                    padding: 12px;
                    border-radius: 8px;
                    box-shadow: 0 0 15px rgba(0,0,0,0.3);
                    max-width: 250px;
                    font-size: 12px;
                    color: #ffffff;
                }
                .methods-note h4 {
                    margin: 0 0 8px 0;
                    font-size: 13px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    color: #999;
                }
                .methods-note p {
                    margin: 0 0 8px 0;
                    line-height: 1.4;
                }
                button.mode-btn {
                    padding-left: 24px;
                    position: relative;
                }
                button.mode-btn::before {
                    content: '';
                    position: absolute;
                    left: 8px;
                    top: 50%;
                    transform: translateY(-50%);
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                }
                {% for mode, info in mode_info.items() %}
                button.mode-btn.{{ mode }}::before {
                    background-color: {{ info.color }};
                }
                {% endfor %}
            </style>
        </head>
        <body>
            <div class="controls">
                <h3>Catchment Areas</h3>
                <div class="btn-group">
                    <p>Location</p>
                    {% for poi_id, info in poi_info.items() %}
                    <button onclick="selectPOI('{{ poi_id }}')" id="poi-{{ poi_id }}">{{ info.display }}</button>
                    {% endfor %}
                </div>
                <div class="btn-group">
                    <p>Transport Mode</p>
                    {% for mode_id, info in mode_info.items() %}
                    <button onclick="selectMode('{{ mode_id }}')" id="mode-{{ mode_id }}" class="mode-btn {{ mode_id }}">
                        {{ info.display }}
                    </button>
                    {% endfor %}
                </div>
            </div>
            
            <div class="methods-note">
                <h4>Methodology</h4>
                <p>These catchment areas represent the minimal continuous region containing 90% of trips to each destination.</p>
                <p>Colors indicate transport mode:</p>
                {% for mode_id, info in mode_info.items() if mode_id != 'all' %}
                <p style="color: {{ info.color }}">● {{ info.display }}</p>
                {% endfor %}
            </div>

            <div id="map-container">
                <iframe id="map-frame" src=""></iframe>
            </div>

            <script>
                // Initialize with first POI and mode
                let currentPOI = '{{ poi_info.keys()|list|first }}';
                let currentMode = '{{ mode_info.keys()|list|first }}';
                
                const poiInfo = {{ poi_info|tojson|safe }};

                function updateMap() {
                    const modeSuffix = currentMode === 'all' ? 'all' : currentMode;
                    const filename = `${poiInfo[currentPOI].file}_catchment_${modeSuffix}.html`;
                    document.getElementById('map-frame').src = filename;
                    
                    document.querySelectorAll('button').forEach(btn => btn.classList.remove('active'));
                    document.getElementById(`poi-${currentPOI}`).classList.add('active');
                    document.getElementById(`mode-${currentMode}`).classList.add('active');
                }

                function selectPOI(poi) {
                    currentPOI = poi;
                    updateMap();
                }

                function selectMode(mode) {
                    currentMode = mode;
                    updateMap();
                }

                document.addEventListener('DOMContentLoaded', function() {
                    selectPOI('{{ poi_info.keys()|list|first }}');
                    selectMode('{{ mode_info.keys()|list|first }}');
                });
            </script>
        </body>
        </html>
        """
        
        # Render template
        template = jinja2.Template(template)
        html = template.render(
            poi_info=self.poi_info,
            mode_info=self.mode_info
        )
        
        # Save dashboard
        with open(self.output_dir / "index.html", "w") as f:
            f.write(html)
        
        print(f"Dashboard generated at: {self.output_dir / 'index.html'}")

if __name__ == "__main__":
    dashboard = CatchmentDashboard()
    dashboard.generate_dashboard() 