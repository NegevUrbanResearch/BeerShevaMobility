import sys
import os
import numpy as np
import random

from config import BASE_DIR, OUTPUT_DIR, DATA_DIR

from data_loader import DataLoader
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import FloatImage
from branca.colormap import LinearColormap

def load_data():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    loader = DataLoader(BASE_DIR, OUTPUT_DIR)
    print(f"Looking for zones file at: {loader.zones_file}")
    zones = loader.load_zones()
    poi_df = loader.load_poi_data()
    trip_data = loader.load_trip_data()
    return zones, poi_df, trip_data


def calculate_percentages(df):
    total_trips = df['total_trips'].sum()
    df['percentage'] = df['total_trips'] / total_trips * 100
    return df

def create_comparative_map(poi1, poi2, trip_type, zones, trip_data):
    df1 = calculate_percentages(trip_data[(poi1, trip_type)])
    df2 = calculate_percentages(trip_data[(poi2, trip_type)])

    merged_df = pd.merge(df1, df2, on='tract', suffixes=('_1', '_2'))
    merged_df['ratio'] = np.where(
        merged_df['percentage_2'] == 0,
        merged_df['percentage_1'].clip(lower=1e-10),  # Use a small positive value instead of 0
        merged_df['percentage_1'] / merged_df['percentage_2']
    )
    merged_df['ratio'] = merged_df['ratio'].clip(lower=1e-10, upper=100)  # Limit extreme ratios
    merged_df['log_ratio'] = np.log2(merged_df['ratio'])
    merged_df['difference'] = merged_df['percentage_1'] - merged_df['percentage_2']
    merged_df = merged_df.dropna(subset=['ratio', 'difference'])

    # Debug: Print some statistics about the ratio
    print(f"\nRatio statistics:")
    print(f"Min ratio: {merged_df['ratio'].min()}")
    print(f"Max ratio: {merged_df['ratio'].max()}")
    print(f"Mean ratio: {merged_df['ratio'].mean()}")
    print(f"Median ratio: {merged_df['ratio'].median()}")

    # Handle extreme ratios
    merged_df['log_ratio'] = np.clip(merged_df['log_ratio'], -5, 5)

    map_df = zones.merge(merged_df, left_on='YISHUV_STAT11', right_on='tract', how='inner')

    m = folium.Map(location=[31.2529, 34.7915], zoom_start=11, tiles='CartoDB dark_matter')

    colormap = LinearColormap(
        colors=['blue', 'white', 'red'], 
        vmin=-5, 
        vmax=5,
        caption='Ratio of percentages (log scale)',
        text_color = 'white'
    )

    # Add the colormap to the map
    colormap.add_to(m)


    def style_function(feature):
        log_ratio = feature['properties']['log_ratio']
        color = colormap(log_ratio)
        # Debug: Print some ratios and their corresponding colors
        if random.random() < 0.1:  # Print for about 10% of features
            print(f"Log Ratio: {log_ratio}, Color: {color}")
        return {'fillColor': color, 'color': 'black', 'weight': 1, 'fillOpacity': 0.7}

    def highlight_function(feature):
        return {'fillColor': 'yellow', 'color': 'black', 'weight': 3, 'fillOpacity': 0.9}

    folium.GeoJson(
        map_df,
        style_function=style_function,
        highlight_function=highlight_function,
        tooltip=folium.GeoJsonTooltip(
            fields=['YISHUV_STAT11', 'total_trips_1', 'percentage_1', 'total_trips_2', 'percentage_2', 'ratio', 'difference'],
            aliases=[f'Zone', f'{poi1} Trips', f'{poi1} %', f'{poi2} Trips', f'{poi2} %', 'Ratio', 'Difference'],
            localize=True,
            sticky=False,
            labels=True,
            style="""
                background-color: #F0EFEF;
                border: 2px solid black;
                border-radius: 3px;
                box-shadow: 3px;
            """,
            max_width=800,
        ),
    ).add_to(m)

    colormap.add_to(m)

    total_trips1 = df1['total_trips'].sum()
    total_trips2 = df2['total_trips'].sum()

    legend_html = f"""
    <div style="position: fixed; bottom: 50px; left: 50px; width: 250px; height: 250px; 
                border:2px solid grey; z-index:9999; font-size:14px; 
                background-color:rgba(0, 0, 0, 0.8); color: white;">
        <p style="margin: 10px;">
            <b>{poi1} vs {poi2} ({trip_type})</b><br>
            Color indicates the ratio of percentages of users from each zone.<br>
            Blue: Higher % for {poi2}<br>
            White: Equal %<br>
            Red: Higher % for {poi1}<br>
            Total trips for {poi1}: {total_trips1:,}<br>
            Total trips for {poi2}: {total_trips2:,}<br>
            Trip type: {trip_type}
        </p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    output_dir = os.path.join(OUTPUT_DIR, 'comparison_maps')
    os.makedirs(output_dir, exist_ok=True)
    m.save(os.path.join(output_dir, f'comparison_{poi1.replace(" ", "_")}_{poi2.replace(" ", "_")}_{trip_type}.html'))

def get_valid_input(prompt, valid_range):
    while True:
        try:
            user_input = int(input(prompt))
            if user_input in valid_range:
                return user_input
            else:
                print(f"Please enter a number between {valid_range.start} and {valid_range.stop - 1}")
        except ValueError:
            print("Please enter a valid number")

def main():
    zones, poi_df, trip_data = load_data()

    comparisons = [
        ("BGU", "Gev Yam"),
        ("BGU", "Soroka Hospital"),
        ("Gev Yam", "Soroka Hospital")
    ]

    for poi1, poi2 in comparisons:
        for trip_type in ['inbound', 'outbound']:
            create_comparative_map(poi1, poi2, trip_type, zones, trip_data)
            print(f"Map comparing {poi1} and {poi2} for {trip_type} trips has been saved.")

if __name__ == "__main__":
    main()
