import pytest
import geopandas as gpd
from shapely.geometry import LineString, Point
import os
from ..coordinate_utils import CoordinateValidator

class TestRouteValidation:
    @pytest.fixture
    def poi_polygons(self):
        """Fixture to load POI polygons"""
        attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
        poi_polygons = attractions[attractions['ID'].isin([7, 11])].copy()
        return poi_polygons.to_crs("EPSG:4326")

    @pytest.fixture
    def sample_routes(self):
        """Fixture for sample route data"""
        return {
            'inbound': gpd.read_file("data-viz/output/dashboard_data/walk_routes_inbound.geojson"),
            'outbound': gpd.read_file("data-viz/output/dashboard_data/walk_routes_outbound.geojson"),
            'car': gpd.read_file("data-viz/output/dashboard_data/car_routes_inbound.geojson")
        }

    def test_poi_intersection(self, sample_routes, poi_polygons):
        """Test that routes don't intersect unauthorized POIs"""
        poi_name_to_id = {
            'Ben-Gurion-University': 7,
            'Soroka-Medical-Center': 11
        }

        for route_type, routes in sample_routes.items():
            for _, route in routes.iterrows():
                # Parse origin POI from route ID for outbound routes
                route_id = route['route_id']
                route_parts = route_id.split('-')
                
                # Route ID format: ZONEID-POI-direction-number
                # e.g., "90000111-Ben-Gurion-University-outbound-0"
                if len(route_parts) >= 4:
                    poi_name = '-'.join(route_parts[1:-2])  # Handle POI names with hyphens
                else:
                    continue

                for _, poi in poi_polygons.iterrows():
                    # For outbound routes, check if current POI is the origin POI
                    if route_type == 'outbound':
                        if poi_name_to_id.get(poi_name) == poi['ID']:
                            continue
                    # For inbound/car routes, check destination
                    else:
                        if poi_name_to_id.get(route['destination']) == poi['ID']:
                            continue
                    
                    assert not route.geometry.intersects(poi.geometry), \
                        f"{route_type} route {route['route_id']} intersects unauthorized POI {poi['ID']}"

    @pytest.mark.parametrize("route_type", ["inbound", "outbound", "car"])
    def test_required_attributes(self, sample_routes, route_type):
        """Test that routes have all required attributes"""
        required_fields = [
            'route_id', 'num_trips', 'origin_zone', 'destination',
            'geometry', 'departure_time', 'arrival_time'
        ]
        
        routes = sample_routes[route_type]
        for field in required_fields:
            assert field in routes.columns, \
                f"Missing required field '{field}' in {route_type} routes"