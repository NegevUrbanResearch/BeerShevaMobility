import osmium
import geopandas as gpd
import logging
import os
import time

logger = logging.getLogger(__name__)

class OSMAccessHandler(osmium.SimpleHandler):
    def __init__(self, poi_polygons):
        super().__init__()
        
        # Get bounds with buffer
        bounds = poi_polygons.total_bounds
        buffer_size = 500 / 111000  # 500m buffer in degrees
        
        # Store target bounds (Beer Sheva area)
        self.min_lat = bounds[1] - buffer_size
        self.max_lat = bounds[3] + buffer_size
        self.min_lon = bounds[0] - buffer_size
        self.max_lon = bounds[2] + buffer_size
        
        # Wider search area (all of Beer Sheva)
        self.search_min_lat = 31.20  # South Beer Sheva
        self.search_max_lat = 31.30  # North Beer Sheva
        self.search_min_lon = 34.75  # West Beer Sheva
        self.search_max_lon = 34.85  # East Beer Sheva
        
        logger.info(f"Target bounds (with 500m buffer):")
        logger.info(f"  Latitude:  {self.min_lat:.6f} to {self.max_lat:.6f}")
        logger.info(f"  Longitude: {self.min_lon:.6f} to {self.max_lon:.6f}")
        
        # Stats
        self.total_ways = 0
        self.nodes_checked = 0
        self.ways_in_bounds = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.debug_count = 0
        
    def node(self, n):
        """Sample nodes in wider Beer Sheva area"""
        if self.debug_count >= 20:  # Limit debug output
            return
            
        if n.location.valid():
            lat = n.location.lat
            lon = n.location.lon
            
            # Check if in wider Beer Sheva area
            if (self.search_min_lat <= lat <= self.search_max_lat and 
                self.search_min_lon <= lon <= self.search_max_lon):
                
                # Check if in target bounds
                in_bounds = (self.min_lat <= lat <= self.max_lat and 
                           self.min_lon <= lon <= self.max_lon)
                
                logger.info(f"Found Beer Sheva area node: {lat:.6f}°N, {lon:.6f}°E")
                logger.info(f"In target bounds: {in_bounds}")
                logger.info("Bounds check details:")
                logger.info(f"  Latitude {self.min_lat:.6f} <= {lat:.6f} <= {self.max_lat:.6f}: {self.min_lat <= lat <= self.max_lat}")
                logger.info(f"  Longitude {self.min_lon:.6f} <= {lon:.6f} <= {self.max_lon:.6f}: {self.min_lon <= lon <= self.max_lon}")
                
                self.debug_count += 1
    
    def way(self, w):
        """Process ways with detailed debugging"""
        self.total_ways += 1
        
        if self.debug_count >= 20:  # Limit debug output
            return
            
        # Check nodes in way
        for n in w.nodes:
            if n.location.valid():
                lat = n.location.lat
                lon = n.location.lon
                
                # Check if in wider Beer Sheva area
                if (self.search_min_lat <= lat <= self.search_max_lat and 
                    self.search_min_lon <= lon <= self.search_max_lon):
                    
                    # Check if in target bounds
                    in_bounds = (self.min_lat <= lat <= self.max_lat and 
                               self.min_lon <= lon <= self.max_lon)
                    
                    # Get way type if available
                    way_type = "unknown"
                    for tag in w.tags:
                        if tag.k == 'highway':
                            way_type = tag.v
                            break
                    
                    logger.info(f"Found Beer Sheva area way {w.id} ({way_type}):")
                    logger.info(f"  Node: {lat:.6f}°N, {lon:.6f}°E")
                    logger.info(f"  In target bounds: {in_bounds}")
                    self.debug_count += 1
                    break
        
        # Progress update every 5 seconds
        current_time = time.time()
        if current_time - self.last_update > 5:
            elapsed = current_time - self.start_time
            rate = self.total_ways / elapsed if elapsed > 0 else 0
            logger.info(
                f"Processed {self.total_ways:,} ways ({rate:.0f} ways/sec) - "
                f"Debug count: {self.debug_count}"
            )
            self.last_update = current_time

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logger.info("Starting script...")
    
    # Load POI polygons
    logger.info("Loading POI polygons...")
    attractions = gpd.read_file("shapes/data/maps/Be'er_Sheva_Shapefiles_Attraction_Centers.shp")
    logger.info(f"Original CRS: {attractions.crs}")
    
    # Filter for BGU and Soroka
    poi_polygons = attractions[attractions['ID'].isin([11, 7])]
    logger.info(f"Loaded {len(poi_polygons)} POI polygons")
    
    for _, poi in poi_polygons.iterrows():
        centroid = poi.geometry.centroid
        logger.info(f"POI {poi['ID']} centroid: {centroid.y:.6f}°N, {centroid.x:.6f}°E")
    
    # Initialize handler and process file
    handler = OSMAccessHandler(poi_polygons)
    osm_path = "/Users/noamgal/Downloads/NUR/otp_project/graphs/israel-and-palestine-latest.osm.pbf"
    
    logger.info("Processing OSM file...")
    handler.apply_file(osm_path)