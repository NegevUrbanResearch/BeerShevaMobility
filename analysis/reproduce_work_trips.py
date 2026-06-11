#!/usr/bin/env python3
"""Reproduce inbound dashboard exports filtered to work-purpose trips only."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import time
from pathlib import Path

import geopandas as gpd
import geopy.distance
import numpy as np
import pandas as pd

from mobility.config import OUTPUT_DIR, OUTPUT_ROOT, RAW_TRIPS_FILE, REPO_ROOT
from mobility.utils.data_standards import DataStandardizer
from mobility.utils.work_trip_filter import filter_to_work_trips
from mobility.utils.zone_utils import clean_zone_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORK_OUTPUT_DIR = OUTPUT_ROOT / "working_trips"
REPRODUCE_INBOUND_DIR = REPO_ROOT / "reproduce_inbound"

POI_TRIP_FILES = {
    "BGU": "BGU",
    "Soroka Hospital": "Soroka_Hospital",
    "Gav Yam": "Gev_Yam",
}

POI_RAW_NAMES = {
    "BGU": "BGU",
    "Soroka Hospital": "Soroka Hospital",
    "Gav Yam": "Gev Yam",
}

POI_COORDS = {
    "BGU": {"lat": 31.262218, "lon": 34.801472},
    "Soroka_Hospital": {"lat": 31.262650, "lon": 34.799452},
    "Gev_Yam": {"lat": 31.263500, "lon": 34.803500},
}

DISTANCE_RANGES = {
    "walk": [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, float("inf"))],
    "bike": [(0, 1), (1, 2), (2, 3), (3, 5), (5, float("inf"))],
    "car": [(0, 10), (10, 25), (25, 50), (50, 75), (75, float("inf"))],
    "transit": [(0, 10), (10, 25), (25, 50), (50, 75), (75, float("inf"))],
}

MODE_DISPLAY = {
    "bus": "Public Transit",
    "car": "Car",
    "link": "Shared Mobility",
    "train": "Train",
    "ped": "Walking",
    "bike": "Bike",
}

DISTANCE_MODE_DISPLAY = {
    "walk": "Walking",
    "bike": "Bike",
    "car": "Car",
    "transit": "Public Transit",
}


def load_work_poi_trips(file_stem: str, trip_type: str = "inbound") -> pd.DataFrame:
    path = OUTPUT_DIR / f"{file_stem}_{trip_type}_trips.csv"
    df = pd.read_csv(path)
    return filter_to_work_trips(df)


def clean_mode_name(mode_raw: str) -> str:
    mode_clean = mode_raw.replace("mode_", "").replace("_", " ").title()
    return MODE_DISPLAY.get(mode_clean.lower().replace(" ", "_"), mode_clean)


def generate_mode_split() -> pd.DataFrame:
    rows = []
    for destination, file_stem in POI_TRIP_FILES.items():
        df = load_work_poi_trips(file_stem)
        mode_cols = [col for col in df.columns if col.startswith("mode_")]
        total = df["total_trips"].sum()
        if total <= 0:
            continue
        for col in mode_cols:
            mode_trips = (df[col] / 100 * df["total_trips"]).sum()
            rows.append(
                {
                    "destination": destination,
                    "mode": clean_mode_name(col),
                    "percentage": round(mode_trips / total * 100, 2),
                    "trips": round(mode_trips, 1),
                }
            )
    return pd.DataFrame(rows)


def load_raw_work_trips() -> pd.DataFrame:
    df = pd.read_excel(RAW_TRIPS_FILE, sheet_name="StageB1")
    df = df[df["purpose"].str.strip() == "Work"].copy()
    df["hour"] = df["time_bin"].apply(lambda value: value.hour if isinstance(value, time) else 0)
    return df


def generate_temporal() -> pd.DataFrame:
    raw_trips = load_raw_work_trips()
    rows = []

    for destination, raw_name in POI_RAW_NAMES.items():
        poi_trips = raw_trips[raw_trips["to_name"] == raw_name]
        hourly = poi_trips.groupby("hour")["count"].sum()
        total = hourly.sum()
        for hour in range(24):
            proportion = float(hourly.get(hour, 0)) / total if total > 0 else 0.0
            rows.append(
                {
                    "destination": destination,
                    "hour": hour,
                    "proportion": round(proportion, 6),
                }
            )
    return pd.DataFrame(rows)


def prepare_distance_frame(poi_key: str) -> pd.DataFrame | None:
    df = load_work_poi_trips(poi_key)
    zones = gpd.read_file(OUTPUT_DIR / "zones.geojson")
    zones = zones.set_crs(epsg=2039, allow_override=True)
    centroids = zones.to_crs(epsg=4326).geometry.centroid
    zones = zones.assign(centroid_lat=centroids.y, centroid_lon=centroids.x)
    df = df.merge(
        zones[["YISHUV_STAT11", "centroid_lon", "centroid_lat"]],
        left_on="tract",
        right_on="YISHUV_STAT11",
        how="left",
    )

    poi_coords = POI_COORDS[poi_key]
    df["distance"] = df.apply(
        lambda row: geopy.distance.geodesic(
            (poi_coords["lat"], poi_coords["lon"]),
            (row["centroid_lat"], row["centroid_lon"]),
        ).kilometers
        if pd.notna(row["centroid_lat"])
        else np.nan,
        axis=1,
    )

    if "mode_ped" in df.columns:
        df["mode_walk"] = df["mode_ped"]
    transit_cols = [col for col in ["mode_bus", "mode_link", "mode_train"] if col in df.columns]
    if transit_cols:
        df["mode_transit"] = df[transit_cols].sum(axis=1)
    return df


def calculate_distance_distribution(df: pd.DataFrame, mode: str) -> list[dict]:
    mode_col = f"mode_{mode}"
    mode_trips = df[mode_col] / 100 * df["total_trips"]
    distribution = []
    for start, end in DISTANCE_RANGES[mode]:
        mask = df["distance"] >= start
        if end != float("inf"):
            mask &= df["distance"] < end
        trips = float(mode_trips[mask].sum())
        range_label = f"{start}-{end}" if end != float("inf") else f">{start}"
        distribution.append({"range": range_label, "trips": trips})
    return distribution


def generate_distance_histogram() -> pd.DataFrame:
    poi_display = {
        "BGU": "BGU",
        "Soroka_Hospital": "Soroka Hospital",
        "Gev_Yam": "Gav Yam",
    }
    rows = []
    for poi_key, destination in poi_display.items():
        df = prepare_distance_frame(poi_key)
        if df is None:
            continue
        for mode in DISTANCE_RANGES:
            for range_data in calculate_distance_distribution(df, mode):
                rows.append(
                    {
                        "destination": destination,
                        "mode": DISTANCE_MODE_DISPLAY[mode],
                        "distance_range": range_data["range"],
                        "trips": round(range_data["trips"], 1),
                    }
                )
    return pd.DataFrame(rows)


def generate_consolidated_csv(
    mode_df: pd.DataFrame,
    temporal_df: pd.DataFrame,
    distance_df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, row in mode_df.iterrows():
        rows.append(
            {
                "data_type": "mode_split",
                "destination": row["destination"],
                "mode": row["mode"],
                "hour": None,
                "distance_range": None,
                "value": row["percentage"],
                "trips": row["trips"],
            }
        )
    for _, row in temporal_df.iterrows():
        rows.append(
            {
                "data_type": "temporal",
                "destination": row["destination"],
                "mode": None,
                "hour": row["hour"],
                "distance_range": None,
                "value": row["proportion"],
                "trips": None,
            }
        )
    for _, row in distance_df.iterrows():
        rows.append(
            {
                "data_type": "distance_histogram",
                "destination": row["destination"],
                "mode": row["mode"],
                "hour": None,
                "distance_range": row["distance_range"],
                "value": None,
                "trips": row["trips"],
            }
        )
    return pd.DataFrame(rows)


def load_city_analysis_data() -> pd.DataFrame:
    standardizer = DataStandardizer()
    innovation_district_pois = [
        "Ben-Gurion-University",
        "Soroka-Medical-Center",
        "Gav-Yam-High-Tech-Park",
    ]
    other_pois = [
        poi
        for poi in standardizer.get_all_standard_poi_names()
        if poi not in innovation_district_pois
    ]
    file_name_mapping = {
        "Ben-Gurion-University": "BGU",
        "Soroka-Medical-Center": "Soroka Hospital",
        "Gav-Yam-High-Tech-Park": "Gev Yam",
        "Emek-Sara-Industrial-Area": "Emek Shara industrial area",
        "Omer-Industrial-Area": "Omer industrial area",
        "HaNegev-Mall": "HaNegev Mall",
        "BIG": "BIG",
        "Assuta-Hospital": "Assuta Hospital",
        "SCE": "Sami Shimon collage",
        "Grand-Kenyon": "Grand Kenyon",
        "Yes-Planet": "Yes Planet",
        "Kaye-College": "K collage",
        "Ramat-Hovav-Industrial-Zone": "Ramat Hovav Industry",
    }

    zones = gpd.read_file(OUTPUT_DIR / "zones.geojson")
    all_data = []
    for poi in innovation_district_pois + other_pois:
        file_name = file_name_mapping.get(poi, poi).replace(" ", "_")
        for direction in ["inbound", "outbound"]:
            file_path = OUTPUT_DIR / f"{file_name}_{direction}_trips.csv"
            if not file_path.exists():
                continue
            df = filter_to_work_trips(pd.read_csv(file_path))
            df = df.merge(
                zones[["YISHUV_STAT11", "SHEM_YISHUV_ENGLISH"]],
                left_on="tract",
                right_on="YISHUV_STAT11",
                how="left",
            )
            df["poi"] = poi
            df["direction"] = direction
            all_data.append(df)
    return pd.concat(all_data, ignore_index=True)


def analyze_cities(df: pd.DataFrame) -> pd.DataFrame:
    innovation_district_pois = [
        "Ben-Gurion-University",
        "Soroka-Medical-Center",
        "Gav-Yam-High-Tech-Park",
    ]
    city_stats = []
    for city, city_data in df.groupby("SHEM_YISHUV_ENGLISH"):
        if pd.isna(city):
            continue
        total_trips = city_data["total_trips"].sum()
        poi_trips = city_data.groupby("poi")["total_trips"].sum()
        poi_shares = poi_trips / total_trips if total_trips > 0 else poi_trips * 0
        mode_cols = [col for col in city_data.columns if col.startswith("mode_")]
        mode_shares = {}
        for mode in mode_cols:
            mode_shares[mode.replace("mode_", "")] = (
                (city_data[mode] * city_data["total_trips"]).sum() / total_trips
                if total_trips > 0
                else 0
            )
        city_stats.append(
            {
                "city": city,
                "total_trips": total_trips,
                "innovation_share": sum(poi_shares.get(poi, 0) for poi in innovation_district_pois),
                "poi_distribution": poi_shares.to_dict(),
                "mode_shares": mode_shares,
                "BGU_trips": poi_trips.get("Ben-Gurion-University", 0),
                "Soroka_trips": poi_trips.get("Soroka-Medical-Center", 0),
                "GavYam_trips": poi_trips.get("Gav-Yam-High-Tech-Park", 0),
                "ID_trips": (
                    poi_trips.get("Ben-Gurion-University", 0)
                    + poi_trips.get("Soroka-Medical-Center", 0)
                    + poi_trips.get("Gav-Yam-High-Tech-Park", 0)
                ),
            }
        )
    return pd.DataFrame(city_stats).sort_values("total_trips", ascending=False)


def generate_origin_statistics_csv(city_df: pd.DataFrame) -> pd.DataFrame:
    notes_path = REPRODUCE_INBOUND_DIR / "origin_city_notes.csv"
    notes = pd.read_csv(notes_path)
    featured = city_df.merge(notes, on="city", how="inner")
    featured = featured.sort_values("ID_trips", ascending=False)
    return featured[
        [
            "city",
            "BGU_trips",
            "Soroka_trips",
            "GavYam_trips",
            "ID_trips",
            "note",
        ]
    ]


def write_dataset_details() -> None:
    source = REPRODUCE_INBOUND_DIR / "dataset_details.md"
    text = source.read_text()
    filter_note = (
        "\n\n## Work-Trip Filter\n\n"
        "All exports in `output/working_trips/` include **work-purpose trips only**, "
        "identified by the `Work` purpose category in the source mobility data.\n"
    )
    if "## Work-Trip Filter" not in text:
        text = text.rstrip() + filter_note + "\n"
    (WORK_OUTPUT_DIR / "dataset_details.md").write_text(text)


def copy_static_files() -> None:
    shutil.copy2(
        REPRODUCE_INBOUND_DIR / "origin_city_notes.csv",
        WORK_OUTPUT_DIR / "origin_city_notes.csv",
    )


def generate_walk_animation() -> Path:
    sys.path.insert(0, str(REPO_ROOT / "viz" / "trips"))
    from walk_trips_viz import create_animation

    output_path = WORK_OUTPUT_DIR / "walking_trip_animation.html"
    create_animation(output_path=output_path, work_trips_only=True)
    return output_path


def generate_arc_visualization() -> Path:
    sys.path.insert(0, str(REPO_ROOT / "viz" / "trips"))
    from trips_arc_glow import create_arc_visualization

    return create_arc_visualization(
        output_dir=WORK_OUTPUT_DIR,
        work_trips_only=True,
        light_theme=True,
        output_filename="walking_arc_visualization.html",
    )


def generate_zone_trip_map() -> Path:
    sys.path.insert(0, str(REPO_ROOT / "viz" / "trips"))
    from zone_trip_map import create_zone_trip_map

    return create_zone_trip_map(
        output_path=WORK_OUTPUT_DIR / "zone_trip_map.html",
        work_trips_only=True,
    )


def run() -> None:
    WORK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Generating work-trip exports in %s", WORK_OUTPUT_DIR)

    mode_df = generate_mode_split()
    temporal_df = generate_temporal()
    distance_df = generate_distance_histogram()
    consolidated_df = generate_consolidated_csv(mode_df, temporal_df, distance_df)
    city_df = analyze_cities(load_city_analysis_data())

    mode_df.to_csv(WORK_OUTPUT_DIR / "frontend_mode_split.csv", index=False)
    temporal_df.to_csv(WORK_OUTPUT_DIR / "frontend_temporal.csv", index=False)
    distance_df.to_csv(WORK_OUTPUT_DIR / "frontend_distance_histogram.csv", index=False)
    consolidated_df.to_csv(WORK_OUTPUT_DIR / "frontend_mobility_data.csv", index=False)
    city_df.head(15).to_csv(
        WORK_OUTPUT_DIR / "top_15_cities_innovation_district.csv",
        index=False,
    )
    generate_origin_statistics_csv(city_df).to_csv(
        WORK_OUTPUT_DIR / "origin_statistics.csv",
        index=False,
    )

    write_dataset_details()
    copy_static_files()
    animation_path = generate_walk_animation()
    arc_path = generate_arc_visualization()
    zone_map_path = generate_zone_trip_map()

    logger.info("Created %s rows in frontend_mobility_data.csv", len(consolidated_df))
    logger.info("Walking animation saved to %s", animation_path)
    logger.info("Arc visualization saved to %s", arc_path)
    logger.info("Zone trip map saved to %s", zone_map_path)
    logger.info("Done.")


if __name__ == "__main__":
    run()
