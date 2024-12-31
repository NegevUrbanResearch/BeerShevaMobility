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
        
        # Color scheme for different modes
        self.mode_colors = {
            'car': '#FF6B6B',
            'transit': '#4ECDC4',
            'walk': '#45B7D1',
            'bike': '#96CEB4',
            'other': '#FFEEAD'
        }
        
        # Load Israel boundary for clipping
        self.israel_boundary = self._load_israel_boundary()

    def _load_israel_boundary(self) -> gpd.GeoDataFrame:
        """Create a manually defined boundary polygon encompassing Israel and West Bank"""
        # Define coordinates for a polygon that covers Israel and West Bank
        # Format: [lon, lat] pairs
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
        
        # Create polygon and GeoDataFrame
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
            print("Sample of merged data:")
            print(df[['tract', 'YISHUV_STAT11', 'centroid_lon', 'centroid_lat']].head())
            
            # Get mode columns - Update this section to be more specific
            mode_cols = [col for col in df.columns if col.startswith('mode_')]
            print(f"\nMode columns found: {mode_cols}")
            
            # Verify the mode columns are what we expect
            expected_modes = {'mode_car', 'mode_transit', 'mode_walk', 'mode_bike'}
            found_modes = set(mode_cols)
            if not expected_modes.issubset(found_modes):
                print("\nWARNING: Missing expected mode columns!")
                print(f"Expected: {expected_modes}")
                print(f"Found: {found_modes}")
            
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
            
            print(f"\nWeight Analysis:")
            print(f"Total trips: {total_weight:.0f}")
            print(f"Target {percentile}% weight: {target_weight:.0f}")
            
            # Build continuous region
            included_points = []
            current_weight = 0
            current_hull = None
            
            for idx, row in gdf.iterrows():
                # Add point
                included_points.append(row.geometry)
                current_weight += row['weight']
                
                # Update hull
                if len(included_points) >= 3:
                    points_gdf = gpd.GeoDataFrame(geometry=included_points)
                    current_hull = points_gdf.unary_union.convex_hull
                    
                # Break if we've reached our target weight
                if current_weight >= target_weight:
                    break
                    
            print(f"Final included weight: {current_weight:.0f} ({(current_weight/total_weight*100):.1f}%)")
            print(f"Number of zones included: {len(included_points)}")
            
            if current_hull is None or len(included_points) < 3:
                print("Warning: Could not create valid hull")
                return None
                
            # Clip with Israel boundary if available
            if self.israel_boundary is not None:
                try:
                    current_hull = current_hull.intersection(self.israel_boundary.unary_union)
                    if current_hull.is_empty:
                        print("Warning: Clipping resulted in empty polygon")
                        return None
                except Exception as e:
                    print(f"Error during clipping: {str(e)}")
                    
            # Calculate and print stats about the catchment
            included_gdf = gdf.iloc[:len(included_points)]
            max_dist = included_gdf['distance'].max()
            avg_dist = included_gdf['distance'].mean()
            
            print(f"\nCatchment Statistics:")
            print(f"Maximum distance: {max_dist:.2f}km")
            print(f"Average distance: {avg_dist:.2f}km")
            print(f"Area: {current_hull.area:.6f} square degrees")
            
            return current_hull
            
        except Exception as e:
            print(f"Error in catchment calculation: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return None

    def create_catchment_map(self, 
                            poi_name: str, 
                            mode: str = None) -> folium.Map:
        """Create catchment area map for a POI and transport mode"""
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
            print("Warning: No POI data loaded")
            return m
        
        # Calculate trips by mode - Updated mode handling
        if mode:
            if mode == 'walk':
                mode_col = 'mode_ped'
            elif mode == 'transit':
                # Combine all transit modes (bus, link, train)
                transit_cols = ['mode_bus', 'mode_link', 'mode_train']
                print(f"\nCombining transit modes: {transit_cols}")
                df['mode_trips'] = df['total_trips'] * df[transit_cols].sum(axis=1)
            else:
                mode_col = f'mode_{mode}'
                
            if mode != 'transit' and mode_col not in mode_cols:
                print(f"\nWARNING: Mode column {mode_col} not found in {mode_cols}")
                return m
                
            if mode != 'transit':
                print(f"\nCalculating trips for mode: {mode} using column {mode_col}")
                df['mode_trips'] = df['total_trips'] * df[mode_col]
        else:
            df['mode_trips'] = df['total_trips']
            print("\nUsing total trips (no mode filter)")

        print(f"Total trips in dataset: {df['mode_trips'].sum():.0f}")
        
        # Prepare points and weights
        valid_data = df.dropna(subset=['centroid_lon', 'centroid_lat'])
        points = list(zip(valid_data['centroid_lon'], valid_data['centroid_lat']))
        weights = valid_data['mode_trips'].values
        
        print(f"\nValid points for catchment: {len(points)}")
        print("Sample points (first 3):")
        for i, (lon, lat) in enumerate(points[:3]):
            print(f"Point {i+1}: lon={lon:.6f}, lat={lat:.6f}, weight={weights[i]:.2f}")
        
        # Calculate catchment with POI coordinates
        catchment = self.calculate_catchment_polygon(
            points=points,
            weights=weights,
            poi_coords=poi_coords  # Added missing argument
        )
        
        # Track map bounds
        bounds = None
        
        # Add catchment area to map if valid
        if catchment is not None:
            color = self.mode_colors.get(mode, self.mode_colors['other'])
            print(f"\nAdding catchment polygon to map with color: {color}")
            
            try:
                geojson_data = catchment.__geo_interface__
                print("Successfully converted catchment to GeoJSON")
                print(f"GeoJSON type: {geojson_data['type']}")
                
                # Get bounds from the catchment polygon
                bounds = [
                    [catchment.bounds[1], catchment.bounds[0]],  # SW corner [lat, lon]
                    [catchment.bounds[3], catchment.bounds[2]]   # NE corner [lat, lon]
                ]
                
                folium.GeoJson(
                    geojson_data,
                    style_function=lambda x: {
                        'fillColor': color,
                        'color': color,
                        'weight': 2,
                        'fillOpacity': 0.4
                    }
                ).add_to(m)
                print("Added catchment polygon to map")
            except Exception as e:
                print(f"Error adding catchment to map: {str(e)}")
                import traceback
                print(traceback.format_exc())
        else:
            print("Warning: No valid catchment polygon to add to map")
        
        # Add POI marker
        folium.CircleMarker(
            location=[poi_coords['lat'], poi_coords['lon']],
            radius=8,
            color='white',
            fill=True,
            popup=poi_name
        ).add_to(m)
        print("Added POI marker to map")
        
        # Fit map to bounds if we have them, otherwise zoom to POI
        if bounds:
            m.fit_bounds(bounds, padding=(30, 30))
        else:
            m.location = [poi_coords['lat'], poi_coords['lon']]
            m.zoom_start = 11
        
        return m
    
    def generate_all_catchment_maps(self):
        """Generate catchment maps for all POIs and modes"""
        modes = ['car', 'transit', 'walk', 'bike']
        
        for poi_name in self.focus_pois.keys():
            print(f"\nGenerating catchment maps for {poi_name}")
            
            # Generate overall catchment map
            m = self.create_catchment_map(poi_name)
            m.save(self.output_dir / f"{poi_name.lower()}_catchment_all.html")
            print(f"Saved overall catchment map for {poi_name}")
            
            # Generate mode-specific catchment maps
            for mode in modes:
                print(f"\nProcessing {mode} mode for {poi_name}...")
                m = self.create_catchment_map(poi_name, mode)
                m.save(self.output_dir / f"{poi_name.lower()}_catchment_{mode}.html")
                print(f"Saved {mode} catchment map for {poi_name}")
                
            print(f"All maps saved to {self.output_dir}")

    def load_zones(self):
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