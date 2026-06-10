import re
import pandas as pd

# Zone format definitions
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

def clean_zone_id(zone_id):
    """
    Clean and standardize zone ID format
    Args:
        zone_id: Raw zone ID (can be string, int, or float)
    Returns:
        Cleaned zone ID string in proper format
    """
    if pd.isna(zone_id):
        return '00000000'
        
    # Convert to string and remove any decimals
    zone_str = str(zone_id).split('.')[0].strip()
    
    # Handle city zones (starting with C)
    if zone_str.upper().startswith('C'):
        digits = ''.join(filter(str.isdigit, zone_str))
        return f"C{digits.zfill(7)}"
    
    # Handle POI zones (must match exactly 000000XX pattern)
    digits = ''.join(filter(str.isdigit, zone_str))
    if len(digits) <= 2 and zone_str.startswith('0'):
        return f"000000{digits.zfill(2)}"
    
    # Handle statistical zones (8 digits)
    if len(digits) <= 8:
        return digits.zfill(8)
    
    raise ValueError(f"Invalid zone ID format: {zone_id}")

def is_valid_zone_id(zone_id):
    """Check if a single zone ID is valid"""
    if pd.isna(zone_id):
        return False
        
    zone_str = str(zone_id).strip()
    
    # Check city format first (more specific check)
    if zone_str.startswith('C'):
        return bool(re.match(r'^C\d{7}$', zone_str))
    
    # Check other formats
    for format_type, format_spec in ZONE_FORMATS.items():
        if re.match(format_spec['pattern'], zone_str):
            return True
    
    return False

def get_zone_type(zone_id):
    """
    Determine the type of zone from its ID
    Args:
        zone_id: Zone ID to check
    Returns:
        str: 'city', 'statistical', 'poi', or 'unknown'
    """
    if pd.isna(zone_id):
        return 'unknown'
        
    zone_str = str(zone_id)
    
    if zone_str.startswith('C'):
        return 'city'
    elif re.match(r'^000000\d{2}$', zone_str):  # Strict POI pattern
        return 'poi'
    elif len(zone_str) == 8 and zone_str.isdigit():
        return 'statistical'
    else:
        return 'unknown'

def standardize_zone_ids(df, columns):
    """
    Standardize zone IDs in specified columns of a DataFrame
    Args:
        df: pandas DataFrame
        columns: list of column names containing zone IDs
    Returns:
        DataFrame with standardized zone IDs
    """
    df = df.copy()
    for col in columns:
        # Convert column to string type first
        df[col] = df[col].astype(str)
        df[col] = df[col].apply(clean_zone_id)
    return df

def analyze_zone_ids(df, columns):
    """Analyze zone IDs in a DataFrame and return statistics"""
    results = {
        'city': 0,
        'statistical': 0,
        'poi': 0,
        'unknown': 0,
        'invalid': []
    }
    
    for col in columns:
        for zone_id in df[col].unique():
            zone_type = get_zone_type(zone_id)
            results[zone_type] += 1
            
            if zone_type == 'unknown':
                results['invalid'].append(zone_id)
    
    return results 