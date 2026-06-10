import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT

DATA_DIR = REPO_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
SPATIAL_DIR = REPO_ROOT / "shapes" / "data"
SPATIAL_OUTPUT_DIR = SPATIAL_DIR / "output"
MODEL_OUTLINE_DIR = DATA_DIR / "model_outline"

OUTPUT_ROOT = REPO_ROOT / "output"
OUTPUT_DIR = OUTPUT_ROOT / "dashboard_data"
STATS_DIR = OUTPUT_ROOT / "statistics"

RAW_ZONES_FILE = DATA_DIR / "statisticalareas_demography2019.gdb"
RAW_TRIPS_FILE = DATA_DIR / "All-Stages.xlsx"
POI_FILE = DATA_DIR / "poi_with_exact_coordinates.csv"

ZONES_WITH_CITIES_FILE = PROCESSED_DIR / "zones_with_cities.geojson"
TRIPS_WITH_CITIES_FILE = PROCESSED_DIR / "trips_with_cities.xlsx"

FINAL_ZONES_FILE = OUTPUT_DIR / "zones.geojson"
FINAL_TRIPS_PATTERN = str(OUTPUT_DIR / "*_trips.csv")
BUILDINGS_FILE = OUTPUT_DIR / "buildings.geojson"
ROAD_USAGE_PATH = OUTPUT_DIR / "road_usage_trips.geojson"

TEMPORAL_FILES = {
    "BGU": {
        "inbound": OUTPUT_DIR / "ben_gurion_university_inbound_temporal.csv",
        "outbound": OUTPUT_DIR / "ben_gurion_university_outbound_temporal.csv",
    },
    "Gav Yam": {
        "inbound": OUTPUT_DIR / "gav_yam_high_tech_park_inbound_temporal.csv",
        "outbound": OUTPUT_DIR / "gav_yam_high_tech_park_outbound_temporal.csv",
    },
    "Soroka Hospital": {
        "inbound": OUTPUT_DIR / "soroka_medical_center_inbound_temporal.csv",
        "outbound": OUTPUT_DIR / "soroka_medical_center_outbound_temporal.csv",
    },
}

POI_NAME_MAPPING = {
    "BGU": ["BGU", "Ben-Gurion-University", "ben_gurion_university"],
    "Gav Yam": ["Gav Yam", "Gev Yam", "Gav-Yam-High-Tech-Park", "gav_yam_high_tech_park"],
    "Soroka Hospital": ["Soroka Hospital", "Soroka-Medical-Center", "soroka_medical_center"],
}

COLOR_SCHEME = {
    "background": "#222222",
    "text": "#FFFFFF",
    "primary": "#007BFF",
    "secondary": "#6C757D",
    "success": "#28A745",
    "danger": "#DC3545",
    "warning": "#FFC107",
    "info": "#17A2B8",
}

CHART_COLORS = ["#007BFF", "#DC3545", "#28A745", "#FFC107", "#17A2B8", "#6C757D"]
MAPBOX_API_KEY = os.getenv("MAPBOX_API_KEY", "your_sample_api_key_here")

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
    {"name": "Sami Shimon collage", "lat": 31.2499375, "lon": 34.7893125},
]

POI_RADIUS = 50

ATTRACTION_CENTERS_SHP = SPATIAL_DIR / "maps" / "Be'er_Sheva_Shapefiles_Attraction_Centers.shp"
FILTERED_ENTRANCES_SHP = DATA_DIR / "filtered-entrances" / "filtered_entrances.shp"
GOOGLE_POINTS_SHP = SPATIAL_OUTPUT_DIR / "google_points.shp"
AMENITIES_BUFFER_SHP = SPATIAL_OUTPUT_DIR / "points_within_buffer.shp"

for path in (DATA_DIR, PROCESSED_DIR, OUTPUT_DIR, OUTPUT_ROOT, STATS_DIR, SPATIAL_OUTPUT_DIR):
    path.mkdir(parents=True, exist_ok=True)
