import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
import os
import branca.colormap as cm
import numpy as np

def load_poi_locations(csv_file):
    try:
        poi_df = pd.read_csv(csv_file)
        print(f"Loaded {len(poi_df)} POIs from the CSV file.")
        return poi_df.set_index('ID').to_dict(orient='index')
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return {}

def create_poi_map(poi_id, poi_info, trip_data, zones):
    print(f"\nCreating inbound map for POI: {poi_info['name']} (ID: {poi_id})")
    
    # Load trips info
    trips_info_file = os.path.join(base_dir, 'output/processed_poi_data', f"{poi_info['name'].replace(' ', '_')}_inbound_trips_info.csv")
    trips_info = pd.read_csv(trips_info_file)
    
    # Ensure tract is string type in both dataframes
    zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].astype(str)
    trip_data['tract'] = trip_data['tract'].astype(str)
    
    # Separate metro and outside trips
    metro_trips = trip_data[trip_data['tract'] != '000000']
    outside_trips = trip_data[trip_data['tract'] == '000000']

    # Get total trips from trips_info
    total_trips = trips_info['total_trips'].iloc[0]
    total_metro_trips = trips_info['metro_trips'].iloc[0]
    total_outside_trips = trips_info['outside_trips'].iloc[0]

    print(f"Total trips: {total_trips}")
    print(f"Total metro trips: {total_metro_trips}")
    print(f"Total outside trips: {total_outside_trips}")

    # Merge trip data with zones
    zones_with_data = zones.merge(metro_trips, left_on='YISHUV_STAT11', right_on='tract', how='left')
    zones_with_data['total_trips'] = zones_with_data['total_trips'].fillna(0)

    # Calculate log-transformed trip counts
    zones_with_data['log_trips'] = np.log1p(zones_with_data['total_trips'])
    
    # Calculate max value for color scale (using log-transformed data)
    max_log_trips = zones_with_data['log_trips'].max()
    
    print(f"\nMax log trips: {max_log_trips}")
    
    # Create color map with logarithmic scale
    colormap = cm.LinearColormap(colors=['#FEF0D9', '#FDD49E', '#FDBB84', '#FC8D59', '#EF6548', '#D7301F'],
                                 vmin=0,
                                 vmax=max_log_trips)
    
    # Create the map
    m = folium.Map(location=[31.25, 34.8], zoom_start=11)
    
    # Define style function
    def style_function(feature):
        trips = feature['properties']['total_trips']
        log_trips = np.log1p(trips)
        if trips == 0:
            return {'fillColor': 'transparent', 'fillOpacity': 0, 'color': 'grey', 'weight': 1}
        else:
            return {'fillColor': colormap(log_trips), 'fillOpacity': 0.7, 'color': 'black', 'weight': 1}
    
    
    # Add GeoJSON layer
    folium.GeoJson(
        zones_with_data,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(fields=['STAT11', 'total_trips'],
                                      aliases=['Statistical Area', 'Total Trips'],
                                      localize=True)
    ).add_to(m)
    
    # Add colormap to the map
    colormap.add_to(m)
    
    # Customize colormap legend
    colormap.caption = f'Number of Trips (log scale)'
    
    # Add legend for metro and outside trips
    legend_html = f'''
    <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 90px; 
                border:2px solid grey; z-index:9999; font-size:14px; background-color:white;
                ">&nbsp;<b>Trip Summary:</b><br>
    &nbsp;Trips within metro: {total_metro_trips}<br>
    &nbsp;Trips from/to outside: {total_outside_trips}<br>
    &nbsp;Total trips: {total_trips}
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Add POI marker
    folium.Marker(
        location=[poi_info['lat'], poi_info['lon']],
        popup=poi_info['name'],
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)
    
    # Add markers for trip counts
    marker_cluster = MarkerCluster().add_to(m)
    for idx, row in zones_with_data.iterrows():
        if pd.notna(row.geometry) and row['total_trips'] > 0:
            popup_html = f"""
            <b>YISHUV_STAT11:</b> {row['YISHUV_STAT11']}<br>
            <b>Total Inbound Trips:</b> {row['total_trips']:.0f}<br>
            <b>Percent Frequent:</b> {row['percent_frequent']:.1f}%<br>
            <b>Percent Car:</b> {row['percent_car']:.1f}%<br>
            <b>Percent Work:</b> {row['percent_work']:.1f}%
            """
            folium.Marker(
                location=[row.geometry.centroid.y, row.geometry.centroid.x],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.DivIcon(html=f"<div style='font-size: 10pt'>{row['total_trips']:.0f}</div>")
            ).add_to(marker_cluster)
    
    return m

# Main execution
if __name__ == "__main__":
    print("Loading data...")
    # File paths
    base_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
    poi_locations_file = os.path.join(base_dir, 'output/processed_poi_data/poi_with_exact_coordinates.csv')
    zones_file = os.path.join(base_dir, 'output/processed_poi_data/zones.geojson')
    output_dir = os.path.join(base_dir, 'output', 'poi_maps')
    os.makedirs(output_dir, exist_ok=True)

    # Load POI locations
    poi_locations = load_poi_locations(poi_locations_file)

    # Load zones data
    zones = gpd.read_file(zones_file)
    zones = zones.to_crs(epsg=4326)

    print(f"Loaded {len(zones)} zones")

    # Create maps for all POIs
    for poi_id, poi_info in poi_locations.items():
        # Load inbound trip data for this POI
        inbound_file = os.path.join(base_dir, 'output/processed_poi_data', f"{poi_info['name'].replace(' ', '_')}_inbound_trips.csv")
        
        if os.path.exists(inbound_file):
            inbound_trips = pd.read_csv(inbound_file)
            
            print(f"\nProcessed inbound data for {poi_info['name']}:")
            print(inbound_trips.head())
            
            m = create_poi_map(poi_id, poi_info, inbound_trips, zones)
            
            # Save the map
            map_filename = f"{poi_info['name'].replace(' ', '_')}_inbound_map.html"
            m.save(os.path.join(output_dir, map_filename))
            print(f"Inbound map saved: {map_filename}")
        else:
            print(f"Inbound trip data file not found for {poi_info['name']}. Skipping map creation.")

    print("All POI inbound maps have been generated and saved in the output directory.")