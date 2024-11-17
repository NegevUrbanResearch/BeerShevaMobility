import geopandas as gpd
import pydeck as pdk
import numpy as np
import os
import sys
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_loader import DataLoader
from config import BASE_DIR, OUTPUT_DIR
import logging
from pyproj import Transformer
from shapely.geometry import LineString, Point

logger = logging.getLogger(__name__)

def load_road_usage():
    """Load the road usage data and process geometries"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage.geojson")
    print(f"Loading road usage data from: {file_path}")
    road_usage = gpd.read_file(file_path)
    
    print("\nData Preview:")
    print(f"Number of records: {len(road_usage)}")
    print(f"Columns: {road_usage.columns.tolist()}")
    print(f"CRS: {road_usage.crs}")
    
    # Ensure CRS is WGS84
    if road_usage.crs is None:
        print("Warning: No CRS found, assuming WGS84")
        road_usage.set_crs(epsg=4326, inplace=True)
    elif road_usage.crs.to_epsg() != 4326:
        print(f"Converting from {road_usage.crs} to WGS84")
        road_usage = road_usage.to_crs(epsg=4326)
    
    # Filter out any invalid geometries
    initial_count = len(road_usage)
    road_usage = road_usage[road_usage.geometry.notna()]
    road_usage = road_usage[road_usage.geometry.is_valid]
    if len(road_usage) < initial_count:
        print(f"Filtered out {initial_count - len(road_usage)} invalid geometries")
    
    # Debug coordinate ranges
    coords = np.array([(x, y) for geom in road_usage.geometry 
                      for x, y in geom.coords])
    print("\nCoordinate ranges:")
    print(f"Longitude: {coords[:,0].min():.6f} to {coords[:,0].max():.6f}")
    print(f"Latitude: {coords[:,1].min():.6f} to {coords[:,1].max():.6f}")
    
    # Verify coordinates are in reasonable range for Beer Sheva
    beer_sheva_bounds = {
        'lon_min': 34.7,
        'lon_max': 34.9,
        'lat_min': 31.2,
        'lat_max': 31.3
    }
    
    in_bounds = ((coords[:,0] >= beer_sheva_bounds['lon_min']) & 
                 (coords[:,0] <= beer_sheva_bounds['lon_max']) &
                 (coords[:,1] >= beer_sheva_bounds['lat_min']) &
                 (coords[:,1] <= beer_sheva_bounds['lat_max']))
    
    if not np.all(in_bounds):
        print("\nWarning: Some coordinates outside Beer Sheva bounds!")
        out_of_bounds = coords[~in_bounds]
        print(f"First 5 out-of-bounds coordinates:")
        print(out_of_bounds[:5])
    
    return road_usage

def create_line_layer(road_usage):
    """Create a deck.gl visualization with LineLayer"""
    line_data = []
    
    print("\nProcessing geometries...")
    for idx, row in road_usage.iterrows():
        coords = list(row.geometry.coords)
        for i in range(len(coords) - 1):
            line_data.append({
                'sourcePosition': [float(coords[i][0]), float(coords[i][1])],
                'targetPosition': [float(coords[i+1][0]), float(coords[i+1][1])],
                'count': float(row['count'])
            })
    
    # Calculate min and max counts
    counts = [d['count'] for d in line_data]
    min_count = min(counts)
    max_count = max(counts)
    print(f"\nCount range: {min_count:.2f} to {max_count:.2f}")
    
    return line_data, min_count, max_count

def main():
    print("\nStarting road usage visualization...")
    road_usage = load_road_usage()
    
    # Expand bounds for filtering
    bounds = (34.65, 31.15, 34.95, 31.35)  # minx, miny, maxx, maxy
    road_usage = road_usage.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    print(f"Processing {len(road_usage)} road segments after filtering")
    
    line_data, min_count, max_count = create_line_layer(road_usage)
    
    output_file = os.path.join(OUTPUT_DIR, "road_usage_deck.html")
    
    # Updated HTML wrapper with fixed data handling
    html_content = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="UTF-8">
        <title>Beer Sheva Road Usage</title>
        <script src="https://unpkg.com/@deck.gl/core@8.8.23/dist.min.js"></script>
        <script src="https://unpkg.com/@deck.gl/layers@8.8.23/dist.min.js"></script>
        <style>
          body {{
            margin: 0;
            padding: 0;
            background: #000000;
            overflow: hidden;
          }}
          #deck-container {{
            width: 100vw;
            height: 100vh;
            background: #000000;
            position: fixed;
            top: 0;
            left: 0;
          }}
          .legend {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.8);
            padding: 10px;
            border-radius: 5px;
            color: white;
            font-family: Arial;
          }}
        </style>
      </head>
      <body>
        <div id="deck-container"></div>
        <div class="legend">
          <h3 style="margin: 0 0 10px 0">Traffic Volume</h3>
          <div style="display: flex; align-items: center; margin: 5px 0;">
            <div style="width: 20px; height: 10px; background: rgb(63, 0, 113); margin-right: 10px;"></div>
            <span>Low ({min_count:.0f})</span>
          </div>
          <div style="display: flex; align-items: center; margin: 5px 0;">
            <div style="width: 20px; height: 10px; background: rgb(233, 0, 255); margin-right: 10px;"></div>
            <span>Medium ({(min_count + max_count)/2:.0f})</span>
          </div>
          <div style="display: flex; align-items: center; margin: 5px 0;">
            <div style="width: 20px; height: 10px; background: rgb(255, 0, 0); margin-right: 10px;"></div>
            <span>High ({max_count:.0f})</span>
          </div>
        </div>
        <script type="text/javascript">
          const {{DeckGL, LineLayer}} = deck;

          const data = {line_data};
          const minCount = {min_count};
          const maxCount = {max_count};
          
          new DeckGL({{
            container: 'deck-container',
            initialViewState: {{
              latitude: 31.25,
              longitude: 34.80,
              zoom: 11.5,
              pitch: 45,
              bearing: 0
            }},
            controller: true,
            layers: [
              new LineLayer({{
                id: 'traffic',
                data: data,
                getSourcePosition: d => d.sourcePosition,
                getTargetPosition: d => d.targetPosition,
                getWidth: d => {{
                  const normalized = (d.count - minCount) / (maxCount - minCount);
                  return 1 + normalized * 19;
                }},
                getColor: d => {{
                  const normalized = (d.count - minCount) / (maxCount - minCount);
                  if (normalized < 0.2) return [63, 0, 113, 80];      // Deep purple
                  if (normalized < 0.4) return [123, 0, 221, 120];    // Bright purple
                  if (normalized < 0.6) return [233, 0, 255, 160];    // Pink
                  if (normalized < 0.8) return [255, 51, 51, 200];    // Light red
                  return [255, 0, 0, 255];                            // Bright red
                }},
                pickable: true,
                widthUnits: 'pixels',
                opacity: 0.8
              }})
            ]
          }});
        </script>
      </body>
    </html>
    """
    
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    print(f"\nVisualization saved to: {output_file}")

if __name__ == "__main__":
    main()