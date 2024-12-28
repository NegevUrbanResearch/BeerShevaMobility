import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from shapely.geometry import Point
import geopandas as gpd
import os
import logging
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set the correct directories
BASE_DIR = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
DATA_DIR = os.path.join(BASE_DIR, 'output', 'processed_poi_data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output', 'visualizations')
POI_FILE = os.path.join(BASE_DIR, 'output/processed_poi_data/poi_with_exact_coordinates.csv')
ZONES_FILE = os.path.join(BASE_DIR, 'statisticalareas_demography2019.gdb')

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Modern color scheme (using the same as mode_spread_visualization.py)
colors = {
    'car': '#FF6B6B',
    'public_transit': '#4ECDC4',
    'train': '#45B7D1',
    'ped': '#98FB98',
    'bike': '#FFA07A'
}

poi_display_names = {
    'BGU': 'Ben Gurion University',
    'Soroka_Hospital': 'Soroka Hospital',
    'Gev_Yam': 'Gav Yam High-Tech Park'
}

# Update the mode info with cleaner labels
mode_info = {
    'car': {'color': '#FF6B6B', 'label': 'Car'},
    'public_transit': {'color': '#4ECDC4', 'label': 'Public Transit'},
    'ped': {'color': '#98FB98', 'label': 'Walking'},
    'bike': {'color': '#FFA07A', 'label': 'Cycling'}
}

def calculate_distances(poi_data, zones_gdf):
    """Calculate distances from each zone centroid to POI"""
    # Create a GeoDataFrame for the POI point
    poi_point = Point(poi_data['lon'], poi_data['lat'])  # Changed from longitude/latitude to lon/lat
    poi_gdf = gpd.GeoDataFrame(geometry=[poi_point], crs="EPSG:4326")
    
    # Ensure both geometries are in the same projected CRS (UTM zone 36N for Israel)
    poi_gdf = poi_gdf.to_crs("EPSG:32636")
    zones_projected = zones_gdf.to_crs("EPSG:32636")
    
    # Calculate centroids and distances
    zones_projected['centroid'] = zones_projected.geometry.centroid
    zones_projected['distance_km'] = zones_projected.apply(
        lambda row: poi_gdf.geometry.iloc[0].distance(row.centroid) / 1000,  # Convert meters to kilometers
        axis=1
    )
    
    return zones_projected

def calculate_percentages(trip_data):
    """Calculate percentage of trips for each tract"""
    total_trips = trip_data['count'].sum()
    trip_data['percentage'] = (trip_data['count'] / total_trips) * 100
    return trip_data

def load_poi_locations(csv_file):
    try:
        poi_df = pd.read_csv(csv_file)
        # Debug print
        logger.info(f"Loaded POI DataFrame:")
        logger.info(f"Columns: {poi_df.columns.tolist()}")
        logger.info(f"Sample data:\n{poi_df.head()}")
        
        poi_dict = poi_df.set_index('ID').to_dict(orient='index')
        logger.info(f"Converted to dictionary with {len(poi_dict)} entries")
        logger.info(f"Sample POI entry: {next(iter(poi_dict.items()))}")
        return poi_dict
    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
        logger.debug(traceback.format_exc())
        return {}

