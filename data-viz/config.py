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
