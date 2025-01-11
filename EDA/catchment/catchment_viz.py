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
        self.project_root = Path(__file__).parent.parent
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
        
        # Color scheme - consistent across all visualizations
        self.mode_colors = {
            'car': '#FF6B6B',       # Bright red
            'transit': '#4ECDC4',    # Turquoise
            'walk': '#FFE66D',       # Yellow
            'bike': '#96CEB4',       # Sage green
            'other': '#FFEEAD'       # Cream
        }
        
        # Load Israel boundary for clipping
        self.israel_boundary = self._load_israel_boundary()
        
        # Add back style parameters
        self.style_params = {
            'single': {
                'weight': 1,
                'fillOpacity': 0.6,
                'opacity': 0.8
            }
        }

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
        """Create a map with layered catchment areas for all modes"""
        # Get POI coordinates
        poi_coords = self.focus_pois[poi_name]
        print(f"\nCreating layered catchment map for {poi_name}")
        
        # Create base map with dark theme and larger font size
        m = folium.Map(
            location=[poi_coords['lat'], poi_coords['lon']],
            tiles='cartodbdark_matter',
            zoom_start=11
        )
        
        # Add CSS to increase font sizes
        css = """
        <style>
            .leaflet-popup-content {
                font-size: 15px !important;
            }
            .leaflet-control-layers-toggle {
                font-size: 15px !important;
            }
            .leaflet-control-attribution {
                font-size: 12px !important;
            }
        </style>
        """
        m.get_root().html.add_child(folium.Element(css))

        # Load POI data
        df, mode_cols = self.load_poi_data(poi_name)
        if df is None:
            return m
            
        # Track catchments
        catchments = []
        
        # Calculate catchments for all modes
        modes = ['car', 'transit', 'walk', 'bike']
        for mode in modes:
            print(f"\nProcessing {mode} mode...")
            
            # Calculate mode-specific trips
            df_mode = df.copy()
            
            if mode == 'walk':
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode['mode_ped']
            elif mode == 'transit':
                transit_cols = ['mode_bus', 'mode_link', 'mode_train']
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[transit_cols].sum(axis=1)
            else:
                mode_col = f'mode_{mode}'
                if mode_col not in mode_cols:
                    continue
                df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[mode_col]
            
            # Prepare points and weights
            valid_data = df_mode.dropna(subset=['centroid_lon', 'centroid_lat'])
            if len(valid_data) > 0:
                points = list(zip(valid_data['centroid_lon'], valid_data['centroid_lat']))
                weights = valid_data['mode_trips'].values
                
                # Calculate catchment
                catchment = self.calculate_catchment_polygon(
                    points=points,
                    weights=weights,
                    poi_coords=poi_coords
                )
                
                if catchment is not None:
                    catchments.append({
                        'mode': mode,
                        'polygon': catchment,
                        'area': catchment.area
                    })
        
        # Sort catchments by area (largest to smallest)
        catchments.sort(key=lambda x: x['area'], reverse=True)
        
        # Calculate bounds that encompass all catchments
        if catchments:
            # Initialize with first catchment bounds
            min_x = float('inf')
            max_x = float('-inf')
            min_y = float('inf')
            max_y = float('-inf')

            # Find min/max bounds across all catchments
            for catchment_data in catchments:
                catchment = catchment_data['polygon']
                bounds = catchment.bounds  # (minx, miny, maxx, maxy)
                min_x = min(min_x, bounds[0])
                min_y = min(min_y, bounds[1])
                max_x = max(max_x, bounds[2])
                max_y = max(max_y, bounds[3])

            # Create base map with calculated bounds
            center_lat = (min_y + max_y) / 2
            center_lon = (min_x + max_x) / 2
            m = folium.Map(
                location=[center_lat, center_lon],
                tiles='cartodbdark_matter'
            )

            # Set bounds with padding
            m.fit_bounds(
                [[min_y, min_x], [max_y, max_x]],
                padding=(30, 30)  # Add 30 pixels padding on all sides
            )
        else:
            # Fallback to POI-centered map if no catchments
            poi_coords = self.focus_pois[poi_name]
            m = folium.Map(
                location=[poi_coords['lat'], poi_coords['lon']],
                tiles='cartodbdark_matter',
                zoom_start=11
            )
        
        # Add catchments to map
        for catchment_data in catchments:
            mode = catchment_data['mode']
            catchment = catchment_data['polygon']
            color = self.mode_colors[mode]
            
            if not catchment.is_empty:
                folium.GeoJson(
                    catchment.__geo_interface__,
                    style_function=lambda x, color=color: {
                        'fillColor': color,
                        'color': color,
                        'weight': 1,
                        'fillOpacity': 0.6,
                        'opacity': 0.8
                    }
                ).add_to(m)
        
        # Add POI marker with larger popup font
        folium.CircleMarker(
            location=[poi_coords['lat'], poi_coords['lon']],
            radius=8,
            color='white',
            fill=True,
            popup=folium.Popup(poi_name, parse_html=True, max_width=300)
        ).add_to(m)
        
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
        
        # Add CSS to increase font sizes
        css = """
        <style>
            .leaflet-popup-content {
                font-size: 15px !important;
            }
            .leaflet-control-layers-toggle {
                font-size: 15px !important;
            }
            .leaflet-control-attribution {
                font-size: 12px !important;
            }
        </style>
        """
        m.get_root().html.add_child(folium.Element(css))

        # Load POI data
        df, mode_cols = self.load_poi_data(poi_name)
        if df is None:
            return m
        
        # Calculate trips by mode
        df_mode = df.copy()
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
                    'weight': 1,
                    'fillOpacity': 0.6,
                    'opacity': 0.8
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
        
        # Add POI marker with larger popup font
        folium.CircleMarker(
            location=[poi_coords['lat'], poi_coords['lon']],
            radius=8,
            color='white',
            fill=True,
            popup=folium.Popup(poi_name, parse_html=True, max_width=300)
        ).add_to(m)
        
        return m
    
    def analyze_catchments(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Integrated analysis of catchment areas and their overlaps.
        
        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (areas_df, overlaps_df)
            - areas_df: Areas for each POI and mode
            - overlaps_df: Overlap calculations between POIs and modes
        """
        modes = ['car', 'transit', 'walk', 'bike']
        areas_dict = {}
        overlaps = []
        catchments = {}  # Store all catchments for overlap calculations
        
        # Calculate all catchments and their areas
        for poi_name in self.focus_pois.keys():
            print(f"\nAnalyzing catchments for {poi_name}")
            poi_areas = {}
            catchments[poi_name] = {}
            
            # Get POI coordinates
            poi_coords = self.focus_pois[poi_name]
            
            # Load POI data
            df, mode_cols = self.load_poi_data(poi_name)
            if df is None:
                continue
                
            # Calculate catchments and areas for each mode
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
                    if mode_col not in mode_cols:
                        poi_areas[mode] = None
                        continue
                    df_mode['mode_trips'] = df_mode['total_trips'] * df_mode[mode_col]
                
                # Prepare points and weights
                valid_data = df_mode.dropna(subset=['centroid_lon', 'centroid_lat'])
                if len(valid_data) > 0:
                    points = list(zip(valid_data['centroid_lon'], valid_data['centroid_lat']))
                    weights = valid_data['mode_trips'].values
                    
                    # Calculate catchment
                    catchment = self.calculate_catchment_polygon(
                        points=points,
                        weights=weights,
                        poi_coords=poi_coords
                    )
                    
                    if catchment is not None:
                        # Store catchment for overlap calculations
                        catchments[poi_name][mode] = catchment
                        
                        # Calculate area
                        gdf_catchment = gpd.GeoDataFrame(geometry=[catchment], crs="EPSG:4326")
                        gdf_catchment_projected = gdf_catchment.to_crs({'proj':'cea'})
                        area_km2 = gdf_catchment_projected.geometry.area.iloc[0] / 10**6
                        poi_areas[mode] = area_km2
                    else:
                        poi_areas[mode] = None
                else:
                    poi_areas[mode] = None
            
            areas_dict[poi_name] = poi_areas
        
        # Calculate overlaps between POIs for each mode
        for mode in modes:
            for poi1 in self.focus_pois.keys():
                for poi2 in self.focus_pois.keys():
                    if poi1 >= poi2:  # Skip duplicate combinations
                        continue
                        
                    if poi1 in catchments and poi2 in catchments:
                        catchment1 = catchments[poi1].get(mode)
                        catchment2 = catchments[poi2].get(mode)
                        
                        if catchment1 is not None and catchment2 is not None:
                            # Calculate overlap
                            gdf1 = gpd.GeoDataFrame(geometry=[catchment1], crs="EPSG:4326")
                            gdf2 = gpd.GeoDataFrame(geometry=[catchment2], crs="EPSG:4326")
                            
                            gdf1_proj = gdf1.to_crs({'proj':'cea'})
                            gdf2_proj = gdf2.to_crs({'proj':'cea'})
                            
                            intersection = gdf1_proj.intersection(gdf2_proj)
                            intersection_area = intersection.area.iloc[0] / 10**6
                            area1 = gdf1_proj.area.iloc[0] / 10**6
                            area2 = gdf2_proj.area.iloc[0] / 10**6
                            
                            overlap_pct1 = (intersection_area / area1) * 100
                            overlap_pct2 = (intersection_area / area2) * 100
                            
                            overlaps.append({
                                'type': 'poi_to_poi',
                                'mode': mode,
                                'entity1': poi1,
                                'entity2': poi2,
                                'intersection_area_km2': intersection_area,
                                'overlap_pct_of_1': overlap_pct1,
                                'overlap_pct_of_2': overlap_pct2
                            })
        
        # Calculate overlaps between modes for each POI
        for poi_name in self.focus_pois.keys():
            if poi_name in catchments:
                for mode1 in modes:
                    for mode2 in modes:
                        if mode1 >= mode2:  # Skip duplicate combinations
                            continue
                            
                        catchment1 = catchments[poi_name].get(mode1)
                        catchment2 = catchments[poi_name].get(mode2)
                        
                        if catchment1 is not None and catchment2 is not None:
                            # Calculate overlap
                            gdf1 = gpd.GeoDataFrame(geometry=[catchment1], crs="EPSG:4326")
                            gdf2 = gpd.GeoDataFrame(geometry=[catchment2], crs="EPSG:4326")
                            
                            gdf1_proj = gdf1.to_crs({'proj':'cea'})
                            gdf2_proj = gdf2.to_crs({'proj':'cea'})
                            
                            intersection = gdf1_proj.intersection(gdf2_proj)
                            intersection_area = intersection.area.iloc[0] / 10**6
                            area1 = gdf1_proj.area.iloc[0] / 10**6
                            area2 = gdf2_proj.area.iloc[0] / 10**6
                            
                            overlap_pct1 = (intersection_area / area1) * 100
                            overlap_pct2 = (intersection_area / area2) * 100
                            
                            overlaps.append({
                                'type': 'mode_to_mode',
                                'poi': poi_name,
                                'entity1': mode1,
                                'entity2': mode2,
                                'intersection_area_km2': intersection_area,
                                'overlap_pct_of_1': overlap_pct1,
                                'overlap_pct_of_2': overlap_pct2
                            })
        
        # Create DataFrames
        areas_df = pd.DataFrame.from_dict(areas_dict, orient='index')
        overlaps_df = pd.DataFrame(overlaps)
        
        # Save results with descriptions
        description = f"""
    Catchment Areas and Overlaps Analysis
    -----------------------------------
    Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d')}

    This analysis contains two main components:

    1. Catchment Areas (areas.csv):
    ------------------------------
    Areas in square kilometers for each POI and transportation mode.

    POIs:
    - BGU: Ben-Gurion University
    - Soroka_Hospital: Soroka Medical Center
    - Gev_Yam: Gav-Yam Negev Advanced Technologies Park

    Modes:
    - car: Private vehicle trips
    - transit: Combined public transit (bus, train, and other transit links)
    - walk: Pedestrian trips
    - bike: Bicycle trips

    2. Overlaps Analysis (overlaps.csv):
    ----------------------------------
    Two types of overlaps are analyzed:
    a) POI-to-POI: Overlap between different POIs for each mode
    b) Mode-to-mode: Overlap between different modes for each POI

    Overlap metrics:
    - intersection_area_km2: Area of overlap in square kilometers
    - overlap_pct_of_1: Percentage of entity1's catchment that overlaps with entity2
    - overlap_pct_of_2: Percentage of entity2's catchment that overlaps with entity1

    Values represent the minimal continuous catchment area containing 90% of trips.
    Areas are calculated in square kilometers using an equal area projection.
    NULL values indicate insufficient data for that combination.
    """
        
        # Save areas
        with open(self.output_dir / 'catchment_areas.csv', 'w') as f:
            f.write(description + '\n\n')
            f.write("CATCHMENT AREAS (square kilometers)\n")
            areas_df.to_csv(f)
        
        # Save overlaps
        with open(self.output_dir / 'catchment_overlaps.csv', 'w') as f:
            f.write(description + '\n\n')
            f.write("CATCHMENT OVERLAPS\n")
            overlaps_df.to_csv(f, index=False)
        
        print(f"\nResults saved to {self.output_dir}")
        return areas_df, overlaps_df

    def generate_all_catchment_maps(self):
        """Generate catchment maps and analyze areas/overlaps for all POIs and modes"""
        modes = ['car', 'transit', 'walk', 'bike']
        
        # First calculate areas and overlaps
        areas_df, overlaps_df = self.analyze_catchments()
        
        print("\nCatchment areas summary (sq km):")
        print(areas_df)
        print("\nOverlap analysis summary:")
        print(overlaps_df)
        
        # Then generate maps as before
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
        
        print(f"\nAll maps and analysis saved to {self.output_dir}")
        return areas_df, overlaps_df

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