def create_individual_plot(poi_key, poi_data):
    fig = go.Figure()
    
    # Get total counts for each distance bin
    distance_totals = {}
    for distance_bin in range(5):  # 0 to 4 km bins
        total = 0
        for mode in ['car', 'public_transit', 'ped', 'bike']:
            if mode in poi_data['data']:
                mode_data = poi_data['data'][mode]
                bin_data = mode_data[mode_data['distance_bin'] == distance_bin]
                if not bin_data.empty:
                    total += bin_data['count'].iloc[0]
        distance_totals[distance_bin] = total
    
    # Create percentage-based stacked bars
    for mode in ['car', 'public_transit', 'ped', 'bike']:
        if mode in poi_data['data']:
            mode_data = poi_data['data'][mode]
            percentages = []
            x_values = []
            
            for distance_bin in range(5):  # 0 to 4 km bins
                bin_data = mode_data[mode_data['distance_bin'] == distance_bin]
                if not bin_data.empty and distance_totals[distance_bin] > 0:
                    percentage = (bin_data['count'].iloc[0] / distance_totals[distance_bin]) * 100
                    percentages.append(percentage)
                    x_values.append(distance_bin + 0.5)
                else:
                    percentages.append(0)
                    x_values.append(distance_bin + 0.5)
            
            fig.add_trace(
                go.Bar(
                    x=x_values,
                    y=percentages,
                    name=mode_info[mode]['label'],  # Just the clean label, no icon
                    marker_color=mode_info[mode]['color'],
                    opacity=0.85,
                    width=0.8
                )
            )

    # Update layout (mostly the same, but with percentage y-axis)
    fig.update_layout(
        barmode='stack',
        title=dict(
            text=f"Mode Share Distribution Within 5km of {poi_display_names[poi_key]}",
            font=dict(size=32, color='rgba(255,255,255,0.95)', family='Arial Black'),
            x=0.5,
            xanchor='center',
            y=0.95
        ),
        height=900,
        width=1200,
        showlegend=True,
        paper_bgcolor='rgb(17,17,17)',
        plot_bgcolor='rgb(17,17,17)',
        hovermode='x unified',
        margin=dict(l=100, r=100, t=150, b=100),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor='rgba(0,0,0,0)',
            font=dict(
                color='rgba(255,255,255,0.95)', 
                size=24
            ),
            itemsizing='constant',
            tracegroupgap=40  # Increased gap between items
        )
    )
    
    # Update the traces with better visibility
    for trace in fig.data:
        trace.update(
            marker=dict(
                line=dict(width=3, color='rgba(255,255,255,0.5)'),  # Thicker, more visible borders
                opacity=1  # Full opacity
            ),
            showlegend=True,
            legendgrouptitle_font_size=24,
            # Make the legend entries more prominent
            name=f"<span style='display:inline-block;width:50px;height:50px;background-color:{trace.marker.color};border:2px solid rgba(255,255,255,0.5);margin-right:10px'></span>{trace.name}"
        )
    
    # Update axes with larger text
    fig.update_xaxes(
        title_text="Distance (km)",
        title_font=dict(color='rgba(255,255,255,0.95)', size=24),
        title_standoff=15,
        range=[0, 5],
        dtick=1,
        tickfont=dict(color='rgba(255,255,255,0.95)', size=20),
        gridcolor='rgba(255,255,255,0.2)',
        gridwidth=1,
        showgrid=True,
        showline=True,
        linecolor='rgba(255,255,255,0.3)',
        linewidth=2,
        zeroline=True,
        zerolinecolor='rgba(255,255,255,0.3)',
        zerolinewidth=2,
        ticks='outside',
        ticklabelposition='outside',
        ticklen=8,
        tickwidth=2,
        mirror=True,
        anchor='y'
    )
    
    fig.update_yaxes(
        title_text="Mode Share (%)",
        range=[0, 100],
        ticksuffix="%",
        title_font=dict(color='rgba(255,255,255,0.95)', size=24),
        title_standoff=15,
        tickfont=dict(color='rgba(255,255,255,0.95)', size=20),
        gridcolor='rgba(255,255,255,0.2)',
        gridwidth=1,
        showgrid=True,
        showline=True,
        linecolor='rgba(255,255,255,0.3)',
        linewidth=2,
        zeroline=True,
        zerolinecolor='rgba(255,255,255,0.3)',
        zerolinewidth=2,
        ticks='outside',
        ticklabelposition='outside',
        ticklen=8,
        tickwidth=2,
        mirror=True,
        anchor='x'
    )
    
    return fig

