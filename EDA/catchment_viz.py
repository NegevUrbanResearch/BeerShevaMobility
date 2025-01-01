import folium
from folium.plugins import HeatMap
import pandas as pd
import numpy as np
from pathlib import Path
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import geopandas as gpd
from typing import Dict, List, Tuple
import json
import geopy.distance

class CatchmentVisualizer:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.data_dir = self.project_root / "output" / "dashboard_data"
        self.output_dir = self.project_root / "output" / "catchment_maps"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load zones data first
        self.zones_file = self.project_root / "output" / "dashboard_data" / "zones.geojson"
        print(f"\nLoading zones from: {self.zones_file}")
        self.zones = self.load_zones()
        
        print(f"Loaded {len(self.zones)} zones with columns:", self.zones.columns.tolist())
        
        # Innovation district POIs with their standardized file names
        self.focus_pois = {
            'BGU': {'lat': 31.262218, 'lon': 34.801472},
            'Soroka_Hospital': {'lat': 31.262650, 'lon': 34.799452},
            'Gev_Yam': {'lat': 31.263500, 'lon': 34.803500}
        }
        
        # Updated color scheme for better visibility in overlays
        self.mode_colors = {
            'car': '#FF6B6B',      # Bright red
            'transit': '#4ECDC4',   # Turquoise
            'walk': '#FFE66D',      # Yellow
            'bike': '#96CEB4',      # Sage green
            'other': '#FFEEAD'      # Cream
        }
        
        # Define mode order for layering (from top to bottom)
        self.mode_order = ['walk', 'bike', 'car', 'transit']
        
        # Define style parameters
        self.style_params = {
            'single': {
                'weight': 1,           # Thinner border
                'fillOpacity': 0.4,    # Moderate fill opacity
                'opacity': 0.3         # Very transparent border
            },
            'overlay': {
                'weight': 1,           # Thinner border
                'fillOpacity': 0.25,   # More transparent fill for overlays
                'opacity': 0.2         # Very transparent border
            }
        }
        
        # Load Israel boundary for clipping
        self.israel_boundary = self._load_israel_boundary()

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

    def load_poi_data(self, poi_name: str) -> pd.DataFrame:
        """Load and prepare POI data"""
        try:
            # Load data
            df = pd.read_csv(self.data_dir / f"{poi_name}_inbound_trips.csv")
            
            # Print columns for debugging
            print(f"\nColumns in {poi_name} data:")
            print(df.columns.tolist())
            
            # Merge with zones to get centroids
            df = df.merge(
                self.zones[['YISHUV_STAT11', 'geometry', 'centroid_lon', 'centroid_lat']], 
                left_on='tract',
                right_on='YISHUV_STAT11',
                how='left'
            )
            
            # Debug merge results
            print(f"\nMerge results for {poi_name}:")
            print(f"Original rows: {len(df)}")
            print(f"Rows with valid centroids: {df['centroid_lon'].notna().sum()}")
            
            # Get mode columns
            mode_cols = [col for col in df.columns if col.startswith('mode_')]
            print(f"\nMode columns found: {mode_cols}")
            
            return df, mode_cols
            
        except Exception as e:
            print(f"Error loading data for {poi_name}: {str(e)}")
            return None, None

    def calculate_catchment_polygon(self, 
                                points: List[Tuple[float, float]], 
                                weights: List[float],
                                poi_coords: Dict[str, float],
                                mode: str = None,
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

    def create_layered_catchment_map(self, poi_name: str) -> folium.Map:
        """Create a map with layered catchment areas for all modes, ordered by size"""
        # Get POI coordinates
        poi_coords = self.focus_pois[poi_name]
        print(f"\nCreating layered catchment map for {poi_name}")
        
        # Create base map
        m = folium.Map(
            location=[poi_coords['lat'], poi_coords['lon']],
            tiles='cartodbdark_matter'
        )
        
        # Load POI data
        df, mode_cols = self.load_poi_data(poi_name)
        if df is None:
            return m
            
        # Track map bounds and catchments
        all_bounds = []
        catchments = []
        
        # Calculate catchments for all modes
        modes = ['car', 'transit', 'walk', 'bike']
        for mode in modes:
            print(f"\nProcessing {mode} mode...")
            
            # Calculate mode-specific trips
            df_mode = df.copy()  # Create a copy for each mode
            
            if mode == 'walk':
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode['mode_ped']
            elif mode == 'transit':
                transit_cols = ['mode_bus', 'mode_link', 'mode_train']
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[transit_cols].sum(axis=1)
            else:
                mode_col = f'mode_{mode}'
                if mode_col not in mode_cols:
                    print(f"Warning: Mode column {mode_col} not found")
                    continue
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[mode_col]
            
            # Prepare points and weights
            valid_data = df_mode.dropna(subset=['centroid_lon', 'centroid_lat'])
            if len(valid_data) > 0:  # Only proceed if we have valid data
                points = list(zip(valid_data['centroid_lon'], valid_data['centroid_lat']))
                weights = valid_data['mode_trips'].values
                
                # Calculate catchment
                catchment = self.calculate_catchment_polygon(
                    points=points,
                    weights=weights,
                    poi_coords=poi_coords
                )
                
                if catchment is not None:
                    # Store catchment with its area and mode
                    area = catchment.area
                    catchments.append({
                        'mode': mode,
                        'polygon': catchment,
                        'area': area
                    })
                    
                    # Track bounds
                    all_bounds.extend([
                        [catchment.bounds[1], catchment.bounds[0]],  # SW corner
                        [catchment.bounds[3], catchment.bounds[2]]   # NE corner
                    ])
        
        # Sort catchments by area (largest to smallest) and add to map
        catchments.sort(key=lambda x: x['area'], reverse=True)
        
        # Add catchments to map in order (largest first, so smallest will be on top)
        for catchment_data in catchments:
            mode = catchment_data['mode']
            catchment = catchment_data['polygon']
            color = self.mode_colors[mode]
            
            folium.GeoJson(
                catchment.__geo_interface__,
                style_function=lambda x, color=color: {
                    'fillColor': color,
                    'color': color,
                    **self.style_params['overlay']
                },
                name=f"{mode.capitalize()} ({catchment_data['area']:.2f} sq deg)"
            ).add_to(m)
        
        # Add POI marker
        folium.CircleMarker(
            location=[poi_coords['lat'], poi_coords['lon']],
            radius=8,
            color='white',
            fill=True,
            popup=poi_name
        ).add_to(m)
        
        # Add layer control
        folium.LayerControl().add_to(m)
        
        # Fit map to bounds if we have them
        if all_bounds:
            m.fit_bounds(all_bounds, padding=(30, 30))
        else:
            m.location = [poi_coords['lat'], poi_coords['lon']]
            m.zoom_start = 11
        
        return m

    def create_catchment_map(self, poi_name: str, mode: str = None) -> folium.Map:
        """Create single-mode catchment area map for a POI"""
        # Get POI coordinates
        poi_coords = self.focus_pois[poi_name]
        print(f"\nCreating map for {poi_name}")
        print(f"POI coordinates: lat={poi_coords['lat']}, lon={poi_coords['lon']}")
        print(f"Mode filter: {mode}")
        
        # Create base map
        m = folium.Map(
            location=[poi_coords['lat'], poi_coords['lon']],
            tiles='cartodbdark_matter'
        )
        
        # Load POI data
        df, mode_cols = self.load_poi_data(poi_name)
        if df is None:
            return m
        
        # Calculate trips by mode
        df_mode = df.copy()  # Create a copy for mode-specific calculations
        if mode:
            if mode == 'walk':
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode['mode_ped']
            elif mode == 'transit':
                transit_cols = ['mode_bus', 'mode_link', 'mode_train']
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[transit_cols].sum(axis=1)
            else:
                mode_col = f'mode_{mode}'
                if mode_col not in mode_cols:
                    return m
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[mode_col]
        else:
            df_mode['mode_trips'] = df_mode['total_trips']

        # Prepare points and weights
        valid_data = df_mode.dropna(subset=['centroid_lon', 'centroid_lat'])
        points = list(zip(valid_data['centroid_lon'], valid_data['centroid_lat']))
        weights = valid_data['mode_trips'].values
        
        # Calculate catchment
        catchment = self.calculate_catchment_polygon(
            points=points,
            weights=weights,
            poi_coords=poi_coords
        )
        
        # Add catchment to map if valid
        if catchment is not None:
            color = self.mode_colors.get(mode, self.mode_colors['other'])
            folium.GeoJson(
                catchment.__geo_interface__,
                style_function=lambda x: {
                    'fillColor': color,
                    'color': color,
                    **self.style_params['single']
                }
            ).add_to(m)
            
            # Set bounds
            bounds = [
                [catchment.bounds[1], catchment.bounds[0]],
                [catchment.bounds[3], catchment.bounds[2]]
            ]
            m.fit_bounds(bounds, padding=(30, 30))
        else:
            m.location = [poi_coords['lat'], poi_coords['lon']]
            m.zoom_start = 11
        
        # Add POI marker
        folium.CircleMarker(
            location=[poi_coords['lat'], poi_coords['lon']],
            radius=8,
            color='white',
            fill=True,
            popup=poi_name
        ).add_to(m)
        
        return m

    def generate_all_catchment_maps(self):
        """Generate catchment maps for all POIs and modes"""
        modes = ['car', 'transit', 'walk', 'bike']
        
        for poi_name in self.focus_pois.keys():
            print(f"\nGenerating catchment maps for {poi_name}")
            
            # Generate layered catchment map
            m = self.create_layered_catchment_map(poi_name)
            m.save(self.output_dir / f"{poi_name.lower()}_catchment_layered.html")
            print(f"Saved layered catchment map for {poi_name}")
            
            # Generate mode-specific catchment maps
            for mode in modes:
                print(f"\nProcessing {mode} mode for {poi_name}...")
                m = self.create_catchment_map(poi_name, mode)
                m.save(self.output_dir / f"{poi_name.lower()}_catchment_{mode}.html")
                print(f"Saved {mode} catchment map for {poi_name}")
                
            print(f"All maps saved to {self.output_dir}")

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

if __name__ == "__main__":
    visualizer = CatchmentVisualizer()
    visualizer.generate_all_catchment_maps()