from typing import List, Dict
import pandas as pd
import logging
from .data_standards import DataStandardizer

logger = logging.getLogger(__name__)

class DataValidator:
    def __init__(self):
        self.standardizer = DataStandardizer()

    def validate_data_completeness(
        self,
        df: pd.DataFrame,
        required_columns: List[str]
    ) -> List[str]:
        """Validate presence of required columns"""
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"Missing required columns: {missing_columns}")
            raise ValueError(f"Missing required columns: {missing_columns}")
        return missing_columns

    def validate_zone_ids(
        self,
        df: pd.DataFrame,
        zone_columns: List[str]
    ) -> Dict[str, List[str]]:
        """Validate zone IDs across multiple columns"""
        invalid_ids = {}
        for col in zone_columns:
            invalid = []
            for zone_id in df[col].unique():
                zone_type = self.standardizer.get_zone_type(zone_id)
                if zone_type == 'unknown':
                    invalid.append(zone_id)
            if invalid:
                invalid_ids[col] = invalid
                logger.warning(f"Invalid zone IDs in {col}: {invalid[:5]}")
        return invalid_ids

    def validate_poi_names(
        self,
        names: List[str],
        valid_pois: List[str]
    ) -> List[str]:
        """Validate POI names against known valid POIs"""
        invalid_names = []
        for name in names:
            standardized = self.standardizer.standardize_poi_name(name)
            if standardized not in valid_pois:
                invalid_names.append(name)
                logger.warning(f"Invalid POI name: {name}")
        return invalid_names 