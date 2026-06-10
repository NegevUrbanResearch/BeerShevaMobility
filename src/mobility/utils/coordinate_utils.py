import numpy as np
import logging

logger = logging.getLogger(__name__)

class CoordinateValidator:
    # ITM (EPSG:2039) bounds for Israel
    ITM_BOUNDS = {
        'x': {'min': 120000, 'max': 280000},  # East-West
        'y': {'min': 380000, 'max': 780000}   # North-South
    }
    
    # WGS84 (EPSG:4326) bounds for Israel
    WGS84_BOUNDS = {
        'lat': {'min': 29.5, 'max': 33.3},
        'lon': {'min': 34.2, 'max': 35.9}
    }
    
    # Beer Sheva region bounds - kept for reference but not used for clipping
    BEER_SHEVA_BOUNDS = {
        'lat': {'min': 31.15, 'max': 31.35},
        'lon': {'min': 34.70, 'max': 34.90}
    }
    
    @staticmethod
    def validate_itm(x, y):
        """Validate and adjust ITM coordinates"""
        valid = True
        original_x, original_y = x, y
        
        if not (CoordinateValidator.ITM_BOUNDS['x']['min'] <= x <= CoordinateValidator.ITM_BOUNDS['x']['max']):
            x = np.clip(x, CoordinateValidator.ITM_BOUNDS['x']['min'], CoordinateValidator.ITM_BOUNDS['x']['max'])
            valid = False
            
        if not (CoordinateValidator.ITM_BOUNDS['y']['min'] <= y <= CoordinateValidator.ITM_BOUNDS['y']['max']):
            y = np.clip(y, CoordinateValidator.ITM_BOUNDS['y']['min'], CoordinateValidator.ITM_BOUNDS['y']['max'])
            valid = False
            
        if not valid:
            logger.warning(
                f"ITM coordinates adjusted: ({original_x}, {original_y}) -> ({x}, {y})"
            )
            
        return x, y, valid
    
    @staticmethod
    def validate_wgs84(lat, lon, use_beer_sheva_bounds=False):
        """Validate and adjust WGS84 coordinates"""
        bounds = CoordinateValidator.WGS84_BOUNDS
        valid = True
        original_lat, original_lon = lat, lon
        
        if not (bounds['lat']['min'] <= lat <= bounds['lat']['max']):
            lat = np.clip(lat, bounds['lat']['min'], bounds['lat']['max'])
            valid = False
            
        if not (bounds['lon']['min'] <= lon <= bounds['lon']['max']):
            lon = np.clip(lon, bounds['lon']['min'], bounds['lon']['max'])
            valid = False
            
        if not valid:
            logger.warning(
                f"WGS84 coordinates adjusted: ({original_lat}, {original_lon}) -> ({lat}, {lon})"
            )
            
        return lat, lon, valid 