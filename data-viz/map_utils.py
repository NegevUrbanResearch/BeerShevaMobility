# Mapping functions
import plotly.graph_objs as go
import numpy as np
import logging
import traceback

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MapCreator:
    def __init__(self, color_scheme):
        self.color_scheme = color_scheme

    def create_map(self, df, selected_poi, trip_type, zones, poi_coordinates):
        logger.info(f"Creating map for POI: {selected_poi}, Trip Type: {trip_type}")
        
        try:
            # Convert tract and YISHUV_STAT11 to strings
            df['tract'] = df['tract'].astype(str)
            zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].astype(str)

            # Filter and clip zones
            filtered_zones = self.filter_and_clip_zones(zones, df)

            if len(filtered_zones) == 0:
                logger.warning("No zones with trips found")
                return go.Figure()

            # Merge trip data with filtered zones
            zones_with_data = filtered_zones.merge(df, left_on='YISHUV_STAT11', right_on='tract', how='left')
            zones_with_data['total_trips'] = zones_with_data['total_trips'].fillna(0)

            # Filter out zones with no trips
            zones_with_trips = zones_with_data[zones_with_data['total_trips'] > 0].copy()

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
            zones_with_trips['log_trips'] = np.log1p(zones_with_trips['total_trips'])
            
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
                hovertemplate='<b>Area:</b> %{location}<br><b>Trips:</b> %{customdata:.0f}<extra></extra>',
                customdata=zones_with_trips['total_trips'],
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
        logger.info(f"Number of unique tract values in trip_data: {len(trip_data['tract'].unique())}")

        # Filter zones to only those with trip data
        filtered_zones = zones[zones['YISHUV_STAT11'].isin(trip_data['tract'])]
        
        logger.info(f"Number of zones after filtering: {len(filtered_zones)}")
        
        if len(filtered_zones) == 0:
            logger.warning("No matching zones found after filtering")
            return filtered_zones

        # Clip the geometry to the extent of the filtered zones
        total_bounds = filtered_zones.total_bounds
        filtered_zones = filtered_zones.clip(total_bounds)
        
        logger.info(f"Number of zones after clipping: {len(filtered_zones)}")
        
        return filtered_zones

def test_map_creator():
    from data_loader import DataLoader
    from config import BASE_DIR, OUTPUT_DIR, COLOR_SCHEME
    
    loader = DataLoader(BASE_DIR, OUTPUT_DIR)
    zones = loader.load_zones()
    poi_df = loader.load_poi_data()
    trip_data = loader.load_trip_data()
    
    map_creator = MapCreator(COLOR_SCHEME)
    
    # Test with the first POI and trip type
    test_poi = poi_df['name'].iloc[0]
    test_trip_type = 'inbound'
    test_df = trip_data[(test_poi, test_trip_type)]

    # Create a dictionary of all POI coordinates
    all_poi_coordinates = dict(zip(poi_df['name'], zip(poi_df['lat'], poi_df['lon'])))
    
    fig = map_creator.create_map(test_df, test_poi, test_trip_type, zones, all_poi_coordinates)
    
    # Save the test map
    import plotly.io as pio
    pio.write_html(fig, file='test_map.html', auto_open=True)
    print("Test map saved as 'test_map.html'")

if __name__ == "__main__":
    test_map_creator()