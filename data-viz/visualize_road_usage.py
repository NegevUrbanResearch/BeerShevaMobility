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
    
    # Filter out roads with less than 1 trip
    road_usage = road_usage[road_usage['count'] >= 1]
    
    # Calculate min and max for scaling
    min_count = road_usage['count'].min()
    max_count = road_usage['count'].max()
    
    def get_opacity(count):
        """Calculate opacity using cube root scale, range 0.1 to 0.9"""
        if count <= 0:
            return 0.1
        scale = np.cbrt(count - 1) / np.cbrt(max_count - 1)
        return 0.1 + (scale * 0.8)
    
    def get_weight(count):
        """Calculate line weight using similar cube root scale"""
        scale = np.cbrt(count - 1) / np.cbrt(max_count - 1)
        return 1.5 + (scale * 4.5)  # Scale from 1.5 to 6 pixels
    
    # Add road segments with styling
    for _, row in road_usage.iterrows():
        if row.geometry is None or not row.geometry.is_valid:
            continue
            
        opacity = get_opacity(row['count'])
        weight = get_weight(row['count'])
        
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda x, opacity=opacity, weight=weight: {
                'color': '#7F00FF',  # Single purple color like animated version
                'weight': weight,
                'opacity': opacity,
                'lineCap': 'round',
                'lineJoin': 'round'
            },
            tooltip=f"Traffic Volume: {int(row['count']):,} trips"
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
    
    output_file = os.path.join(OUTPUT_DIR, "road_usage_heatmap.html")
    m.save(output_file)
    print(f"\nHeatmap saved to: {output_file}")

if __name__ == "__main__":
    main()
