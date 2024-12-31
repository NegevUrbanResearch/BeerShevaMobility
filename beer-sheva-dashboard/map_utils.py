# Mapping functions
import plotly.graph_objs as go
import numpy as np
import logging
import traceback
import os
import plotly.io as pio
from config import OUTPUT_DIR
from utils.zone_utils import (
    standardize_zone_ids, 
    analyze_zone_ids,
    is_valid_zone_id,
    get_zone_type,
    ZONE_FORMATS
)
from utils.data_standards import DataStandardizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MapCreator:
    def __init__(self, color_scheme):
        self.color_scheme = {
            'Very High (95th+ percentile)': '#bd0026',
            'High (75th-95th percentile)': '#fc4e2a',
            'Moderate (50th-75th percentile)': '#feb24c',
            'Low (25th-50th percentile)': '#ffeda0',
            'Very Low (0-25th percentile)': '#ffffcc'
        }

    def assign_categories(self, values):
        """Assign categories based on percentiles"""
        percentiles = {
            95: np.percentile(values, 95),
            75: np.percentile(values, 75),
            50: np.percentile(values, 50),
            25: np.percentile(values, 25),
            0: np.min(values)
        }
        
        def get_category(x):
            if x >= percentiles[95]:
                return 'Very High (95th+ percentile)'
            elif x >= percentiles[75]:
                return 'High (75th-95th percentile)'
            elif x >= percentiles[50]:
                return 'Moderate (50th-75th percentile)'
            elif x >= percentiles[25]:
                return 'Low (25th-50th percentile)'
            else:
                return 'Very Low (0-25th percentile)'
        
        categories = [get_category(x) for x in values]
        return categories, percentiles

    def filter_and_clip_zones(self, zones, trip_data):
        logger.info(f"Number of zones before filtering: {len(zones)}")
        
        # Use 'tract' column
        tract_col = 'tract'
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
    
    def create_map(self, df, selected_poi, trip_type, zones, poi_coordinates):
        logger.info(f"Creating map for POI: {selected_poi}, Trip Type: {trip_type}")
        
        try:
            # Standardize the selected POI name
            standard_poi = DataStandardizer.standardize_poi_name(selected_poi)
            
            if standard_poi not in poi_coordinates:
                logger.error(f"POI '{standard_poi}' (standardized from '{selected_poi}') not found in coordinates.")
                logger.error(f"Available POIs: {list(poi_coordinates.keys())}")
                return go.Figure()
            
            center_lat, center_lon = poi_coordinates[standard_poi]
            
            # Debug input data
            logger.info("\nInput data format:")
            logger.info(f"Trip data columns: {df.columns.tolist()}")
            
            # Use 'tract' column instead of from/to_tract
            tract_col = 'tract'
            logger.info(f"Trip data {tract_col} samples:\n{df[tract_col].head()}")
            
            # Aggregate trips by tract using total_trips column
            df_aggregated = df.groupby(tract_col)['total_trips'].sum().reset_index()
            logger.info(f"\nAggregated trip counts:")
            logger.info(f"Original shape: {df.shape}")
            logger.info(f"Aggregated shape: {df_aggregated.shape}")
            
            # Ensure consistent formatting
            df_aggregated = standardize_zone_ids(df_aggregated, [tract_col])
            zones = standardize_zone_ids(zones, ['YISHUV_STAT11'])
            
            # Rename column to match the rest of the code
            df_aggregated = df_aggregated.rename(columns={'total_trips': 'count'})
            
            # Filter and clip zones
            filtered_zones = self.filter_and_clip_zones(zones, df_aggregated)
            
            if len(filtered_zones) == 0:
                logger.warning("No zones with trips found")
                return go.Figure()

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

            trip_counts = zones_with_trips['count']
            percentiles = {
                0: trip_counts.min(),
                5: trip_counts.quantile(0.05),
                20: trip_counts.quantile(0.20),
                40: trip_counts.quantile(0.40),
                60: trip_counts.quantile(0.60),
                80: trip_counts.quantile(0.80),
                95: trip_counts.quantile(0.95),
                100: trip_counts.max()
            }

            def get_category_value(x):
                if x >= percentiles[95]:
                    return 5
                elif x >= percentiles[80]:
                    return 4
                elif x >= percentiles[60]:
                    return 3
                elif x >= percentiles[40]:
                    return 2
                elif x >= percentiles[20]:
                    return 1
                else:
                    return 0

            zones_with_trips['category_value'] = zones_with_trips['count'].apply(get_category_value)

            fig = go.Figure(go.Choroplethmapbox(
                geojson=zones_with_trips.__geo_interface__,
                locations=zones_with_trips.index,
                z=zones_with_trips['category_value'],
                colorscale=[
                    [0.0, '#7c1d6f'],
                    [0.167, '#7c1d6f'],  # Very Low
                    [0.167, '#dc3977'],
                    [0.333, '#dc3977'],  # Moderate-Low
                    [0.333, '#e34f6f'],
                    [0.5, '#e34f6f'],    # Moderate
                    [0.5, '#f0746e'],
                    [0.667, '#f0746e'],  # Moderate-High
                    [0.667, '#faa476'],
                    [0.833, '#faa476'],  # High
                    [0.833, '#fcde9c'],
                    [1.0, '#fcde9c']     # Very High
                ],
                showscale=False,
                marker_opacity=0.8,
                marker_line_width=0,
                zmin=0,
                zmax=5,
                hovertemplate=(
                    '<b>Zone:</b> %{location}<br>' +
                    '<b>Trips:</b> %{customdata:,.0f}<br>' +
                    '<extra></extra>'
                ),
                customdata=zones_with_trips['count']
            ))

            # Add legend entries (reversed order to show brightest on top)
            legend_items = [
                (f'{percentiles[95]:.0f}+ trips', '#fcde9c', 95),
                (f'{percentiles[80]:.0f}-{percentiles[95]:.0f} trips', '#faa476', 80),
                (f'{percentiles[60]:.0f}-{percentiles[80]:.0f} trips', '#f0746e', 60),
                (f'{percentiles[40]:.0f}-{percentiles[60]:.0f} trips', '#e34f6f', 40),
                (f'{percentiles[20]:.0f}-{percentiles[40]:.0f} trips', '#dc3977', 20),
                (f'0-{percentiles[20]:.0f} trips', '#7c1d6f', 0)
            ]

            for category, color, _ in legend_items:
                fig.add_trace(go.Scattermapbox(
                    lat=[None],
                    lon=[None],
                    mode='markers',
                    marker=dict(size=15, color=color),
                    name=category,
                    showlegend=True
                ))

            # Add POI markers
            for poi, coords in poi_coordinates.items():
                is_selected = poi == selected_poi
                fig.add_trace(go.Scattermapbox(
                    lat=[coords[0]],
                    lon=[coords[1]],
                    mode='markers',
                    marker=go.scattermapbox.Marker(
                        size=20,
                        color='red' if is_selected else 'yellow',
                        symbol='circle',
                    ),
                    text=[poi],
                    hoverinfo='text',
                    showlegend=False,
                    customdata=[poi],
                ))

            # Set the center and zoom based on the selected POI
            center_lat, center_lon = poi_coordinates[selected_poi]

            # Update the layout configuration
            fig.update_layout(
                mapbox_style="carto-darkmatter",
                mapbox=dict(
                    center=dict(lat=center_lat, lon=center_lon),
                    zoom=10
                ),
                margin={"r":0,"t":0,"l":0,"b":0},
                font=dict(size=36, color="white"),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=600,
                autosize=True,
                showlegend=True,
                legend=dict(
                    yanchor="bottom",
                    y=0.01,
                    xanchor="left",
                    x=0.01,
                    bgcolor="rgba(0,0,0,0.8)",
                    bordercolor="rgba(255,255,255,0.3)",
                    borderwidth=1,
                    font=dict(size=21, color="white"),
                    itemsizing='constant'
                )
            )

            # Update hover label font size
            for trace in fig.data:
                if isinstance(trace, go.Scattermapbox):
                    trace.hoverlabel = dict(font=dict(size=30))

            return fig

        except Exception as e:
            logger.error(f"Error in create_map: {str(e)}")
            logger.error(traceback.format_exc())
            return go.Figure()

    def filter_and_clip_zones(self, zones, trip_data):
        logger.info(f"Number of zones before filtering: {len(zones)}")
        
        # Use 'tract' column
        tract_col = 'tract'
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
    
    # Clean POI names in both POI data and trip data
    poi_df, trip_data = loader.clean_poi_names(poi_df, trip_data)
    
    # Debug available POIs and trip types
    print("\nAvailable POI-trip type combinations:")
    for key in trip_data.keys():
        print(f"- {key[0]} ({key[1]})")
    
    # Use the first available POI-trip combination
    if not trip_data:
        raise ValueError("No trip data available")
    
    first_key = list(trip_data.keys())[0]
    test_poi, test_trip_type = first_key
    print(f"\nTesting with POI: {test_poi}, Trip type: {test_trip_type}")
    
    test_df = trip_data[first_key]
    
    # Create map
    map_creator = MapCreator(COLOR_SCHEME)
    
    # Create a dictionary of all POI coordinates with standardized naming
    all_poi_coordinates = dict(zip(
        poi_df['name'].apply(DataStandardizer.standardize_poi_name),
        zip(poi_df['lat'], poi_df['lon'])
    ))
    
    print("\nAvailable POI coordinates (standardized):")
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