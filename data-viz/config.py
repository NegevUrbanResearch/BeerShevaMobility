import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration and constants
# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output', 'dashboard_data')

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
