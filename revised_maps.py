import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
import os
import branca.colormap as cm
import numpy as np
from scipy import stats

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
    zones_with_data = zones.merge(metro_trips, left_on='YISHUV_STAT11', right_on='tract', how='right')
    zones_with_data['total_trips'] = zones_with_data['total_trips'].fillna(0)

    # Filter out zones with no trips
    zones_with_trips = zones_with_data[zones_with_data['total_trips'] > 0].copy()

    print(f"Total zones: {len(zones_with_data)}")
    print(f"Zones with trips: {len(zones_with_trips)}")

    # Apply logarithmic transformation to trip counts
    zones_with_trips['log_trips'] = np.log1p(zones_with_trips['total_trips'])
    
    # Cap log-transformed trip counts at 95th percentile
    log_trip_cap = zones_with_trips['log_trips'].quantile(0.95)
    zones_with_trips['log_trips_capped'] = zones_with_trips['log_trips'].clip(upper=log_trip_cap)

    print(f"Symbology approach for {poi_info['name']}:")
    print(f"Mean trips: {zones_with_trips['total_trips'].mean():.2f}")
    print(f"Median trips: {zones_with_trips['total_trips'].median():.2f}")
    
    print(f"Trip count distribution:")
    print(zones_with_trips['total_trips'].describe(percentiles=[.25, .5, .75, .95]))
    print(f"Log-transformed trip count distribution:")
    print(zones_with_trips['log_trips'].describe(percentiles=[.25, .5, .75, .95]))
    print(f"95th percentile log trip count (cap value): {log_trip_cap:.2f}")

    # Use a white to blue color scheme
    colors = ['#ffffff', '#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#4292c6', '#2171b5', '#084594']
    
    # Create color map with log-transformed and capped trip count scale
    colormap = cm.LinearColormap(colors=colors,
                                 vmin=zones_with_trips['log_trips_capped'].min(),
                                 vmax=zones_with_trips['log_trips_capped'].max())
    
    # Create the map
    m = folium.Map(location=[31.25, 34.8], zoom_start=11)
    
    # Calculate total average percent for car and work
    total_trips = zones_with_trips['total_trips'].sum()
    total_avg_percent_car = (zones_with_trips['total_trips'] * zones_with_trips['percent_car']).sum() / total_trips
    total_avg_percent_work = (zones_with_trips['total_trips'] * zones_with_trips['percent_work']).sum() / total_trips
    
    print(f"Total average percent car: {total_avg_percent_car:.2f}%")
    print(f"Total average percent work: {total_avg_percent_work:.2f}%")
    
    # Define style function
    def style_function(feature):
        trips = feature['properties']['total_trips']
        if trips == 0:
            return {'fillColor': 'transparent', 'fillOpacity': 0, 'color': 'grey', 'weight': 1}
        else:
            log_trips = np.log1p(trips)
            capped_log_trips = min(log_trips, log_trip_cap)
            color = colormap(capped_log_trips)
            return {'fillColor': color, 'fillOpacity': 0.7, 'color': 'black', 'weight': 1}
    
    # Add GeoJSON layer
    folium.GeoJson(
        zones_with_trips,
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(fields=['STAT11', 'total_trips', 'percent_car', 'percent_work'],
                                      aliases=['Statistical Area', 'Total Trips', '% Car', '% Work'],
                                      localize=True,
                                      labels=True,
                                      sticky=False)
    ).add_to(m)
    
    # Add colormap to the map
    colormap.add_to(m)
    
    # Customize colormap legend with actual trip counts
    tick_values = np.linspace(zones_with_trips['log_trips_capped'].min(), zones_with_trips['log_trips_capped'].max(), 6)
    tick_labels = [f"{np.expm1(v):.0f}" for v in tick_values]
    colormap.caption = f'Number of Trips (log scale, capped at 95th percentile)'
    colormap.tick_labels = tick_labels
    
    # Add legend for trip summary and averages
    legend_html = f'''
    <div style="position: fixed; 
                bottom: 50px; 
                left: 50px; 
                width: 280px; 
                height: 160px; 
                border:2px solid grey; 
                z-index:9999; 
                font-size:14px; 
                background-color:white;
                padding: 8px;
                border-radius: 6px;
                box-shadow: 0 0 15px rgba(0,0,0,0.2);
                ">
        <b>Trip Summary:</b><br>
        Trips within metro: {total_metro_trips:.0f}<br>
        Trips from/to outside: {total_outside_trips:.0f}<br>
        Total trips: {total_trips:.0f}<br>
        Avg trips per zone: {zones_with_trips['total_trips'].mean():.1f}<br>
        Avg % Car: {total_avg_percent_car:.1f}%<br>
        Avg % Work: {total_avg_percent_work:.1f}%
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