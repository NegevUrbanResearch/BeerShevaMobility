import osmium
import geopandas as gpd
from shapely.geometry import Point, LineString
from shapely.ops import split
import logging
import os
import time
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

class OSMAccessHandler(osmium.SimpleHandler):
    def __init__(self, exclude_polygons):
        super().__init__()
        self.exclude_polygons = exclude_polygons
        self.nodes = {}
        self.ways = {}
        
        # Stats
        self.total_ways = 0
        self.excluded_ways = 0
        self.kept_ways = 0
        
    def node(self, n):
        """Store nodes that aren't in excluded areas"""
        point = Point(n.location.lon, n.location.lat)
        
        # Skip nodes within excluded areas
        for _, poly in self.exclude_polygons.iterrows():
            if point.within(poly.geometry):
                return
                
        self.nodes[n.id] = {
            'lon': n.location.lon,
            'lat': n.location.lat,
            'tags': {tag.k: tag.v for tag in n.tags}
        }
    
    def way(self, w):
        """Store ways that don't intersect excluded areas"""
        self.total_ways += 1
        
        # Create LineString from way nodes
        way_coords = []
        for n in w.nodes:
            if n.ref in self.nodes:
                way_coords.append((self.nodes[n.ref]['lon'], self.nodes[n.ref]['lat']))
        
        if len(way_coords) < 2:
            return
            
        way_line = LineString(way_coords)
        
        # Skip ways that intersect excluded areas
        for _, poly in self.exclude_polygons.iterrows():
            if way_line.intersects(poly.geometry):
                self.excluded_ways += 1
                if self.excluded_ways % 100 == 0:
                    logger.info(f"Excluded {self.excluded_ways} ways...")
                return
        
        self.kept_ways += 1
        self.ways[w.id] = {
            'nodes': [n.ref for n in w.nodes],
            'tags': {t.k: t.v for t in w.tags}
        }

