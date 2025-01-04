import geopandas as gpd
import logging
from shapely.geometry import LineString
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
poi_name_to_id = {
            'Ben-Gurion-University': 7,
            'Soroka-Medical-Center': 11
        }

def load_poi_polygons():
    """Load POI polygons from shapefile"""
    attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
    # BGU (7) and Soroka (11)
    poi_polygons = attractions[attractions['ID'].isin([7, 11])].copy()
    if poi_polygons.crs is None or poi_polygons.crs.to_string() != "EPSG:4326":
        poi_polygons = poi_polygons.to_crs("EPSG:4326")
    return poi_polygons

def validate_routes(routes_gdf, poi_polygons, destination_poi):
    """Validate that routes don't cross through unauthorized areas"""
    valid_routes = 0
    total_routes = len(routes_gdf)
    poi_name_to_id = {
        'Ben-Gurion-University': 7,
        'Soroka-Medical-Center': 11
    }
    
    for idx, route in routes_gdf.iterrows():
        route_line = route.geometry
        is_valid = True
        
        # Check intersection with unauthorized polygons
        for _, poi in poi_polygons.iterrows():
            # Skip if this is the destination POI
            if destination_poi and poi_name_to_id.get(destination_poi) == poi['ID']:
                continue
                
            if route_line.intersects(poi.geometry):
                logger.warning(f"Route {idx} intersects unauthorized POI {poi['ID']}")
                is_valid = False
                break
        
        if is_valid:
            valid_routes += 1
            
        # Print progress every 100 routes
        if (idx + 1) % 100 == 0:
            logger.info(f"Processed {idx + 1}/{total_routes} routes...")
    
    return valid_routes, total_routes

def main():
    # Load POI polygons
    poi_polygons = load_poi_polygons()
    logger.info(f"Loaded {len(poi_polygons)} POI polygons")
    
    # Define input files
    input_dir = "data-viz/output/dashboard_data"
    inbound_file = os.path.join(input_dir, "walk_routes_inbound.geojson")
    outbound_file = os.path.join(input_dir, "walk_routes_outbound.geojson")
    
    # Process inbound routes
    logger.info("\nValidating inbound routes...")
    inbound_routes = gpd.read_file(inbound_file)
    
    # Group by destination and validate
    for dest, group in inbound_routes.groupby('destination'):
        valid, total = validate_routes(group, poi_polygons, dest)
        logger.info(f"""
        Destination: {dest}
        - Total routes: {total}
        - Valid routes: {valid}
        - Success rate: {(valid/total)*100:.1f}%
        """)
        
        # Sample invalid routes for inspection
        invalid_count = 0
        for idx, route in group.iterrows():
            if invalid_count >= 5:  # Limit to 5 examples
                break
            for _, poi in poi_polygons.iterrows():
                if poi_name_to_id.get(dest) != poi['ID'] and route.geometry.intersects(poi.geometry):
                    logger.warning(f"""
                    Invalid route example:
                    - Route ID: {route['route_id']}
                    - Origin: ({route['origin_x']}, {route['origin_y']})
                    - Intersects with POI: {poi['ID']}
                    """)
                    invalid_count += 1
                    break
    
    # Process outbound routes
    logger.info("\nValidating outbound routes...")
    outbound_routes = gpd.read_file(outbound_file)
    
    # Group by origin and validate
    for orig, group in outbound_routes.groupby('origin_zone'):
        valid, total = validate_routes(group, poi_polygons, orig)
        logger.info(f"""
        Origin: {orig}
        - Total routes: {total}
        - Valid routes: {valid}
        - Success rate: {(valid/total)*100:.1f}%
        """)
        
        # Sample invalid routes
        invalid_count = 0
        for idx, route in group.iterrows():
            if invalid_count >= 5:  # Limit to 5 examples
                break
            for _, poi in poi_polygons.iterrows():
                if poi_name_to_id.get(orig) != poi['ID'] and route.geometry.intersects(poi.geometry):
                    logger.warning(f"""
                    Invalid route example:
                    - Route ID: {route['route_id']}
                    - Destination: ({route['origin_x']}, {route['origin_y']})
                    - Intersects with POI: {poi['ID']}
                    """)
                    invalid_count += 1
                    break

if __name__ == "__main__":
    main() 