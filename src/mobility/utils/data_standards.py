from typing import Dict, Optional
import pandas as pd
import re
import logging

logger = logging.getLogger(__name__)

class DataStandardizer:
    # Zone format definitions from zone_utils.py
    ZONE_FORMATS = {
        'city': {
            'prefix': 'C',
            'digits': 7,
            'pattern': r'^C\d{7}$',
            'example': 'C0123456'
        },
        'statistical': {
            'prefix': '',
            'digits': 8,
            'pattern': r'^\d{8}$',
            'example': '12345678'
        },
        'poi': {
            'prefix': '0',
            'digits': 8,
            'pattern': r'^0{6}\d{2}$',
            'example': '00000001'
        }
    }

    POI_NAME_MAPPING = {
        # Full names with hyphens for word separation
        'Emek Shara industrial area': 'Emek-Sara-Industrial-Area',
        'BGU': 'Ben-Gurion-University',
        'Soroka Hospital': 'Soroka-Medical-Center',
        'Yes Planet': 'Yes-Planet',
        'Grand Kenyon': 'Grand-Kenyon',
        'Omer industrial area': 'Omer-Industrial-Area',
        'K collage': 'Kaye-College',
        'HaNegev Mall': 'HaNegev-Mall',
        'BIG': 'BIG',  # Single word remains as-is
        'Assuta Hospital': 'Assuta-Hospital',
        'Gev Yam': 'Gav-Yam-High-Tech-Park',
        'Ramat Hovav Industry': 'Ramat-Hovav-Industrial-Zone',
        'Sami Shimon collage': 'SCE',  # Acronym remains as-is
        
        # Common variations
        'K': 'Kaye-College',
        'Kaye': 'Kaye-College',
        'Ben Gurion': 'Ben-Gurion-University',
        'Ben_Gurion': 'Ben-Gurion-University',
        'Emek Sara': 'Emek-Sara-Industrial-Area',
        'Gav Yam': 'Gav-Yam-High-Tech-Park',
        'Gev-Yam': 'Gav-Yam-High-Tech-Park',
        'HaNegev': 'HaNegev-Mall',
        'Soroka': 'Soroka-Medical-Center',
        'Assuta': 'Assuta-Hospital',
        'Omer': 'Omer-Industrial-Area',
        'Ramat Hovav': 'Ramat-Hovav-Industrial-Zone',
        'Sami Shimon': 'SCE'
    }

    @classmethod
    def standardize_zone_id(cls, zone_id: str) -> str:
        """Standardize zone ID format"""
        if pd.isna(zone_id):
            return '00000000'
            
        zone_str = str(zone_id).split('.')[0].strip()
        
        if zone_str.upper().startswith('C'):
            digits = ''.join(filter(str.isdigit, zone_str))
            return f"C{digits.zfill(7)}"
        
        digits = ''.join(filter(str.isdigit, zone_str))
        if len(digits) <= 2 and zone_str.startswith('0'):
            return f"000000{digits.zfill(2)}"
        
        if len(digits) <= 8:
            return digits.zfill(8)
        
        raise ValueError(f"Invalid zone ID format: {zone_id}")

    @classmethod
    def standardize_poi_name(cls, name: str) -> str:
        """
        Standardize POI name with comprehensive matching strategy.
        Uses hyphens for word separation in POI names.
        """
        if pd.isna(name):
            return None
            
        # Clean the input name
        clean_name = str(name).strip()
        
        # Try various matching strategies
        test_variants = [
            clean_name,  # Original
            clean_name.replace(' ', '-'),  # With hyphens
            clean_name.replace('_', '-'),  # Convert underscores to hyphens
            clean_name.split('(')[0].strip(),  # Remove parenthetical
            clean_name.split()[0]  # First word only
        ]
        
        # Try each variant against both keys and values
        for variant in test_variants:
            # Direct mapping
            if variant in cls.POI_NAME_MAPPING:
                return cls.POI_NAME_MAPPING[variant]
            
            # Case-insensitive mapping
            for key, value in cls.POI_NAME_MAPPING.items():
                if variant.lower() == key.lower():
                    return value
                if variant.lower() == value.lower():
                    return value
        
        # If no match found, standardize with hyphens
        logger.warning(f"No standard mapping found for POI name: {name}")
        return clean_name.replace(' ', '-').replace('_', '-')

    @classmethod
    def extract_poi_name_from_filename(cls, filename: str) -> tuple[str, str]:
        """
        Extract and standardize POI name and trip type from filename.
        Example: 'BGU_outbound_trips.csv' -> ('Ben-Gurion-University', 'outbound')
        """
        # Remove file extension and _trips suffix
        base_name = filename.replace('.csv', '').replace('_trips', '')
        
        # Split on underscores to separate POI name from trip type
        parts = base_name.split('_')
        if len(parts) < 2:
            return None, None
            
        # Last part should be trip type
        trip_type = parts[-1] if parts[-1] in ['inbound', 'outbound'] else None
        if not trip_type:
            return None, None
            
        # Join remaining parts with spaces and standardize
        poi_parts = parts[:-1]
        raw_poi_name = ' '.join(poi_parts)
        standardized_poi = cls.standardize_poi_name(raw_poi_name)
        
        return standardized_poi, trip_type

    @classmethod
    def get_zone_type(cls, zone_id: str) -> str:
        """Determine zone type from ID"""
        if pd.isna(zone_id):
            return 'unknown'
            
        zone_str = str(zone_id)
        
        if zone_str.startswith('C'):
            return 'city'
        elif re.match(r'^000000\d{2}$', zone_str):
            return 'poi'
        elif len(zone_str) == 8 and zone_str.isdigit():
            return 'statistical'
        else:
            return 'unknown'

    @classmethod
    def get_all_standard_poi_names(cls) -> set:
        """Return all standardized POI names"""
        return set(cls.POI_NAME_MAPPING.values())
