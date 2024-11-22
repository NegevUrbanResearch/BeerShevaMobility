# Mapping functions
import plotly.graph_objs as go
import numpy as np
import logging
import traceback
import os
import plotly.io as pio

from utils.zone_utils import (
    standardize_zone_ids, 
    analyze_zone_ids,
    is_valid_zone_id,
    get_zone_type,
    ZONE_FORMATS
)
from config import (
    BASE_DIR, OUTPUT_DIR, COLOR_SCHEME,
    PROCESSED_DIR, FINAL_ZONES_FILE
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MapCreator:
    def __init__(self, color_scheme):
        self.color_scheme = color_scheme

    def create_map(self, df, selected_poi, trip_type, zones, poi_coordinates):
        logger.info(f"Creating map for POI: {selected_poi}, Trip Type: {trip_type}")
        
        try:
            # Debug input data
            logger.info("\nInput data format:")
            logger.info(f"Trip data columns: {df.columns.tolist()}")
            
            # Use correct column names
            tract_col = 'to_tract' if trip_type == 'inbound' else 'from_tract'
            logger.info(f"Trip data {tract_col} samples:\n{df[tract_col].head()}")
            
            # Aggregate trips by tract before merging
            df_aggregated = df.groupby(tract_col)['count'].sum().reset_index()
            logger.info(f"\nAggregated trip counts:")
            logger.info(f"Original shape: {df.shape}")
            logger.info(f"Aggregated shape: {df_aggregated.shape}")
            
            # Ensure consistent formatting
            df_aggregated = standardize_zone_ids(df_aggregated, [tract_col])
            zones = standardize_zone_ids(zones, ['YISHUV_STAT11'])
            
            # Filter and clip zones
            filtered_zones = self.filter_and_clip_zones(zones, df_aggregated)
            
            if len(filtered_zones) == 0:
                logger.warning("No zones with trips found")
                return go.Figure()

            # Debug merge fields
            logger.info("\nMerge fields unique values:")
            logger.info(f"df['{tract_col}'] types: {[get_zone_type(z) for z in df_aggregated[tract_col].unique()[:5]]}")
            logger.info(f"zones['YISHUV_STAT11'] types: {[get_zone_type(z) for z in filtered_zones['YISHUV_STAT11'].unique()[:5]]}")

            # Merge trip data with filtered zones
            zones_with_data = filtered_zones.merge(
                df_aggregated, 
                left_on='YISHUV_STAT11',
                right_on=tract_col,
                how='left',
                validate='1:1'
            )
            
            # Debug merge results
            logger.info("\nMerge results:")
            logger.info(f"Zones before merge: {len(filtered_zones)}")
            logger.info(f"Zones after merge: {len(zones_with_data)}")
            logger.info(f"Successful matches: {len(zones_with_data[zones_with_data['count'].notna()])}")
            
            zones_with_data['count'] = zones_with_data['count'].fillna(0)
            
            # Filter out zones with no trips
            zones_with_trips = zones_with_data[zones_with_data['count'] > 0].copy()

            if len(zones_with_trips) == 0:
                logger.warning("No zones with trips found after filtering")
                return go.Figure()

            # Check and transform CRS if necessary
            if zones_with_trips.crs is None or zones_with_trips.crs.to_epsg() != 4326:
                logger.info(f"Current CRS: {zones_with_trips.crs}")
                zones_with_trips = zones_with_trips.to_crs(epsg=4326)
                logger.info(f"Transformed CRS: {zones_with_trips.crs}")

            # Log the bounding box of the data
            bounds = zones_with_trips.total_bounds
            logger.info(f"Data bounds: {bounds}")

            # Apply logarithmic transformation to trip counts
            zones_with_trips['log_trips'] = np.log1p(zones_with_trips['count'])
            
            # Calculate the 95th percentile for log-transformed trip counts
            log_trip_cap = zones_with_trips['log_trips'].quantile(0.95)

            # Apply the cap to log-transformed trip counts
            zones_with_trips['log_trips_capped'] = zones_with_trips['log_trips'].clip(upper=log_trip_cap)

            # Calculate color scale limits
            vmin = np.log1p(1)  # Minimum of 1 trip
            vmax = log_trip_cap

            logger.info(f"Color scale range: {vmin} to {vmax}")

            # Create choropleth map
            fig = go.Figure(go.Choroplethmapbox(
                geojson=zones_with_trips.__geo_interface__,
                locations=zones_with_trips.index,
                z=zones_with_trips['log_trips_capped'],
                colorscale="Viridis",
                zmin=vmin,
                zmax=vmax,
                marker_opacity=0.7,
                marker_line_width=0,
                colorbar=dict(
                    title="Number of Trips",
                    tickmode='array',
                    tickvals=np.linspace(vmin, vmax, 6),  # Position of ticks
                    ticktext=[f"{int(np.expm1(val))}" for val in np.linspace(vmin, vmax, 6)],  # Text to display
                ),
                hovertemplate='<b>Zone:</b> %{location}<br><b>Trips:</b> %{customdata:.0f}<extra></extra>',
                customdata=zones_with_trips['count'],
            ))
            # Add annotation for logarithmic scale
            fig.add_annotation(
                text="*Color intensity uses logarithmic scale",
                xref="paper", yref="paper",
                x=0.95, y=0.04,
                showarrow=False,
                font=dict(size=12, color="white"),
                align="right",
                yanchor='top'
            )

            # Add all POI markers
            for poi, coords in poi_coordinates.items():
                is_selected = poi == selected_poi
                fig.add_trace(go.Scattermapbox(
                    lat=[coords[0]],
                    lon=[coords[1]],
                    mode='markers',
                    marker=go.scattermapbox.Marker(
                        size=15,
                        color='red' if is_selected else 'yellow',  # Yellow for better visibility on dark background
                        symbol='circle',
                    ),
                    text=[poi],
                    hoverinfo='text',
                    showlegend=False,
                    customdata=[poi],
                ))

            # Calculate the bounding box for all POIs
            all_lats = [coords[0] for coords in poi_coordinates.values()]
            all_lons = [coords[1] for coords in poi_coordinates.values()]
            center_lat = (max(all_lats) + min(all_lats)) / 2
            center_lon = (max(all_lons) + min(all_lons)) / 2

            # Set the center and zoom based on the selected POI
            center_lat, center_lon = poi_coordinates[selected_poi]

            fig.update_layout(
                mapbox_style="carto-darkmatter",  # Dark mode style without requiring Mapbox API
                mapbox=dict(
                    center=dict(lat=center_lat, lon=center_lon),
                    zoom=11
                ),
                margin={"r":0,"t":0,"l":0,"b":0},
                height=600,
                title=f'{trip_type.capitalize()} Trips to {selected_poi}',
                font=dict(size=18, color="white"),  # White text for better contrast
                paper_bgcolor="rgba(0,0,0,0)",  # Transparent background
                plot_bgcolor="rgba(0,0,0,0)"  # Transparent background
            )

            fig.update_layout(
                clickmode='event+select'
            )

            return fig
        except Exception as e:
            logger.error(f"Error in create_map: {str(e)}")
            logger.error(traceback.format_exc())
            return go.Figure()

    def filter_and_clip_zones(self, zones, trip_data):
        logger.info(f"Number of zones before filtering: {len(zones)}")
        
        # Get the appropriate tract column based on trip type
        tract_col = 'to_tract' if 'to_tract' in trip_data.columns else 'from_tract'
        logger.info(f"Number of unique {tract_col} values in trip_data: {len(trip_data[tract_col].unique())}")
        
        # Debug zone types before filtering
        trip_zones = trip_data[tract_col].unique()
        zone_types = {zone: get_zone_type(zone) for zone in trip_zones[:5]}
        logger.info(f"Sample trip data zone types: {zone_types}")
        
        # Filter zones to only those with trip data
        filtered_zones = zones[zones['YISHUV_STAT11'].isin(trip_data[tract_col])]
        
        # Analyze filtered zones
        filtered_analysis = analyze_zone_ids(filtered_zones, ['YISHUV_STAT11'])
        logger.info("\nFiltered zones analysis:")
        logger.info(f"City zones: {filtered_analysis['city']}")
        logger.info(f"Statistical areas: {filtered_analysis['statistical']}")
        logger.info(f"Total valid zones: {len(filtered_zones) - len(filtered_analysis['invalid'])}")
        
        if filtered_analysis['invalid']:
            logger.warning(f"Invalid zones found after filtering: {filtered_analysis['invalid'][:5]}")
        
        # Clip the geometry to the extent of the filtered zones
        if len(filtered_zones) > 0:
            total_bounds = filtered_zones.total_bounds
            filtered_zones = filtered_zones.clip(total_bounds)
            logger.info(f"Number of zones after clipping: {len(filtered_zones)}")
        
        return filtered_zones

def test_map_creator():
    """Test the map creator with sample data"""
    from data_loader import DataLoader
    from config import COLOR_SCHEME
    
    # Initialize loader and get data
    loader = DataLoader()
    zones = loader.load_zones()
    poi_df = loader.load_poi_data()
    trip_data = loader.load_trip_data()
    
    # Debug available POIs and trip types
    print("\nAvailable POI-trip type combinations:")
    for key in trip_data.keys():
        print(f"- {key[0]} ({key[1]})")
    
    # Use the first available POI-trip combination instead of hardcoding
    if not trip_data:
        raise ValueError("No trip data available")
    
    first_key = list(trip_data.keys())[0]
    test_poi, test_trip_type = first_key
    print(f"\nTesting with POI: {test_poi}, Trip type: {test_trip_type}")
    
    test_df = trip_data[first_key]
    
    # Create map
    map_creator = MapCreator(COLOR_SCHEME)
    
    # Create a dictionary of all POI coordinates
    all_poi_coordinates = dict(zip(poi_df['name'], zip(poi_df['lat'], poi_df['lon'])))
    print(f"\nAvailable POI coordinates:")
    for poi, coords in all_poi_coordinates.items():
        print(f"- {poi}: {coords}")
    
    # Create and save map
    fig = map_creator.create_map(test_df, test_poi, test_trip_type, zones, all_poi_coordinates)
    
    # Save the test map
    
    output_file = os.path.join(OUTPUT_DIR, 'test_map.html')
    pio.write_html(fig, file=output_file, auto_open=True)
    print(f"\nTest map saved as: {output_file}")

if __name__ == "__main__":
    test_map_creator()