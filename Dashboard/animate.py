import sys
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from data_loader import DataLoader
from config import BASE_DIR, OUTPUT_DIR, COLOR_SCHEME, CHART_COLORS

def load_data():
    loader = DataLoader(BASE_DIR, OUTPUT_DIR)
    zones = loader.load_zones()
    poi_df = loader.load_poi_data()
    trip_data = loader.load_trip_data()
    return zones, poi_df, trip_data

def create_origin_comparison(trip_data, pois, zones):
    frames = []
    for poi in pois:
        df = trip_data[(poi, 'inbound')]
        merged = zones.merge(df, left_on='YISHUV_STAT11', right_on='tract', how='left')
        merged['total_trips'] = merged['total_trips'].fillna(0)
        
        frame = go.Frame(
            data=[go.Choroplethmapbox(
                geojson=merged.__geo_interface__,
                locations=merged.index,
                z=np.log1p(merged['total_trips']),
                colorscale="Viridis",
                name=poi,
                showscale=True,
                hovertemplate=f"{poi}<br>Trips: %{{z:.0f}}<extra></extra>"
            )],
            name=poi
        )
        frames.append(frame)
    
    return frames

def create_mode_comparison(trip_data, pois):
    frames = []
    for poi in pois:
        df = trip_data[(poi, 'inbound')]
        mode_cols = [col for col in df.columns if col.startswith('mode_')]
        mode_data = df[mode_cols].mean()
        
        frame = go.Frame(
            data=[go.Bar(
                x=mode_data.index,
                y=mode_data.values,
                name=poi
            )],
            name=poi
        )
        frames.append(frame)
    
    return frames

def create_time_comparison(trip_data, pois):
    frames = []
    for poi in pois:
        df = trip_data[(poi, 'inbound')]
        time_cols = [col for col in df.columns if col.startswith('arrival_')]
        time_data = df[time_cols].mean()
        
        frame = go.Frame(
            data=[go.Scatter(
                x=[col.split('_')[1] for col in time_data.index],
                y=time_data.values,
                mode='lines+markers',
                name=poi
            )],
            name=poi
        )
        frames.append(frame)
    
    return frames

def create_animation(pois=['BGU', 'Soroka Hospital', 'Gev Yam']):
    zones, poi_df, trip_data = load_data()
    
    # Create figure with secondary y-axis
    fig = make_subplots(rows=2, cols=2,
                       specs=[[{"type": "mapbox"}, {"type": "xy"}],
                             [{"type": "xy", "colspan": 2}, None]],
                       subplot_titles=("Trip Origins", "Mode Distribution",
                                     "Time Distribution"))
    
    # Add frames for each visualization type
    origin_frames = create_origin_comparison(trip_data, pois, zones)
    mode_frames = create_mode_comparison(trip_data, pois)
    time_frames = create_time_comparison(trip_data, pois)
    
    # Combine all frames
    fig.frames = origin_frames + mode_frames + time_frames
    
    # Add buttons and sliders for animation control
    fig.update_layout(
        updatemenus=[{
            "buttons": [
                {
                    "args": [None, {"frame": {"duration": 1000, "redraw": True},
                                   "fromcurrent": True}],
                    "label": "Play",
                    "method": "animate"
                },
                {
                    "args": [[None], {"frame": {"duration": 0, "redraw": True},
                                     "mode": "immediate",
                                     "transition": {"duration": 0}}],
                    "label": "Pause",
                    "method": "animate"
                }
            ],
            "type": "buttons"
        }],
        sliders=[{
            "steps": [
                {
                    "args": [[f.name], {"frame": {"duration": 0, "redraw": True},
                                       "mode": "immediate",
                                       "transition": {"duration": 0}}],
                    "label": f.name,
                    "method": "animate"
                }
                for f in fig.frames
            ]
        }]
    )
    
    # Update layout
    fig.update_layout(
        mapbox_style="carto-darkmatter",
        mapbox=dict(
            center=dict(lat=31.2529, lon=34.7915),
            zoom=11
        ),
        template="plotly_dark",
        height=1000
    )
    
    return fig

def main():
    print("\nStarting POI comparison animation generation...")
    print(f"Output directory: {os.path.abspath(OUTPUT_DIR)}")
    
    # Load data
    print("\nLoading data...")
    zones, poi_df, trip_data = load_data()
    print(f"Loaded {len(zones)} zones")
    print(f"Loaded {len(poi_df)} POIs")
    print(f"Loaded trip data for {len(trip_data)} POI-trip type combinations")
    
    # Create animation
    print("\nCreating animation...")
    pois = ['BGU', 'Soroka Hospital', 'Gev Yam']
    print(f"Comparing POIs: {', '.join(pois)}")
    
    fig = create_animation(pois)
    
    # Save animation
    output_file = "new_poi_comparison_animation.html"
    output_path = os.path.join(OUTPUT_DIR, output_file)
    fig.write_html(output_path)
    print(f"\nAnimation saved to: {output_path}")
    
    # Print statistics for each POI
    print("\nPOI Statistics:")
    for poi in pois:
        df = trip_data[(poi, 'inbound')]
        total_trips = df['total_trips'].sum()
        mode_cols = [col for col in df.columns if col.startswith('mode_')]
        main_mode = max([(col, df[col].mean()) for col in mode_cols], key=lambda x: x[1])
        
        print(f"\n{poi}:")
        print(f"  Total trips: {total_trips:,.0f}")
        print(f"  Main mode: {main_mode[0].replace('mode_', '')} ({main_mode[1]:.1f}%)")

if __name__ == "__main__":
    main()
