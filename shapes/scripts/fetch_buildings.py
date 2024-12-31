import requests
import geopandas as gpd
import json
import os
import sys
import logging
from shapely.geometry import box, Polygon
import osmnx as ox

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
OUTPUT_DIR = "shapes/data/output"

def is_valid_geojson(geojson):
    """Check if the GeoJSON is valid."""
    if geojson['type'] != 'FeatureCollection':
        logger.error("Invalid GeoJSON: Must be a FeatureCollection")
        return False
    for feature in geojson['features']:
        if feature['type'] != 'Feature':
            logger.error("Invalid GeoJSON: Each item must be a Feature")
            return False
        if 'geometry' not in feature or 'properties' not in feature:
            logger.error("Invalid GeoJSON: Feature must have geometry and properties")
            return False
        if feature['geometry']['type'] != 'Polygon':
            logger.error("Invalid GeoJSON: Geometry type must be Polygon")
            return False
        if not isinstance(feature['geometry']['coordinates'], list) or len(feature['geometry']['coordinates']) == 0:
            logger.error("Invalid GeoJSON: Coordinates must be a non-empty list")
            return False
    return True

def fetch_buildings():
    """Fetch building data for Beer Sheva from OpenStreetMap"""
    logger.info("Fetching building data for Beer Sheva")
    
    try:
        # Beer Sheva approximate bounding box
        north, south = 31.28, 31.23
        east, west = 34.83, 34.77
        
        # Download building footprints from OSM
        buildings = ox.features.features_from_bbox(
            north, south, east, west,
            tags={'building': True}
        )
        
        # Convert to GeoDataFrame
        buildings_gdf = gpd.GeoDataFrame(buildings)
        
        # Add height information based on building levels
        buildings_gdf['height'] = buildings_gdf.apply(
            lambda x: float(x.get('height', x.get('building:levels', 3) * 3)), 
            axis=1
        )
        
        # Convert to the format expected by deck.gl
        features = []
        for idx, row in buildings_gdf.iterrows():
            try:
                # Extract coordinates from the geometry
                if row.geometry.geom_type == 'Polygon':
                    coords = list(row.geometry.exterior.coords)
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[list(coord) for coord in coords]]
                        },
                        "properties": {
                            "height": row['height']
                        }
                    }
                    features.append(feature)
            except Exception as e:
                logger.warning(f"Skipping building {idx}: {str(e)}")
                continue
        
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        # Validate GeoJSON
        if not is_valid_geojson(geojson):
            logger.error("GeoJSON validation failed. Not saving the file.")
            return None
        
        # Save to file
        output_path = os.path.join(OUTPUT_DIR, "buildings.geojson")
        with open(output_path, 'w') as f:
            json.dump(geojson, f)
        
        logger.info(f"Saved {len(features)} buildings to: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error fetching building data: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        output_file = fetch_buildings()
        if output_file:
            print(f"Building data saved to: {output_file}")
    except Exception as e:
        logger.error(f"Failed to fetch building data: {str(e)}")
        sys.exit(1)
