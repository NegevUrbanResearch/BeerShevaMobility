from datetime import time

import numpy as np
import pandas as pd

from mobility.config import OUTPUT_DIR, RAW_TRIPS_FILE
from mobility.utils.zone_utils import clean_zone_id

TRIP_LOOKUP_FILES = {
    "Ben-Gurion-University": "BGU_inbound_trips.csv",
    "Soroka-Medical-Center": "Soroka_Hospital_inbound_trips.csv",
}

DEFAULT_BGU_DIST = {
    7: 0.020829,
    8: 0.148528,
    9: 0.132706,
    10: 0.181134,
    11: 0.091648,
    12: 0.110234,
    13: 0.067655,
    14: 0.071941,
    15: 0.036371,
    16: 0.044302,
    17: 0.032646,
    18: 0.029481,
    19: 0.018466,
}

DEFAULT_SOROKA_DIST = {
    7: 0.080456,
    8: 0.270533,
    9: 0.110459,
    10: 0.089172,
    11: 0.051793,
    12: 0.052799,
    13: 0.058666,
    14: 0.103084,
    15: 0.030003,
    16: 0.042910,
    17: 0.027154,
    18: 0.017264,
    19: 0.022796,
}


def normalize_distribution(dist: dict) -> dict:
    total = sum(dist.values())
    if total == 0:
        return dist
    return {hour: value / total for hour, value in dist.items()}


def build_work_share_lookup() -> dict:
    lookup = {}
    for destination, filename in TRIP_LOOKUP_FILES.items():
        trip_df = pd.read_csv(OUTPUT_DIR / filename)
        trip_df["tract_clean"] = trip_df["tract"].apply(clean_zone_id)
        lookup[destination] = trip_df.set_index("tract_clean")["purpose_Work"].fillna(0) / 100.0
    return lookup


def get_work_share(row, work_share_lookup: dict) -> float:
    destination = row["destination"]
    zone = clean_zone_id(str(row["origin_zone"]))
    if destination not in work_share_lookup:
        return 0.0
    return float(work_share_lookup[destination].get(zone, 0.0))


def compute_work_hourly_distributions() -> dict:
    df = pd.read_excel(RAW_TRIPS_FILE, sheet_name="StageB1")
    df = df[df["purpose"].str.strip() == "Work"].copy()
    df["hour"] = df["time_bin"].apply(
        lambda value: value.hour if isinstance(value, time) else 0
    )
    df = df[df["mode"].str.lower().isin(["ped", "walk", "walking"])]

    defaults = {
        "Ben-Gurion-University": DEFAULT_BGU_DIST,
        "Soroka-Medical-Center": DEFAULT_SOROKA_DIST,
    }
    distributions = {}
    for raw_name, destination in [
        ("BGU", "Ben-Gurion-University"),
        ("Soroka Hospital", "Soroka-Medical-Center"),
    ]:
        poi_trips = df[df["to_name"] == raw_name]
        hourly = poi_trips.groupby("hour")["count"].sum()
        hour_range = range(7, 20)
        totals = {hour: float(hourly.get(hour, 0)) for hour in hour_range}
        total = sum(totals.values())
        distributions[destination] = normalize_distribution(
            {hour: totals[hour] for hour in hour_range} if total > 0 else defaults[destination]
        )
    return distributions
