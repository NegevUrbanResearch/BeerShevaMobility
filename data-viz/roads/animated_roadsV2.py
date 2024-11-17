import geopandas as gpd
import folium
from branca.colormap import LinearColormap
import numpy as np
import os
import sys
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    
    # Updated CSS with smoother animations
    css = """
    <style>
        /* Animation keyframes with longer distances for smoother flow */
        @keyframes flow1 {
            0% { stroke-dashoffset: 2000; }
            100% { stroke-dashoffset: 0; }
        }
        @keyframes flow2 {
            0% { stroke-dashoffset: 1800; }
            100% { stroke-dashoffset: -200; }
        }
        @keyframes flow3 {
            0% { stroke-dashoffset: 1600; }
            100% { stroke-dashoffset: -400; }
        }
        @keyframes flow4 {
            0% { stroke-dashoffset: 1400; }
            100% { stroke-dashoffset: -600; }
        }
        @keyframes flow5 {
            0% { stroke-dashoffset: 1200; }
            100% { stroke-dashoffset: -800; }
        }
        
        .leaflet-overlay-pane svg path {
            stroke-linecap: round;
            stroke-linejoin: round;
        }
        .road-base {
            opacity: 0.7;
        }
        .flow-line {
            stroke-width: 3px !important;
            stroke: white !important;
            animation-timing-function: linear;
            will-change: stroke-dashoffset;
            backface-visibility: hidden;
            -webkit-backface-visibility: hidden;
        }
    </style>
    """
    m.get_root().header.add_child(folium.Element(css))
    
    # Filter out roads with less than 10 trips
    road_usage = road_usage[road_usage['count'] >= 10]
    
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
    
    # Calculate speed thresholds using percentiles
    speed_thresholds = np.percentile(road_usage['count'], [20, 40, 60, 80])
    
    # Calculate logarithmic scale for opacity
    min_count = road_usage['count'].min()
    max_count = road_usage['count'].max()
    
    def get_opacity(count):
        """Calculate opacity using cube root scale, range 0.1 to 0.9"""
        if count <= 0:
            return 0.1
        # Using cube root instead of log for less compression of higher values
        scale = np.cbrt(count - 10) / np.cbrt(max_count - 10)
        # Alternative: could use square root for even less compression
        # scale = np.sqrt(count - 10) / np.sqrt(max_count - 10)
        return 0.1 + (scale * 0.8)  # Scale to range 0.1-0.9
    
    def get_weight(count):
        """Calculate line weight using similar cube root scale"""
        scale = np.cbrt(count - 10) / np.cbrt(max_count - 10)
        return 2 + (scale * 6)  # Scale from 2 to 8 pixels
    
    def get_speed_class(count):
        """Get speed class based on count terciles"""
        if count >= np.percentile(road_usage['count'], 66):
            return 'flow-speed-high'
        elif count >= np.percentile(road_usage['count'], 33):
            return 'flow-speed-med'
        return 'flow-speed-low'
    
    def get_animation_duration(count):
        """Calculate animation duration based on traffic volume"""
        min_duration = 20  # fastest animation (highest volume)
        max_duration = 35  # even slower for low volume roads
        scale = 1 - (np.cbrt(count - 10) / np.cbrt(max_count - 10))
        return min_duration + (scale * (max_duration - min_duration))
    
    def get_dash_pattern(count):
        """Calculate dash pattern based on traffic volume"""
        dash_length = 30
        min_gap = 40    # for highest volume
        max_gap = 120   # slightly larger gaps for low volume
        scale = 1 - (np.cbrt(count - 10) / np.cbrt(max_count - 10))
        gap = min_gap + (scale * (max_gap - min_gap))
        return f"{dash_length}, {int(gap)}"
    
    def get_dash_opacity(count):
        """Calculate dash opacity based on traffic volume using cube root scaling"""
        min_opacity = 0.05  # very faint for lowest volume
        max_opacity = 1.0   # fully visible for highest volume
        
        # Use cube root scaling like we did for the roads
        scale = np.cbrt(count - 10) / np.cbrt(max_count - 10)
        opacity = min_opacity + (scale * (max_opacity - min_opacity))
        
        # Make high traffic roads much brighter
        return opacity ** 0.5  # Square root to boost high values
    
    # Add road segments with styling
    for _, row in road_usage.iterrows():
        if row.geometry is None or not row.geometry.is_valid:
            continue
            
        base_opacity = get_opacity(row['count'])
        dash_opacity = get_dash_opacity(row['count'])
        weight = get_weight(row['count'])
        duration = get_animation_duration(row['count'])
        dash_pattern = get_dash_pattern(row['count'])
        
        # Add base road
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x, opacity=base_opacity, weight=weight: {
                'color': '#7F00FF',
                'weight': weight,
                'opacity': opacity,
                'className': 'road-base'
            },
            tooltip=f"Traffic Volume: {int(row['count']):,} trips"
        ).add_to(m)
        
        # Add animated flow line with volume-based opacity
        variant = np.random.randint(1, 6)
        delay = np.random.uniform(0, duration)
        
        style = f"""
            <style>
                .flow-line-{row.name} {{
                    animation: flow{variant} {duration}s linear infinite;
                    animation-delay: -{delay}s;
                    stroke-dasharray: {dash_pattern};
                    opacity: {dash_opacity} !important;
                    stroke: rgba(255, 255, 255, {dash_opacity}) !important;
                }}
            </style>
        """
        m.get_root().header.add_child(folium.Element(style))
        
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x: {
                'className': f'flow-line flow-line-{row.name}'
            }
        ).add_to(m)
    
    # Updated continuous legend with color bar
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
            <div style="height: 150px; width: 40px; margin-right: 20px; float: left;">
                <div style="height: 100%; width: 100%; 
                            background: linear-gradient(to bottom, 
                                rgba(127, 0, 255, 0.9) 0%,
                                rgba(127, 0, 255, 0.5) 50%,
                                rgba(127, 0, 255, 0.1) 100%);
                            border-radius: 3px;">
                </div>
            </div>
            <div style="margin-left: 70px;">
                <div style="margin-bottom: 120px;">{int(max_count):,} trips</div>
                <div style="margin-bottom: 5px;">{int(min_count):,} trips</div>
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