import geopandas as gpd
import folium
from branca.colormap import LinearColormap
import numpy as np
import os
from data_loader import DataLoader
from config import BASE_DIR, OUTPUT_DIR
import logging

logger = logging.getLogger(__name__)

def load_road_usage():
    """Load the road usage data and process geometries"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage.geojson")
    print(f"Loading road usage data from: {file_path}")
    road_usage = gpd.read_file(file_path)
    
    # Filter out any invalid geometries
    road_usage = road_usage[road_usage.geometry.notna()]
    road_usage = road_usage[road_usage.geometry.is_valid]
    
    # Ensure CRS is correct
    if road_usage.crs is None or road_usage.crs.to_epsg() != 4326:
        road_usage = road_usage.to_crs(epsg=4326)
    
    return road_usage

def create_road_heatmap(road_usage):
    """Create a folium map with road usage heatmap"""
    m = folium.Map(
        location=[31.2529, 34.7915],
        zoom_start=13,
        tiles='CartoDB dark_matter'
    )
    
    # Updated CSS with larger elements
    css = """
    <style>
        @keyframes flow {
            0% {
                stroke-dashoffset: 500;
            }
            100% {
                stroke-dashoffset: 0;
            }
        }
        .leaflet-overlay-pane svg path {
            stroke-linecap: round;
            stroke-linejoin: round;
        }
        /* Base road style */
        .road-base {
            opacity: 0.7;
        }
        /* Animated flow line */
        .flow-line {
            stroke-width: 4px !important;
            stroke: #FFD700 !important;
            opacity: 0.9;
            animation: flow 15s linear infinite;
        }
        /* Only adjust density of dots based on traffic */
        .flow-speed-1 { 
            stroke-dasharray: 8, 40;
        }
        .flow-speed-2 { 
            stroke-dasharray: 8, 100;
        }
        .flow-speed-3 { 
            stroke-dasharray: 8, 200;
        }
        .flow-speed-4 { 
            stroke-dasharray: 8, 400;
        }
        .flow-speed-5 { 
            stroke-dasharray: 8, 800;
        }
    </style>
    """
    m.get_root().header.add_child(folium.Element(css))
    
    # Filter out roads with less than 1 trip
    road_usage = road_usage[road_usage['count'] >= 1]
    
    # Calculate percentiles for stepped scale
    percentiles = [0, 15, 30, 50, 70, 85, 95, 100]
    thresholds = np.percentile(road_usage['count'], percentiles)
    thresholds = [int(t) for t in thresholds]
    
    # Calculate and print statistics
    total_trips = road_usage['count'].sum()
    avg_trips = road_usage['count'].mean()
    
    # Get top 5 road segments
    top_5_roads = road_usage.nlargest(5, 'count')
    
    print(f"\nRoad Usage Statistics:")
    print(f"Total trips: {int(total_trips):,}")
    print(f"Average trips per segment: {avg_trips:.1f}")
    print("\nTop 5 most used road segments:")
    for idx, row in top_5_roads.iterrows():
        print(f"Segment {idx}: {int(row['count']):,} trips")
    
    # Updated brighter color scheme
    colors = ['#F2E6FF', '#D4B3FF', '#B366FF', '#9933FF', '#7F00FF', '#6600FF', '#5200CC']
    
    colormap = LinearColormap(
        colors=colors,
        vmin=thresholds[0],
        vmax=thresholds[-1],
        caption='',
        text_color='white',
        index=thresholds[1:-1]  # Use thresholds as break points
    )
    
    # Calculate speed thresholds using percentiles
    speed_thresholds = np.percentile(road_usage['count'], [20, 40, 60, 80])
    
    # Add road segments with styling
    for _, row in road_usage.iterrows():
        if row.geometry is None or not row.geometry.is_valid:
            continue
            
        color = colormap(row['count'])
        weight = 3 + (np.log1p(row['count']) / np.log1p(thresholds[-1])) * 6  # Doubled from 1.5 and 3
        
        # Determine animation speed class based on count (higher traffic = faster)
        if row['count'] <= speed_thresholds[0]:
            speed_class = 'flow-speed-5'
        elif row['count'] <= speed_thresholds[1]:
            speed_class = 'flow-speed-4'
        elif row['count'] <= speed_thresholds[2]:
            speed_class = 'flow-speed-3'
        elif row['count'] <= speed_thresholds[3]:
            speed_class = 'flow-speed-2'
        else:
            speed_class = 'flow-speed-1'
        
        # Add base road
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x, color=color, weight=weight: {
                'color': color,
                'weight': weight,
                'opacity': 0.8,
                'className': 'road-base'
            },
            tooltip=f"Traffic Volume: {int(row['count']):,} trips"
        ).add_to(m)
        
        # Add animated flow line
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x, speed_class=speed_class: {
                'className': f'flow-line {speed_class}'
            }
        ).add_to(m)
    
    #colormap.add_to(m)
    
    # Add custom legend showing actual numbers
    legend_html = f"""
    <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 280px;
                border-radius: 8px;
                z-index:9999; 
                font-family: 'Helvetica Neue', Arial, sans-serif;
                background-color: rgba(0, 0, 0, 0.8);
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                color: white;">
        <div style="padding: 15px;">
            <h4 style="margin:0 0 10px 0;">Daily Trips to Innovation District</h4>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background-color: {colors[6]}; margin-right: 10px;"></div>
                <span>{thresholds[6]:,}+ trips</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background-color: {colors[5]}; margin-right: 10px;"></div>
                <span>{thresholds[5]:,} - {thresholds[6]:,} trips</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background-color: {colors[4]}; margin-right: 10px;"></div>
                <span>{thresholds[4]:,} - {thresholds[5]:,} trips</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background-color: {colors[3]}; margin-right: 10px;"></div>
                <span>{thresholds[3]:,} - {thresholds[4]:,} trips</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background-color: {colors[2]}; margin-right: 10px;"></div>
                <span>{thresholds[2]:,} - {thresholds[3]:,} trips</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 5px;">
                <div style="width: 20px; height: 20px; background-color: {colors[1]}; margin-right: 10px;"></div>
                <span>{thresholds[1]:,} - {thresholds[2]:,} trips</span>
            </div>
            <div style="display: flex; align-items: center;">
                <div style="width: 20px; height: 20px; background-color: {colors[0]}; margin-right: 10px;"></div>
                <span>{thresholds[0]:,} - {thresholds[1]:,} trips</span>
            </div>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

def main():
    print("\nStarting road usage visualization...")
    road_usage = load_road_usage()
    print(f"Processing {len(road_usage)} road segments")
    
    m = create_road_heatmap(road_usage)
    
    output_file = os.path.join(OUTPUT_DIR, "road_usage_heatmap_animated.html")
    m.save(output_file)
    print(f"\nHeatmap saved to: {output_file}")

if __name__ == "__main__":
    main()
