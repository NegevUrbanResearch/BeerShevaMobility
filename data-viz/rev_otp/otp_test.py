import requests
from datetime import datetime
import polyline
import geopandas as gpd
from shapely.geometry import LineString
import folium
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_walking_route(from_lat, from_lon, to_lat, to_lon, base_url="http://localhost:8080/otp/routers/default"):
    """Test a walking route between two points"""
    params = {
        'fromPlace': f"{from_lat},{from_lon}",
        'toPlace': f"{to_lat},{to_lon}",
        'mode': 'WALK',
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': '09:00:00',
        'arriveBy': 'false',
        'walkSpeed': 1.4
    }
    
    try:
        response = requests.get(f"{base_url}/plan", params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'error' in data:
                logger.error(f"Route error: {data['error']}")
                return None
                
            if 'plan' not in data or not data['plan'].get('itineraries'):
                logger.error("No route found")
                return None
                
            # Extract route geometry
            itinerary = data['plan']['itineraries'][0]
            route_points = []
            for leg in itinerary['legs']:
                points = polyline.decode(leg['legGeometry']['points'])
                route_points.extend(points)
                
            return {
                'geometry': LineString([(lon, lat) for lat, lon in route_points]),
                'duration': itinerary['duration'],
                'distance': itinerary['walkDistance']
            }
    except Exception as e:
        logger.error(f"Error getting route: {str(e)}")
        return None

def create_test_map(routes, poi_polygons):
    """Create a Folium map with the test routes"""
    # Get center point
    center_lat = (poi_polygons.total_bounds[1] + poi_polygons.total_bounds[3]) / 2
    center_lon = (poi_polygons.total_bounds[0] + poi_polygons.total_bounds[2]) / 2
    
    # Create map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=15)
    
    # Add POI polygons
    for _, poi in poi_polygons.iterrows():
        folium.GeoJson(
            poi.geometry.__geo_interface__,
            style_function=lambda x: {
                'fillColor': 'red' if poi['ID'] == 11 else 'blue',
                'color': 'red' if poi['ID'] == 11 else 'blue',
                'fillOpacity': 0.3
            }
        ).add_to(m)
        
    # Add routes
    colors = ['green', 'purple', 'orange', 'yellow']
    for (name, route), color in zip(routes.items(), colors):
        if route:
            folium.GeoJson(
                route['geometry'].__geo_interface__,
                name=name,
                style_function=lambda x, color=color: {
                    'color': color,
                    'weight': 4,
                    'opacity': 0.8
                }
            ).add_to(m)
            
            # Add start/end markers
            coords = list(route['geometry'].coords)
            folium.CircleMarker(
                location=[coords[0][1], coords[0][0]],
                radius=8,
                color=color,
                popup=f"Start of {name}"
            ).add_to(m)
            folium.CircleMarker(
                location=[coords[-1][1], coords[-1][0]],
                radius=8,
                color=color,
                popup=f"End of {name}"
            ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    return m

def main():
    # Load POI polygons
    attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
    poi_polygons = attractions[attractions['ID'].isin([11, 7])]  # BGU and Soroka
    
    # Test points (example coordinates)
    test_routes = {
        "BGU to Soroka": test_walking_route(
            31.262, 34.801,  # BGU
            31.258, 34.800   # Soroka
        ),
        "Soroka to BGU": test_walking_route(
            31.258, 34.800,  # Soroka
            31.262, 34.801   # BGU
        )
    }
    
    # Create visualization
    m = create_test_map(test_routes, poi_polygons)
    
    # Save map
    output_file = "test_routes.html"
    m.save(output_file)
    logger.info(f"Test map saved to {output_file}")
    
    # Print route statistics
    for name, route in test_routes.items():
        if route:
            logger.info(f"\n{name}:")
            logger.info(f"Duration: {route['duration']/60:.1f} minutes")
            logger.info(f"Distance: {route['distance']:.0f} meters")
        else:
            logger.info(f"\n{name}: No route found")

if __name__ == "__main__":
    main()