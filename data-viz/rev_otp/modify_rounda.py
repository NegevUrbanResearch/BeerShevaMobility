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
    def __init__(self, poi_polygons):
        super().__init__()
        self.poi_polygons = poi_polygons
        # Store nodes and ways we need to modify
        self.nodes = {}
        self.ways_to_modify = {}
        self.unmodified_ways = {}
        
        # First pass: collect nodes and ways in bounds
        self.first_pass = True
        self.nodes_in_area = set()  # Store node IDs in our area
        
        # Store POI bounds with buffer
        buffer_meters = 1000
        buffer_deg = buffer_meters / 111000  # rough conversion
        
        bounds = poi_polygons.total_bounds
        self.min_lat = bounds[1] - buffer_deg
        self.max_lat = bounds[3] + buffer_deg
        self.min_lon = bounds[0] - buffer_deg
        self.max_lon = bounds[2] + buffer_deg
        
        logger.info(f"Search bounds (with {buffer_meters}m buffer around POIs):")
        logger.info(f"  Latitude:  {self.min_lat:.6f} to {self.max_lat:.6f}")
        logger.info(f"  Longitude: {self.min_lon:.6f} to {self.max_lon:.6f}")
        
        # Stats
        self.total_nodes = 0
        self.nodes_in_bounds = 0
        self.total_ways = 0
        self.ways_in_bounds = 0
        self.ways_split = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.phase = "nodes"  # Track current processing phase
        
        # Add storage for unmodified ways
        self.unmodified_ways = {}
    
    def _create_node(self, lon, lat):
        """Create a new node at the given coordinates"""
        self.next_node_id -= 1
        self.new_nodes[self.next_node_id] = {
            'lon': lon,
            'lat': lat,
            'tags': {}  # No special tags needed for intersection nodes
        }
        return self.next_node_id
    
    def _interpolate_nodes(self, line):
        """Create nodes for all points in a line"""
        nodes = []
        for x, y in line.coords:
            node_id = self._create_node(x, y)
            nodes.append(node_id)
        return nodes
    
    def node(self, n):
        """First pass: just collect nodes in our area"""
        if not self.first_pass:
            return
            
        if (self.min_lat <= n.location.lat <= self.max_lat and 
            self.min_lon <= n.location.lon <= self.max_lon):
            self.nodes_in_area.add(n.id)
            self.nodes[n.id] = {
                'lon': n.location.lon,
                'lat': n.location.lat,
                'tags': {tag.k: tag.v for tag in n.tags}
            }
    
    def way(self, w):
        """Process ways that use our nodes"""
        if self.first_pass:
            return
            
        # Check if way uses any of our nodes
        way_nodes = set(n.ref for n in w.nodes)
        if not (way_nodes & self.nodes_in_area):  # Intersection of sets
            self.unmodified_ways[w.id] = {
                'nodes': [n.ref for n in w.nodes],
                'tags': {t.k: t.v for t in w.tags}
            }
            return

        # It's a way we care about, check if it's a type we want to modify
        highway_tag = None
        for tag in w.tags:
            if tag.k == 'highway':
                highway_tag = tag.v
                break

        if not highway_tag:
            return

        modifiable_types = {
            'footway', 'pedestrian', 'path', 'steps', 'corridor',
            'residential', 'service', 'living_street', 'unclassified',
            'primary', 'secondary', 'tertiary',
            'primary_link', 'secondary_link', 'tertiary_link'
        }

        if highway_tag not in modifiable_types:
            self.unmodified_ways[w.id] = {
                'nodes': [n.ref for n in w.nodes],
                'tags': {t.k: t.v for t in w.tags}
            }
            return

        # Process the way for modifications
        # ... rest of way processing ...
    
    def write_modified_pbf(self, output_path):
        """Write modified network while preserving unmodified areas"""
        logger.info("Writing modified network...")
        writer = osmium.SimpleWriter(output_path)
        
        # Write all nodes
        logger.info(f"Writing {len(self.nodes) + len(self.new_nodes):,} nodes...")
        
        # Original nodes
        for node_id, node in self.nodes.items():
            writer.add_node(
                osmium.osm.mutable.Node(
                    id=node_id,
                    location=osmium.osm.Location(node['lon'], node['lat']),
                    tags=node['tags']
                )
            )
        
        # New intersection nodes
        for node_id, node in self.new_nodes.items():
            writer.add_node(
                osmium.osm.mutable.Node(
                    id=node_id,
                    location=osmium.osm.Location(node['lon'], node['lat']),
                    tags=node['tags']
                )
            )
        
        # Write modified ways
        logger.info(f"Writing {len(self.ways_to_modify):,} modified ways...")
        for way_id, way in self.ways_to_modify.items():
            writer.add_way(
                osmium.osm.mutable.Way(
                    id=way_id,
                    nodes=way['nodes'],
                    tags=way['tags']
                )
            )
        
        # Write unmodified ways
        logger.info(f"Writing {len(self.unmodified_ways):,} unmodified ways...")
        for way_id, way in self.unmodified_ways.items():
            writer.add_way(
                osmium.osm.mutable.Way(
                    id=way_id,
                    nodes=way['nodes'],
                    tags=way['tags']
                )
            )
        
        writer.close()
        
        # Verify file size
        output_size = os.path.getsize(output_path) / (1024 * 1024)  # Size in MB
        logger.info(f"Output file size: {output_size:.1f} MB")
        
        if output_size < 10:  # Arbitrary threshold
            logger.warning("Output file seems unusually small! Something might be wrong.")

def modify_otp_network(otp_dir, poi_polygons):
    """Modify OSM network with two passes"""
    logger.info("Starting network modification...")
    
    graphs_dir = os.path.join(otp_dir, 'graphs')
    if not os.path.exists(graphs_dir):
        raise ValueError(f"Graphs directory not found: {graphs_dir}")
    
    osm_file = 'israel-and-palestine-latest.osm.pbf'
    osm_path = os.path.join(graphs_dir, osm_file)
    
    if not os.path.exists(osm_path):
        raise ValueError(f"OSM file not found: {osm_path}")
    
    # Create backup if needed
    backup_path = osm_path + '.backup'
    if not os.path.exists(backup_path):
        logger.info(f"Creating backup: {backup_path}")
        import shutil
        shutil.copy2(osm_path, backup_path)
    
    # Process network
    handler = OSMAccessHandler(poi_polygons)
    
    # First pass: collect nodes
    logger.info("First pass: collecting nodes...")
    handler.apply_file(osm_path)
    
    # Switch to second pass
    handler.first_pass = False
    logger.info(f"Found {len(handler.nodes_in_area)} nodes in area")
    
    # Second pass: process ways
    logger.info("Second pass: processing ways...")
    handler.apply_file(osm_path)
    
    # Write modified network
    temp_path = osm_path + '.temp.osm.pbf'
    handler.write_modified_pbf(temp_path)
    
    # Verify file size before replacing
    original_size = os.path.getsize(osm_path) / (1024 * 1024)
    temp_size = os.path.getsize(temp_path) / (1024 * 1024)
    
    if temp_size < original_size * 0.5:  # If new file is less than 50% of original
        raise ValueError(
            f"New file ({temp_size:.1f} MB) is much smaller than original ({original_size:.1f} MB). "
            "Aborting to prevent data loss."
        )
    
    # Replace original
    os.replace(temp_path, osm_path)
    logger.info(f"Successfully modified network: {osm_path}")
    logger.info("Restart OTP server for changes to take effect")

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
    
    # Modify network
    modify_otp_network(
        "/Users/noamgal/Downloads/NUR/otp_project",
        poi_polygons
    )