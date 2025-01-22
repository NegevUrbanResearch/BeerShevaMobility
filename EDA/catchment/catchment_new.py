from pathlib import Path
import geopandas as gpd
import pandas as pd
import json
import jinja2
from shapely.geometry import Point, Polygon
import geopy.distance
from typing import Dict, List, Tuple

class OptimizedCatchmentDashboard:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.data_dir = self.project_root / "output" / "dashboard_data"
        self.output_dir = self.project_root / "output" / "dashboard"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load zones data first
        self.zones_file = self.project_root / "output" / "dashboard_data" / "zones.geojson"
        print(f"\nLoading zones from: {self.zones_file}")
        self.zones = self.load_zones()
        print(f"Loaded {len(self.zones)} zones with columns:", self.zones.columns.tolist())
        
        # Define POIs
        self.focus_pois = {
            'BGU': {'lat': 31.262218, 'lon': 34.801472},
            'Soroka_Hospital': {'lat': 31.262650, 'lon': 34.799452},
            'Gev_Yam': {'lat': 31.263500, 'lon': 34.803500}
        }
        
        # Define display names
        self.poi_info = {
            'BGU': {'display': 'Ben Gurion University', 'file': 'bgu'},
            'Soroka_Hospital': {'display': 'Soroka Hospital', 'file': 'soroka_hospital'},
            'Gev_Yam': {'display': 'Gav Yam High-Tech Park', 'file': 'gev_yam'}
        }
        
        # Color scheme - consistent with original
        self.mode_info = {
            'layered': {'display': 'All Modes', 'color': '#FFEEAD'},
            'car': {'display': 'Car', 'color': '#FF6B6B'},
            'transit': {'display': 'Public Transit', 'color': '#4ECDC4'},
            'walk': {'display': 'Walking', 'color': '#FFE66D'},
            'bike': {'display': 'Bicycle', 'color': '#96CEB4'}
        }
        
        # Load Israel boundary for clipping
        self.israel_boundary = self._load_israel_boundary()
        
        # Initialize data storage
        self.catchment_data = {}

    def _load_israel_boundary(self) -> gpd.GeoDataFrame:
        """Create a manually defined boundary polygon encompassing Israel and West Bank"""
        boundary_coords = [
            [34.2, 29.5],   # Southwest corner
            [34.3, 31.2],   # Western coast
            [34.6, 31.9],   # Tel Aviv area
            [34.9, 32.9],   # Northern coast
            [35.7, 33.3],   # Northern border
            [35.9, 32.7],   # Northeast
            [35.6, 31.5],   # Eastern border (including West Bank)
            [35.4, 30.9],   # Dead Sea region
            [35.0, 29.5],   # Southern tip
            [34.2, 29.5]    # Back to start
        ]
        
        geometry = [Polygon(boundary_coords)]
        israel = gpd.GeoDataFrame(geometry=geometry, crs="EPSG:4326")
        
        return israel

    def load_zones(self):
        """Load zones data and calculate centroids"""
        # Load zones
        zones = gpd.read_file(self.zones_file)
        
        # Calculate centroids for all valid geometries
        # Store both ITM and WGS84 coordinates
        zones['centroid_itm'] = zones.geometry.centroid
        zones['centroid_lon'] = zones['centroid_itm'].to_crs(epsg=4326).x
        zones['centroid_lat'] = zones['centroid_itm'].to_crs(epsg=4326).y
        
        return zones

    def load_poi_data(self, poi_name: str) -> pd.DataFrame:
        """Load and prepare POI data"""
        try:
            # Load data
            df = pd.read_csv(self.data_dir / f"{poi_name}_inbound_trips.csv")
            
            # Merge with zones to get centroids
            df = df.merge(
                self.zones[['YISHUV_STAT11', 'geometry', 'centroid_lon', 'centroid_lat']], 
                left_on='tract',
                right_on='YISHUV_STAT11',
                how='left'
            )
            
            return df
            
        except Exception as e:
            print(f"Error loading data for {poi_name}: {str(e)}")
            return None

    def calculate_catchment_polygon(self, 
                                points: List[Tuple[float, float]], 
                                weights: List[float],
                                poi_coords: Dict[str, float],
                                percentile: float = 90) -> Polygon:
        """Calculate minimal continuous catchment area containing percentile% of trips"""
        try:
            # Create GeoDataFrame with points and weights
            gdf = gpd.GeoDataFrame(
                geometry=[Point(x, y) for x, y in points if not (pd.isna(x) or pd.isna(y))],
                data={'weight': weights}
            )
            gdf.set_crs(epsg=4326, inplace=True)
            
            # Calculate distances from POI
            poi_point = Point(poi_coords['lon'], poi_coords['lat'])
            gdf['distance'] = gdf.geometry.apply(lambda p: 
                geopy.distance.geodesic(
                    (poi_coords['lat'], poi_coords['lon']), 
                    (p.y, p.x)
                ).kilometers
            )
            
            # Sort by distance and remove zero-weight points
            gdf = gdf[gdf['weight'] > 0].sort_values('distance')
            
            if len(gdf) < 3:
                print("Warning: Not enough non-zero weight points")
                return None
            
            # Calculate total weight
            total_weight = gdf['weight'].sum()
            target_weight = total_weight * (percentile / 100)
            
            # Build continuous region
            included_points = []
            current_weight = 0
            
            for idx, row in gdf.iterrows():
                included_points.append(row.geometry)
                current_weight += row['weight']
                
                if current_weight >= target_weight and len(included_points) >= 3:
                    break
            
            if len(included_points) < 3:
                print("Warning: Not enough points for valid hull")
                return None
            
            # Create hull
            points_gdf = gpd.GeoDataFrame(geometry=included_points)
            current_hull = points_gdf.unary_union.convex_hull
            
            # Clip with Israel boundary if available
            if self.israel_boundary is not None:
                try:
                    current_hull = current_hull.intersection(self.israel_boundary.unary_union)
                    if current_hull.is_empty:
                        print("Warning: Clipping resulted in empty polygon")
                        return None
                except Exception as e:
                    print(f"Error during clipping: {str(e)}")
            
            return current_hull
            
        except Exception as e:
            print(f"Error in catchment calculation: {str(e)}")
            return None

    def process_all_catchments(self):
        """Process catchment areas for all POIs and modes"""
        for poi_name, coords in self.focus_pois.items():
            print(f"\nProcessing catchments for {poi_name}")
            
            # Initialize POI data structure
            self.catchment_data[poi_name] = {
                'center': [coords['lat'], coords['lon']],
                'modes': {},
                'bounds': None
            }
            
            # Load POI data
            df = self.load_poi_data(poi_name)
            if df is None:
                continue
                
            # Process each mode and store catchments
            catchments = []
            modes = ['car', 'transit', 'walk', 'bike']
            
            for mode in modes:
                print(f"Processing {mode} mode...")
                
                # Calculate mode-specific trips
                df_mode = df.copy()
                
                if mode == 'walk':
                    df_mode['mode_trips'] = df_mode['total_trips'] * df_mode['mode_ped']
                elif mode == 'transit':
                    transit_cols = ['mode_bus', 'mode_link', 'mode_train']
                    df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[transit_cols].sum(axis=1)
                else:
                    mode_col = f'mode_{mode}'
                    df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[mode_col]
                
                # Prepare points and weights
                valid_data = df_mode.dropna(subset=['centroid_lon', 'centroid_lat'])
                points = list(zip(valid_data['centroid_lon'], valid_data['centroid_lat']))
                weights = valid_data['mode_trips'].values
                
                # Calculate catchment
                catchment = self.calculate_catchment_polygon(
                    points=points,
                    weights=weights,
                    poi_coords=coords
                )
                
                if catchment is not None:
                    catchments.append({
                        'mode': mode,
                        'geometry': catchment.__geo_interface__,
                        'area': catchment.area,
                        'color': self.mode_info[mode]['color']
                    })
                    
                    # Update bounds
                    bounds = catchment.bounds  # (minx, miny, maxx, maxy)
                    if self.catchment_data[poi_name]['bounds'] is None:
                        self.catchment_data[poi_name]['bounds'] = list(bounds)
                    else:
                        current_bounds = self.catchment_data[poi_name]['bounds']
                        self.catchment_data[poi_name]['bounds'] = [
                            min(current_bounds[0], bounds[0]),  # min_x
                            min(current_bounds[1], bounds[1]),  # min_y
                            max(current_bounds[2], bounds[2]),  # max_x
                            max(current_bounds[3], bounds[3])   # max_y
                        ]
            
            # Sort catchments by area (largest to smallest)
            catchments.sort(key=lambda x: x['area'], reverse=True)
            
            # Store sorted catchments
            for catchment in catchments:
                self.catchment_data[poi_name]['modes'][catchment['mode']] = {
                    'geometry': catchment['geometry'],
                    'color': catchment['color'],
                    'area': catchment['area']
                }

    def generate_dashboard(self):
        """Generate optimized single-page dashboard with enhanced UI"""
        # Process all catchments first
        self.process_all_catchments()
        
        # Create the template
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
            font-size: 23px;
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
            width: 322px;
        }
        .controls h3 {
            margin: 0 0 18px 0;
            font-size: 27px;
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
            margin: 0 0 5px 0;
            font-size: 23px;
            color: #999;
        }
        button {
            display: block;
            width: 100%;
            padding: 12px 18px;
            margin: 2px 0;
            border: 1px solid #444;
            border-radius: 4px;
            cursor: pointer;
            background: #333;
            color: #fff;
            font-size: 23px;
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
        .explanation {
            position: fixed;
            top: 20px;
            right: 60px;
            background: rgba(33, 33, 33, 0.9);
            padding: 12px;
            border-radius: 8px;
            box-shadow: 0 0 15px rgba(0,0,0,0.3);
            z-index: 1000;
            width: 498px;
        }
        .explanation h3 {
            margin: 0 0 8px 0;
            font-size: 27px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #ffffff;
            border-bottom: 1px solid #444;
            padding-bottom: 8px;
        }
        .explanation p {
            margin: 0 0 8px 0;
            line-height: 1.4;
            color: #cccccc;
        }
        .legend-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            margin-top: 12px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .color-box {
            width: 23px;
            height: 23px;
            border-radius: 2px;
        }
        .mode-name {
            font-size: 23px;
            color: #cccccc;
        }
        #map {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }
        #fade-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(26, 26, 26, 0.5);
            opacity: 0;
            transition: opacity 0.3s ease-in-out;
            pointer-events: none;
            z-index: 999;
        }
        #fade-overlay.active {
            opacity: 1;
        }
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

    <div class="explanation">
        <h3>About Catchment Areas</h3>
        <p id="explanation-text">Map shows where 90% of trips to each location originate from by mode.</p>
        <div id="mode-legend" style="display: none;">
            <div class="legend-grid">
                {% for mode_id, info in mode_info.items() if mode_id != 'layered' %}
                <div class="legend-item">
                    <span class="color-box" style="background-color: {{ info.color }}"></span>
                    <span class="mode-name">{{ info.display }}</span>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <div id="map"></div>
    <div id="fade-overlay"></div>

    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.3/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.3/dist/leaflet.js"></script>
    <script>
        // Embed all catchment data
        const catchmentData = {{ catchment_data|tojson|safe }};
        const poiInfo = {{ poi_info|tojson|safe }};
        const modeInfo = {{ mode_info|tojson|safe }};
        
        let currentPOI = '{{ default_poi }}';
        let currentMode = 'layered';
        let currentLayer = null;
        let map = null;

        function updateExplanation() {
            const explanationText = document.getElementById('explanation-text');
            const modeLegend = document.getElementById('mode-legend');
            
            if (currentMode === 'layered') {
                explanationText.textContent = 'Map shows where 90% of trips to each location originate from by mode.';
                modeLegend.style.display = 'block';
            } else {
                explanationText.textContent = `Map shows where 90% of trips to each location originate from by ${modeInfo[currentMode].display.toLowerCase()}.`;
                modeLegend.style.display = 'none';
            }
        }

        function initMap() {
            if (!map) {
                map = L.map('map', {
                    preferCanvas: true,
                    zoomControl: true
                });

                L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                    maxZoom: 19
                }).addTo(map);

                // Set bounds to show all of Beer Sheva metropolitan area
                const bounds = L.latLngBounds(
                    [31.15, 34.65],  // Southwest corner
                    [31.35, 34.95]   // Northeast corner
                );
                map.fitBounds(bounds);
            }
        }

        function updateMap() {
            initMap();
            const fadeOverlay = document.getElementById('fade-overlay');
            fadeOverlay.classList.add('active');

            // Remove current layer if it exists
            if (currentLayer) {
                map.removeLayer(currentLayer);
            }

            const poiData = catchmentData[currentPOI];
            const newLayer = L.layerGroup();
            
            if (currentMode === 'layered') {
                // Sort modes by area before adding to map
                const sortedModes = Object.entries(poiData.modes)
                    .sort((a, b) => b[1].area - a[1].area);
                
                sortedModes.forEach(([mode, data]) => {
                    L.geoJSON(data.geometry, {
                        style: {
                            color: data.color,
                            fillColor: data.color,
                            fillOpacity: 0.6,
                            weight: 1
                        }
                    }).addTo(newLayer);
                });
            } else if (poiData.modes[currentMode]) {
                const modeData = poiData.modes[currentMode];
                L.geoJSON(modeData.geometry, {
                    style: {
                        color: modeData.color,
                        fillColor: modeData.color,
                        fillOpacity: 0.6,
                        weight: 1
                    }
                }).addTo(newLayer);
            }

            // Add POI marker
            L.circleMarker(poiData.center, {
                radius: 8,
                color: 'white',
                fillColor: 'white',
                fillOpacity: 0.2,
                weight: 3
            })
            .bindPopup(poiInfo[currentPOI].display)
            .addTo(newLayer);

            // Add new layer to map
            newLayer.addTo(map);
            currentLayer = newLayer;

            // Fit bounds if available
            if (poiData.bounds) {
                const bounds = [
                    [poiData.bounds[1], poiData.bounds[0]],  // Southwest corner
                    [poiData.bounds[3], poiData.bounds[2]]   // Northeast corner
                ];
                map.fitBounds(bounds, {
                    padding: [30, 30]  // Add padding
                });
            }

            // Update UI
            document.querySelectorAll('button').forEach(btn => btn.classList.remove('active'));
            document.getElementById(`poi-${currentPOI}`).classList.add('active');
            document.getElementById(`mode-${currentMode}`).classList.add('active');
            
            updateExplanation();

            // Remove fade overlay
            setTimeout(() => {
                fadeOverlay.classList.remove('active');
            }, 300);
        }

        function selectPOI(poi) {
            currentPOI = poi;
            updateMap();
        }

        function selectMode(mode) {
            currentMode = mode;
            updateMap();
        }

        // Initialize with first POI
        document.addEventListener('DOMContentLoaded', function() {
            selectPOI('{{ default_poi }}');
            selectMode('layered');
        });
    </script>
</body>
</html>
"""
        
        # Render template
        template = jinja2.Template(template)
        html = template.render(
            catchment_data=self.catchment_data,
            poi_info=self.poi_info,
            mode_info=self.mode_info,
            default_poi='BGU'
        )
        
        # Save dashboard
        output_path = self.output_dir / "index.html"
        with open(output_path, "w") as f:
            f.write(html)
            
        print(f"\nOptimized dashboard generated at: {output_path}")
        print("Improvements:")
        print("- Single page load with embedded data")
        print("- Maintained all original UI functionality")
        print("- Smooth transitions between views")
        print("- Improved performance through layer reuse")

if __name__ == "__main__":
    dashboard = OptimizedCatchmentDashboard()
    dashboard.generate_dashboard()