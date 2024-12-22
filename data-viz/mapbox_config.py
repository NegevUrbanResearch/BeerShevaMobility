# mapbox_config.py

import os
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

class MapboxConfig:
    def __init__(self):
        self.api_key = None
        self.config_file = Path(__file__).parent / 'mapbox_config.json'
        self.load_config()

    def load_config(self):
        """Load Mapbox configuration from environment variable or config file"""
        # First try environment variable
        self.api_key = os.environ.get('MAPBOX_API_KEY')
        
        if not self.api_key:
            try:
                if self.config_file.exists():
                    with open(self.config_file, 'r') as f:
                        config = json.load(f)
                        self.api_key = config.get('api_key')
            except Exception as e:
                logger.error(f"Error loading config file: {e}")

        if not self.api_key:
            raise ValueError("Mapbox API key not found in environment or config file")

    def save_config(self, api_key):
        """Save Mapbox configuration to config file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump({'api_key': api_key}, f, indent=2)
            self.api_key = api_key
            logger.info("Mapbox configuration saved successfully")
        except Exception as e:
            logger.error(f"Error saving config file: {e}")
            raise

    def get_api_key(self):
        """Get the Mapbox API key"""
        if not self.api_key:
            self.load_config()
        return self.api_key

    def validate_api_key(self):
        """Validate that the API key exists and has the correct format"""
        if not self.api_key:
            return False
        
        # Basic validation - check if it starts with 'pk.' for public key
        if not self.api_key.startswith('pk.'):
            logger.error("Invalid Mapbox API key format")
            return False
            
        return True