def create_filtered_networks(otp_dir, poi_polygons):
    """Create three filtered networks excluding different POIs
    
    This creates three variants of the network for different routing purposes:
    
    1. network_no_bgu.osm.pbf:
       - Excludes all roads within BGU campus
       - Use for routing to/from Soroka Hospital
       - Build OTP graph: otp --build --save graphs/no_bgu
    
    2. network_no_soroka.osm.pbf:
       - Excludes all roads within Soroka Hospital
       - Use for routing to/from BGU campus
       - Build OTP graph: otp --build --save graphs/no_soroka
    
    3. network_no_both.osm.pbf:
       - Excludes roads in both BGU and Soroka
       - Use for general routing avoiding both areas
       - Build OTP graph: otp --build --save graphs/no_both
    
    4. Original network (israel-and-palestine-latest.osm.pbf):
       - Contains all roads
       - Use as baseline for comparison
       - Build OTP graph: otp --build --save graphs/original
    
    After building graphs, configure OTP to use appropriate graph based on origin/destination:
    - For trips to BGU: Use no_soroka graph
    - For trips to Soroka: Use no_bgu graph
    - For other trips: Use no_both graph
    - For baseline comparison: Use original graph
    """
    logger.info("Creating filtered networks...")
    start_time = time.time()
    
    graphs_dir = os.path.join(otp_dir, 'graphs')
    osm_path = os.path.join(graphs_dir, 'israel-and-palestine-latest.osm.pbf')
    
    # Create variants
    variants = {
        'no_bgu': poi_polygons[poi_polygons['ID'] == 7],  # BGU only
        'no_soroka': poi_polygons[poi_polygons['ID'] == 11],  # Soroka only
        'no_both': poi_polygons  # Both
    }
    
    for i, (name, exclude_pois) in enumerate(variants.items(), 1):
        logger.info(f"\nCreating variant {i} of {len(variants)}: {name}")
        output_path = os.path.join(graphs_dir, f'network_{name}.osm.pbf')
        
        variant_start = time.time()
        handler = OSMAccessHandler(exclude_pois)
        
        # Add progress logging during file processing
        logger.info("Reading OSM file and filtering elements...")
        handler.apply_file(osm_path)
        
        logger.info(f"Network statistics for {name}:")
        logger.info(f"Total ways processed: {handler.total_ways:,}")
        logger.info(f"Ways excluded: {handler.excluded_ways:,}")
        logger.info(f"Ways kept: {handler.kept_ways:,}")
        
        # Write filtered network with progress updates
        writer = osmium.SimpleWriter(output_path)
        
        logger.info(f"Writing {len(handler.nodes):,} nodes...")
        node_count = 0
        for node_id, node in handler.nodes.items():
            writer.add_node(
                osmium.osm.mutable.Node(
                    id=node_id,
                    location=osmium.osm.Location(node['lon'], node['lat']),
                    tags=node['tags']
                )
            )
            node_count += 1
            if node_count % 100000 == 0:
                logger.info(f"Wrote {node_count:,} nodes...")
        
        logger.info(f"Writing {len(handler.ways):,} ways...")
        way_count = 0
        for way_id, way in handler.ways.items():
            writer.add_way(
                osmium.osm.mutable.Way(
                    id=way_id,
                    nodes=way['nodes'],
                    tags=way['tags']
                )
            )
            way_count += 1
            if way_count % 50000 == 0:
                logger.info(f"Wrote {way_count:,} ways...")
        
        writer.close()
        
        # Report file size and timing
        output_size = os.path.getsize(output_path) / (1024 * 1024)
        variant_time = time.time() - variant_start
        logger.info(f"Output file size: {output_size:.1f} MB")
        logger.info(f"Variant processing time: {variant_time:.1f} seconds")
    
    total_time = time.time() - start_time
    logger.info(f"\nTotal processing time: {total_time:.1f} seconds")
    logger.info("\nNext steps:")
    logger.info("1. Build OTP graphs for each variant:")
    logger.info("   otp --build --save graphs/no_bgu")
    logger.info("   otp --build --save graphs/no_soroka")
    logger.info("   otp --build --save graphs/no_both")
    logger.info("2. Configure OTP to use appropriate graph based on trip type")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logger.info("Starting script...")
    
    # Load POI polygons
    logger.info("Loading POI polygons...")
    attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
    poi_polygons = attractions[attractions['ID'].isin([11, 7])]  # BGU and Soroka

    # Check CRS and convert if needed
    if poi_polygons.crs is None:
        logger.warning("POI polygons have no CRS defined, assuming ITM")
        poi_polygons.set_crs("EPSG:2039", inplace=True)

    if poi_polygons.crs.to_string() != "EPSG:4326":  # WGS 84
        logger.info(f"Converting POI polygons from {poi_polygons.crs} to WGS 84")
        poi_polygons = poi_polygons.to_crs("EPSG:4326")
    else:
        logger.info("POI polygons already in WGS 84")

    logger.info(f"Loaded {len(poi_polygons)} POI polygons")
    logger.info(f"POI bounds (WGS 84): {poi_polygons.total_bounds}")
    logger.info(f"POI areas: {poi_polygons.area.tolist()}")
    
    # After loading POI polygons
    logger.info("Validating POI geometries...")
    for idx, poi in poi_polygons.iterrows():
        logger.info(f"POI {poi.get('name', idx)}:")
        logger.info(f"  - Geometry type: {poi.geometry.geom_type}")
        logger.info(f"  - Bounds: {poi.geometry.bounds}")
        logger.info(f"  - Valid: {poi.geometry.is_valid}")
        if not poi.geometry.is_valid:
            logger.warning(f"  - Invalid geometry: {poi.geometry.explain_validity()}")
    
    create_filtered_networks(
        "/Users/noamgal/Downloads/NUR/otp_project",
        poi_polygons
    )