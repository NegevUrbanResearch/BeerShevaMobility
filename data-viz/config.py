import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration and constants
# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PROCESSED_DIR = os.path.join(DATA_DIR, 'processed')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output', 'dashboard_data')

# Input files (raw data)
RAW_ZONES_FILE = os.path.join(DATA_DIR, 'statisticalareas_demography2019.gdb')
RAW_TRIPS_FILE = os.path.join(DATA_DIR, 'All-Stages.xlsx')
POI_FILE = os.path.join(DATA_DIR, "poi_with_exact_coordinates.csv")

# Intermediate processed files
ZONES_WITH_CITIES_FILE = os.path.join(PROCESSED_DIR, 'zones_with_cities.geojson')
TRIPS_WITH_CITIES_FILE = os.path.join(PROCESSED_DIR, 'trips_with_cities.xlsx')

# Final processed files (after preprocess_data.py)
FINAL_ZONES_FILE = os.path.join(OUTPUT_DIR, 'zones.geojson')
FINAL_TRIPS_PATTERN = os.path.join(OUTPUT_DIR, '*_trips.csv')

BUILDINGS_FILE = os.path.join(OUTPUT_DIR, 'buildings.geojson')

# Add temporal data paths
ROAD_USAGE_PATH = os.path.join(OUTPUT_DIR, 'road_usage_trips.geojson')

# Temporal distribution files
TEMPORAL_FILES = {
    'BGU': {
        'inbound': os.path.join(OUTPUT_DIR, 'ben_gurion_university_inbound_temporal.csv'),
        'outbound': os.path.join(OUTPUT_DIR, 'ben_gurion_university_outbound_temporal.csv')
    },
    'Gav Yam': {
        'inbound': os.path.join(OUTPUT_DIR, 'gav_yam_high_tech_park_inbound_temporal.csv'),
        'outbound': os.path.join(OUTPUT_DIR, 'gav_yam_high_tech_park_outbound_temporal.csv')
    },
    'Soroka Hospital': {
        'inbound': os.path.join(OUTPUT_DIR, 'soroka_medical_center_inbound_temporal.csv'),
        'outbound': os.path.join(OUTPUT_DIR, 'soroka_medical_center_outbound_temporal.csv')
    }
}

# POI name standardization
POI_NAME_MAPPING = {
    'BGU': ['BGU', 'Ben-Gurion-University', 'ben_gurion_university'],
    'Gav Yam': ['Gav Yam', 'Gev Yam', 'Gav-Yam-High-Tech-Park', 'gav_yam_high_tech_park'],
    'Soroka Hospital': ['Soroka Hospital', 'Soroka-Medical-Center', 'soroka_medical_center']
}

# Create directories if they don't exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Color scheme
COLOR_SCHEME = {
    'background': '#222222',
    'text': '#FFFFFF',
    'primary': '#007BFF',
    'secondary': '#6C757D',
    'success': '#28A745',
    'danger': '#DC3545',
    'warning': '#FFC107',
    'info': '#17A2B8'
}

# Chart colors
CHART_COLORS = ['#007BFF', '#DC3545', '#28A745', '#FFC107', '#17A2B8', '#6C757D']

# Your public Mapbox API key
MAPBOX_API_KEY = os.getenv('MAPBOX_API_KEY', 'your_sample_api_key_here')

# POI Coordinates
POI_LOCATIONS = [
    {"name": "Emek Shara industrial area", "lat": 31.2271875, "lon": 34.8090625},
    {"name": "BGU", "lat": 31.2614375, "lon": 34.7995625},
    {"name": "Soroka Hospital", "lat": 31.2579375, "lon": 34.8003125},
    {"name": "Yes Planet", "lat": 31.2244375, "lon": 34.8010625},
    {"name": "Grand Kenyon", "lat": 31.2506875, "lon": 34.7716875},
    {"name": "Omer industrial area", "lat": 31.2703125, "lon": 34.8364375},
    {"name": "K collage", "lat": 31.2698125, "lon": 34.7815625},
    {"name": "HaNegev Mall", "lat": 31.2436875, "lon": 34.7949375},
    {"name": "BIG", "lat": 31.2443125, "lon": 34.8114375},
    {"name": "Assuta Hospital", "lat": 31.2451875, "lon": 34.7964375},
    {"name": "Gev Yam", "lat": 31.2641875, "lon": 34.8128125},
    {"name": "Ramat Hovav Industry", "lat": 31.1361875, "lon": 34.7898125},
    {"name": "Sami Shimon collage", "lat": 31.2499375, "lon": 34.7893125}
]

# Constants for visualization
POI_RADIUS = 50  # meters
