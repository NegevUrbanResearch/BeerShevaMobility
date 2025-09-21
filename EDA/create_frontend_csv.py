#!/usr/bin/env python3
"""
Create a consolidated CSV file with key mobility statistics for frontend visualization
"""

import pandas as pd
import json
import os
from pathlib import Path


def load_data():
    """Load all required data files"""
    base_path = Path("/Users/noamgal/Projects/BeerShevaMobility/EDA/output")

    # Load temporal data
    temporal_files = {
        "BGU": base_path
        / "dashboard_data"
        / "ben_gurion_university_inbound_temporal.csv",
        "Soroka Hospital": base_path
        / "dashboard_data"
        / "soroka_medical_center_inbound_temporal.csv",
        "Gav Yam": base_path
        / "dashboard_data"
        / "gav_yam_high_tech_park_inbound_temporal.csv",
    }

    # Load distance data
    distance_files = {
        "BGU": base_path / "distance_histograms" / "bgu_distance_dist.json",
        "Soroka Hospital": base_path
        / "distance_histograms"
        / "soroka_hospital_distance_dist.json",
        "Gav Yam": base_path / "distance_histograms" / "gev_yam_distance_dist.json",
    }

    # Load summary statistics
    summary_file = base_path / "statistics" / "poi_summary_statistics.csv"

    return temporal_files, distance_files, summary_file


def process_mode_split_data(summary_file):
    """Extract mode split data for the three main POIs"""
    df = pd.read_csv(summary_file)

    # Filter for the three main POIs (inbound trips)
    poi_mapping = {
        "Ben-Gurion-University": "BGU",
        "Soroka-Medical-Center": "Soroka Hospital",
        "Gav-Yam-High-Tech-Park": "Gav Yam",
    }

    mode_data = []

    for poi_raw, poi_clean in poi_mapping.items():
        # Get inbound data
        inbound_row = df[(df.iloc[:, 0] == poi_raw) & (df.iloc[:, 1] == "inbound")]
        if not inbound_row.empty:
            # Parse the mode_split string (it's a dictionary string)
            mode_split_str = inbound_row["mode_split"].iloc[0]
            mode_split = eval(mode_split_str)  # Convert string to dict

            # Clean up mode names and convert to percentages
            for mode_raw, percentage in mode_split.items():
                mode_clean = mode_raw.replace("mode_", "").replace("_", " ").title()
                if mode_clean == "Ped":
                    mode_clean = "Walking"
                elif mode_clean == "Bus":
                    mode_clean = "Public Transit"
                elif mode_clean == "Link":
                    mode_clean = "Shared Mobility"

                mode_data.append(
                    {
                        "destination": poi_clean,
                        "mode": mode_clean,
                        "percentage": round(percentage, 2),
                        "trips": round(
                            inbound_row["total_trips"].iloc[0] * percentage / 100, 1
                        ),
                    }
                )

    return pd.DataFrame(mode_data)


def process_temporal_data(temporal_files):
    """Extract hourly trip distributions"""
    temporal_data = []

    for poi, file_path in temporal_files.items():
        df = pd.read_csv(file_path)

        for hour in range(24):
            # Use 'all_dist' column for total distribution across all modes
            if hour < len(df):
                proportion = df.loc[hour, "all_dist"]
                temporal_data.append(
                    {
                        "destination": poi,
                        "hour": hour,
                        "proportion": round(proportion, 6),
                    }
                )

    return pd.DataFrame(temporal_data)


def process_distance_data(distance_files):
    """Extract distance histogram data"""
    distance_data = []

    for poi, file_path in distance_files.items():
        with open(file_path, "r") as f:
            data = json.load(f)

        for mode, ranges in data.items():
            # Clean up mode names
            mode_clean = mode.replace("_", " ").title()
            if mode_clean == "Walk":
                mode_clean = "Walking"
            elif mode_clean == "Transit":
                mode_clean = "Public Transit"

            for range_data in ranges:
                distance_data.append(
                    {
                        "destination": poi,
                        "mode": mode_clean,
                        "distance_range": range_data["range"],
                        "trips": round(range_data["trips"], 1),
                    }
                )

    return pd.DataFrame(distance_data)


def create_consolidated_csv():
    """Create the main consolidated CSV file"""
    print("Loading data files...")
    temporal_files, distance_files, summary_file = load_data()

    print("Processing mode split data...")
    mode_df = process_mode_split_data(summary_file)

    print("Processing temporal data...")
    temporal_df = process_temporal_data(temporal_files)

    print("Processing distance data...")
    distance_df = process_distance_data(distance_files)

    # Create output directory
    output_dir = Path("/Users/noamgal/Projects/BeerShevaMobility/EDA/output")

    # Save individual datasets
    mode_df.to_csv(output_dir / "frontend_mode_split.csv", index=False)
    temporal_df.to_csv(output_dir / "frontend_temporal.csv", index=False)
    distance_df.to_csv(output_dir / "frontend_distance_histogram.csv", index=False)

    print(f"Created individual CSV files:")
    print(f"- Mode split data: {len(mode_df)} rows")
    print(f"- Temporal data: {len(temporal_df)} rows")
    print(f"- Distance data: {len(distance_df)} rows")

    # Create a consolidated file with all data types marked
    consolidated_data = []

    # Add mode split data
    for _, row in mode_df.iterrows():
        consolidated_data.append(
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

    # Add temporal data
    for _, row in temporal_df.iterrows():
        consolidated_data.append(
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

    # Add distance data
    for _, row in distance_df.iterrows():
        consolidated_data.append(
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

    consolidated_df = pd.DataFrame(consolidated_data)
    consolidated_df.to_csv(output_dir / "frontend_mobility_data.csv", index=False)

    print(f"\nCreated consolidated CSV: {len(consolidated_df)} total rows")
    print(f"Saved to: {output_dir / 'frontend_mobility_data.csv'}")

    # Print preview of each data type
    print("\n=== MODE SPLIT DATA PREVIEW ===")
    print(mode_df.head(10))

    print("\n=== TEMPORAL DATA PREVIEW (first 12 hours for BGU) ===")
    print(temporal_df[temporal_df["destination"] == "BGU"].head(12))

    print("\n=== DISTANCE DATA PREVIEW ===")
    print(distance_df.head(10))

    return consolidated_df


if __name__ == "__main__":
    create_consolidated_csv()
