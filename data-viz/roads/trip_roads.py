import pydeck as pdk
import pandas as pd
import geopandas as gpd
import numpy as np
from datetime import datetime
import os
import sys
# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
from config import MAPBOX_API_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR

def load_trip_data():
    """Load the trip data and convert to format needed for TripLayer"""
    file_path = os.path.join(OUTPUT_DIR, "road_usage_trips.geojson")
    trips_gdf = gpd.read_file(file_path)
    
    logger.info(f"Loading {len(trips_gdf)} trips")
    
    # Get bounds for view state
    bounds = trips_gdf.total_bounds
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2
    
    # Process all trips
    trip_data = []
    min_time = pd.to_datetime(trips_gdf['departure_time'].min())
    max_time = pd.to_datetime(trips_gdf['departure_time'].max())
    
    # Calculate time scaling factor (compress 3 hours into 30 seconds)
    time_scale = 30.0 / (3 * 3600)  # 30 seconds / 3 hours
    
    for _, row in trips_gdf.iterrows():
        try:
            coords = list(row.geometry.coords)
            if not coords or len(coords) < 2:
                continue
                
            # Validate coordinates
            if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in coords):
                continue
            
            # Scale the times to fit in 30 seconds
            start_time = pd.to_datetime(row['departure_time'])
            end_time = pd.to_datetime(row['arrival_time'])
            
            start_seconds = (start_time - min_time).total_seconds() * time_scale
            end_seconds = start_seconds + (end_time - start_time).total_seconds() * time_scale
            
            # Create timestamps that ensure smooth movement along the route
            timestamps = np.linspace(start_seconds, end_seconds, len(coords))
            
            trip_data.append({
                "coordinates": [[float(x), float(y)] for x, y in coords],
                "timestamps": timestamps.tolist()
            })
            
        except Exception as e:
            logger.debug(f"Error processing trip: {str(e)}")
            continue
    
    logger.info(f"Processed {len(trip_data)} trips successfully")
    return pd.DataFrame(trip_data), center_lat, center_lon

def create_trip_layer():
    """Create a deck.gl visualization with TripLayer"""
    trips_df, center_lat, center_lon = load_trip_data()
    
    layer = pdk.Layer(
        "TripsLayer",
        trips_df,
        get_path="coordinates",
        get_timestamps="timestamps",
        get_color=[255, 140, 0],  # Bright orange color
        opacity=1.0,  # Increased opacity
        width_min_pixels=4,  # Increased width
        width_scale=2,  # Scale up the width
        rounded=True,
        trail_length=300,  # Much longer trail
        current_time=0,
        pickable=True,
        auto_highlight=True
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=11,
        pitch=45,  # Angled view
        bearing=0
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style='dark',
        parameters={
            "animate": True
        }
    )

    # Add JavaScript animation code
    deck.update_string = """
        function animate() {
            const loopLength = 30000;  // 30 seconds
            const animationSpeed = 1;
            const timestamp = Date.now() / 1000;
            const loopTime = loopLength / animationSpeed;
            const time = ((timestamp % loopTime) / loopTime) * loopLength;
            deck.setProps({
                layers: [
                    new TripsLayer({
                        ...deck.props.layers[0].props,
                        currentTime: time
                    })
                ]
            });
            window.requestAnimationFrame(animate);
        }
        animate();
    """

    return deck

def main():
    logger.info("Starting trip visualization creation...")
    try:
        deck = create_trip_layer()
        output_path = os.path.join(OUTPUT_DIR, "trip_visualization.html")
        deck.to_html(output_path)  # Simplified HTML generation
        logger.info(f"Visualization saved to: {output_path}")
        
    except Exception as e:
        logger.error(f"Error creating visualization: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 