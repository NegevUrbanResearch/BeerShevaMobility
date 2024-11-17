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
import plotly.graph_objects as go
import signal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
from PIL import Image

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

def create_regular_heatmap(road_usage):
    """Create a folium map with normal-sized legend for web viewing"""
    m = folium.Map(
        location=[31.2529, 34.7915],
        zoom_start=15,
        tiles='CartoDB dark_matter'
    )
    
    # Filter out roads with less than 1 trip
    road_usage = road_usage[road_usage['count'] >= 1]
    
    # Calculate min and max for scaling
    min_count = road_usage['count'].min()
    max_count = road_usage['count'].max()
    
    def get_opacity(count):
        """Calculate opacity using cube root scale, range 0.2 to 1.0"""
        if count <= 0:
            return 0.2
        scale = np.cbrt(count - 1) / np.cbrt(max_count - 1)
        return 0.2 + (scale * 0.8)
    
    def get_weight(count):
        """Calculate line weight using similar cube root scale"""
        scale = np.cbrt(count - 1) / np.cbrt(max_count - 1)
        return 3.0 + (scale * 9.0)
    
    # Add road segments with styling and larger tooltip
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
            tooltip=folium.Tooltip(
                f"Traffic Volume: {int(row['count']):,} trips",
                style=("background-color: white; "
                      "border: 2px solid #7F00FF; "
                      "border-radius: 6px; "
                      "font-size: 16px; "  # Increased from default
                      "padding: 10px; "    # Added more padding
                      "font-family: 'Helvetica Neue', Arial, sans-serif; "
                      "transform: scale(2.0); "  # Makes tooltip 2x larger
                      "transform-origin: left center; ")  # Keeps tooltip aligned with cursor
            )
        ).add_to(m)
    
    # Larger legend HTML for regular view
    legend_html = f"""
    <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 800px;
                border-radius: 20px;
                z-index:9999; 
                font-family: 'Helvetica Neue', Arial, sans-serif;
                background-color: rgba(0, 0, 0, 0.8);
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                color: white;">
        <div style="padding: 40px;">
            <h4 style="margin:0 0 30px 0; font-size: 36px;">Daily Trips to Innovation District</h4>
            <div style="height: 400px; width: 120px; margin-right: 60px; float: left;">
                <div style="height: 100%; width: 100%; 
                            background: linear-gradient(to bottom, 
                                rgba(127, 0, 255, 1.0) 0%,
                                rgba(127, 0, 255, 0.6) 50%,
                                rgba(127, 0, 255, 0.2) 100%);
                            border-radius: 8px;">
                </div>
            </div>
            <div style="margin-left: 200px; font-size: 32px;">
                <div style="margin-bottom: 320px;">{int(max_count):,} trips</div>
                <div style="margin-bottom: 10px;">{int(min_count):,} trips</div>
            </div>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

def create_screenshot_heatmap(road_usage):
    """Create a folium map with large legend for screenshots"""
    m = folium.Map(
        location=[31.2529, 34.7915],
        zoom_start=15,
        tiles='CartoDB dark_matter'
    )
    
    # Filter out roads with less than 1 trip
    road_usage = road_usage[road_usage['count'] >= 1]
    
    # Calculate min and max for scaling
    min_count = road_usage['count'].min()
    max_count = road_usage['count'].max()
    
    def get_opacity(count):
        """Calculate opacity using cube root scale, range 0.2 to 1.0"""
        if count <= 0:
            return 0.2
        scale = np.cbrt(count - 1) / np.cbrt(max_count - 1)
        return 0.2 + (scale * 0.8)
    
    def get_weight(count):
        """Calculate line weight using similar cube root scale"""
        scale = np.cbrt(count - 1) / np.cbrt(max_count - 1)
        return 3.0 + (scale * 9.0)
    
    # Add road segments with styling and larger tooltip
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
            tooltip=folium.Tooltip(
                f"Traffic Volume: {int(row['count']):,} trips",
                style=("background-color: white; "
                      "border: 2px solid #7F00FF; "
                      "border-radius: 6px; "
                      "font-size: 16px; "
                      "padding: 10px; "
                      "font-family: 'Helvetica Neue', Arial, sans-serif; "
                      "transform: scale(2.0); "
                      "transform-origin: left center; ")
            )
        ).add_to(m)
    
    # Smaller legend HTML for screenshot
    legend_html = f"""
    <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 570px;
                border-radius: 15px;
                z-index:9999; 
                font-family: 'Helvetica Neue', Arial, sans-serif;
                background-color: rgba(0, 0, 0, 0.8);
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                color: white;
                transform: scale(2.0);
                transform-origin: bottom left;">
        <div style="padding: 30px;">
            <h4 style="margin:0 0 22px 0; font-size: 27px;">Daily Trips to Innovation District</h4>
            <div style="height: 300px; width: 90px; margin-right: 45px; float: left;">
                <div style="height: 100%; width: 100%; 
                            background: linear-gradient(to bottom, 
                                rgba(127, 0, 255, 1.0) 0%,
                                rgba(127, 0, 255, 0.6) 50%,
                                rgba(127, 0, 255, 0.2) 100%);
                            border-radius: 6px;">
                </div>
            </div>
            <div style="margin-left: 150px; font-size: 24px;">
                <div style="margin-bottom: 240px;">{int(max_count):,} trips</div>
                <div style="margin-bottom: 8px;">{int(min_count):,} trips</div>
            </div>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

def save_static_image(road_usage, output_path):
    """Create a static image by taking a screenshot of the HTML map"""
    try:
        print("Setting up Chrome for screenshot...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=2160,4096")
        chrome_options.add_argument("--hide-scrollbars")
        chrome_options.add_argument("--force-device-scale-factor=1")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        screenshot_html = os.path.join(OUTPUT_DIR, "road_usage_heatmap_screenshot.html")
        print(f"Loading HTML map from: {screenshot_html}")
        driver.get(f"file://{os.path.abspath(screenshot_html)}")
        
        print("Waiting for map to load...")
        time.sleep(8)
        
        print("Taking screenshot...")
        driver.save_screenshot(output_path)
        
        # Get file size and compress if needed
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Screenshot saved. File size: {size_mb:.2f} MB")
        
        if size_mb > 5:
            from PIL import Image
            img = Image.open(output_path)
            img.save(output_path, 'JPEG', quality=85, optimize=True)
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"Compressed image saved. New file size: {size_mb:.2f} MB")
        
        driver.quit()
        print("Screenshot completed successfully")
        
    except Exception as e:
        print(f"Error creating screenshot: {str(e)}")
        if 'driver' in locals():
            driver.quit()

def main():
    print("\nStarting road usage visualization...")
    road_usage = load_road_usage()
    print(f"Processing {len(road_usage)} road segments")
    
    try:
        # Create regular heatmap for web viewing
        m = create_regular_heatmap(road_usage)
        output_file = os.path.join(OUTPUT_DIR, "road_usage_heatmap.html")
        m.save(output_file)
        print(f"\nRegular heatmap saved to: {output_file}")
        
        # Create separate heatmap with large legend for screenshot
        m_screenshot = create_screenshot_heatmap(road_usage)
        screenshot_html = os.path.join(OUTPUT_DIR, "road_usage_heatmap_screenshot.html")
        m_screenshot.save(screenshot_html)
        print(f"Screenshot HTML saved to: {screenshot_html}")
        
        # Create static image from the screenshot version
        output_image = os.path.join(OUTPUT_DIR, "road_usage_heatmap.png")
        save_static_image(road_usage, output_image)
        print(f"Screenshot saved to: {output_image}")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