def create_distance_histograms():
    # Load POI locations and zones
    poi_locations = load_poi_locations(POI_FILE)
    zones = gpd.read_file(ZONES_FILE)
    
    # Debug print zones info
    logger.info(f"Loaded zones GeoDataFrame:")
    logger.info(f"Columns: {zones.columns.tolist()}")
    logger.info(f"CRS: {zones.crs}")
    
    # Load the original Excel file once for all POIs
    logger.info("Loading Excel data...")
    df = pd.read_excel(os.path.join(BASE_DIR, 'All-Stages.xlsx'), sheet_name='StageB1')
    logger.info(f"Excel data columns: {df.columns.tolist()}")
    logger.info(f"Sample data:\n{df.head()}")
    
    # Add after loading Excel data (around line 174):
    logger.info("All unique modes in Excel data:")
    logger.info(df['mode'].unique())
    
    # Clean tract IDs
    df['from_tract'] = df['from_tract'].apply(lambda x: f"{int(float(x)):06d}" if pd.notna(x) else '000000')
    df['to_tract'] = df['to_tract'].apply(lambda x: f"{int(float(x)):06d}" if pd.notna(x) else '000000')
    zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].astype(str).str.zfill(6)
    
    # Dictionary to store trip data for each POI
    trip_data = {}
    
    # Pre-process data for each POI
    for poi_key in ['BGU', 'Soroka_Hospital', 'Gev_Yam']:
        try:
            # Get POI info using name with proper mapping
            poi_info = next(
                (
                    {'name': info['name'], 'lat': info['lat'], 'lon': info['lon'], 'ID': key, 'tract': info['tract']}
                    for key, info in poi_locations.items() 
                    if info['name'] == 'BGU' and poi_key == 'BGU'
                    or info['name'] == 'Soroka Hospital' and poi_key == 'Soroka_Hospital'
                    or info['name'] == 'Gev Yam' and poi_key == 'Gev_Yam'
                ),
                None
            )
            
            if poi_info is None:
                logger.error(f"Could not find POI info for {poi_key}")
                logger.info(f"Available POI names: {[info['name'] for info in poi_locations.values()]}")
                continue
            
            logger.info(f"Processing POI: {poi_key}")
            logger.info(f"POI info: {poi_info}")
            
            # Filter for inbound trips to this POI using tract
            poi_tract = str(int(poi_info['tract'])).zfill(6)
            poi_trips = df[df['to_tract'] == poi_tract].copy()
            
            logger.info(f"Found {len(poi_trips)} trips for {poi_key}")
            if len(poi_trips) == 0:
                logger.warning(f"No trips found for {poi_key}")
                continue
            
            # Combine modes with comprehensive mapping
            mode_mapping = {
                'bus': 'public_transit',
                'Bus': 'public_transit',
                'link': 'public_transit',
                'Link': 'public_transit',
                'train': 'public_transit',
                'Train': 'public_transit',
                'Public transit': 'public_transit',
                'public transport': 'public_transit',
                'Public Transport': 'public_transit',
                'walk': 'ped',
                'Walk': 'ped',
                'pedestrian': 'ped',
                'walking': 'ped',
                'Walking': 'ped',
                'bike': 'bike',
                'Bike': 'bike',
                'bicycle': 'bike',
                'Bicycle': 'bike',
                'cycling': 'bike',
                'Cycling': 'bike',
                'ebike': 'bike',
                'E-bike': 'bike',
                'Car': 'car',
                'car': 'car',
                'private car': 'car',
                'Private Car': 'car'
            }

            # Log original mode distribution
            logger.info(f"Original mode distribution for {poi_key}:")
            logger.info(poi_trips['mode'].value_counts())
            logger.info(f"Unique modes before mapping: {poi_trips['mode'].unique()}")

            poi_trips['mode'] = poi_trips['mode'].str.lower().replace(mode_mapping)

            # Log updated mode distribution
            mode_counts = poi_trips['mode'].value_counts()
            logger.info(f"Updated mode distribution for {poi_key} after combining transit modes:\n{mode_counts}")
            
            zones_with_distances = calculate_distances(poi_info, zones.copy())
            
            # Pre-process data for each mode
            processed_data = {}
            for mode in ['car', 'public_transit', 'ped', 'bike']:
                mode_data = poi_trips[poi_trips['mode'] == mode]
                if not mode_data.empty:
                    # Group by origin tract and sum trips
                    tract_trips = mode_data.groupby('from_tract')['count'].sum().reset_index()
                    
                    # Merge with distances
                    merged_data = pd.merge(
                        zones_with_distances[['YISHUV_STAT11', 'distance_km']],
                        tract_trips,
                        left_on='YISHUV_STAT11',
                        right_on='from_tract'
                    )
                    
                    # Create distance bins (1km increments up to 5km)
                    merged_data = merged_data[merged_data['distance_km'] <= 5]  # Filter for trips within 5km
                    merged_data['distance_bin'] = merged_data['distance_km'] // 1 * 1
                    logger.info(f"Distance distribution (0-5km) for {mode} in {poi_key}:")
                    logger.info(merged_data.groupby('distance_bin')['count'].sum())
                    binned_data = merged_data.groupby('distance_bin')['count'].sum().reset_index()
                    processed_data[mode] = binned_data
            
            if processed_data:
                trip_data[poi_key] = {
                    'data': processed_data,
                    'max_distance': zones_with_distances['distance_km'].max(),
                    'max_trips': max(data['count'].max() for data in processed_data.values())
                }
                logger.info(f"Successfully processed data for {poi_key}")

        except Exception as e:
            logger.error(f"Error processing data for {poi_key}: {str(e)}")
            logger.debug(traceback.format_exc())
            continue

    # Create individual plots for each POI
    for poi_key, poi_data in trip_data.items():
        create_individual_plot(poi_key, poi_data)

    # Save visualizations and log locations
    for poi_key in trip_data:
        fig = create_individual_plot(poi_key, trip_data[poi_key])
        
        # Save individual visualizations
        html_file = os.path.join(OUTPUT_DIR, f'distance_spread_{poi_key}_interactive.html')
        jpg_file = os.path.join(OUTPUT_DIR, f'distance_spread_{poi_key}.jpg')
        
        fig.write_html(html_file)
        fig.write_image(jpg_file)
        
        logger.info(f"Saved visualizations for {poi_key}:")
        logger.info(f"- Interactive HTML: {html_file}")
        logger.info(f"- Static Image: {jpg_file}")

if __name__ == "__main__":
    create_distance_histograms()
