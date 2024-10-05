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
    print(f"\nCreating map for POI: {poi_info['name']} (ID: {poi_id})")
    
    # Ensure tract is string type in both dataframes
    zones['YISHUV_STAT11'] = zones['YISHUV_STAT11'].astype(str)
    trip_data['tract'] = trip_data['tract'].astype(str)
    
    # Merge trip data with zones based on YISHUV_STAT11 and tract
    zones_with_data = zones.merge(trip_data, left_on='YISHUV_STAT11', right_on='tract', how='left')
    zones_with_data['total_trips'] = zones_with_data['total_trips'].fillna(0)
    
    print(f"Number of zones with trip data: {len(zones_with_data[zones_with_data['total_trips'] > 0])}")
    
    # Create map centered on POI
    m = folium.Map(location=[poi_info['lat'], poi_info['lon']], zoom_start=11)
    
    # Calculate 95th percentile for color scale
    max_trips = np.percentile(zones_with_data['total_trips'][zones_with_data['total_trips'] > 0], 95)
    
    # Create color map
    colormap = cm.LinearColormap(colors=['#FEF0D9', '#FDD49E', '#FDBB84', '#FC8D59', '#EF6548', '#D7301F'],
                                 vmin=1,  # Start from 1 to exclude 0 trips
                                 vmax=max_trips)
    m.add_child(colormap)
    
    # Create a style function to handle zero trips
    def style_function(feature):
        trips = feature['properties']['total_trips']
        if trips == 0:
            return {'fillColor': 'transparent', 'fillOpacity': 0, 'color': 'grey', 'weight': 1}
        else:
            return {'fillColor': colormap(trips), 'fillOpacity': 0.7, 'color': 'black', 'weight': 1}
    
    # Add choropleth layer
    folium.GeoJson(
        zones_with_data.to_json(),
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(fields=['YISHUV_STAT11', 'total_trips'],
                                      aliases=['YISHUV_STAT11:', 'Total Trips:'],
                                      localize=True)
    ).add_to(m)
    
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
            <b>Total Trips:</b> {row['total_trips']:.0f}<br>
            <b>Percent Frequent:</b> {row['percent_frequent']:.1f}%<br>
            <b>Percent Car:</b> {row['percent_car']:.1f}%<br>
            <b>Percent Work:</b> {row['percent_work']:.1f}%
            """
            folium.Marker(
                location=[row.geometry.centroid.y, row.geometry.centroid.x],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.DivIcon(html=f"<div style='font-size: 10pt'>{row['total_trips']:.0f}</div>")
            ).add_to(marker_cluster)
    
    # Add outside trips information
    outside_trips = trip_data[trip_data['tract'] == '000000']['total_trips'].sum()
    outside_trips_html = f"""
    <h4>Outside Trips</h4>
    <p>Total trips from outside the Beer Sheva metropolitan area: {outside_trips:.0f}</p>
    """
    m.get_root().html.add_child(folium.Element(outside_trips_html))
    
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
        # Load trip data for this POI
        inbound_file = os.path.join(base_dir, 'output/processed_poi_data', f"{poi_info['name'].replace(' ', '_')}_inbound_trips.csv")
        outbound_file = os.path.join(base_dir, 'output/processed_poi_data', f"{poi_info['name'].replace(' ', '_')}_outbound_trips.csv")
        
        if os.path.exists(inbound_file) and os.path.exists(outbound_file):
            inbound_trips = pd.read_csv(inbound_file)
            outbound_trips = pd.read_csv(outbound_file)
            
            # Combine inbound and outbound trips
            trip_data = pd.concat([inbound_trips, outbound_trips])
            
            # Group by tract and sum the trips
            trip_summary = trip_data.groupby('tract').agg({
                'total_trips': 'sum',
                'percent_frequent': 'mean',
                'percent_car': 'mean',
                'percent_work': 'mean'
            }).reset_index()
            
            print(f"\nProcessed data for {poi_info['name']}:")
            print(trip_summary.head())
            
            m = create_poi_map(poi_id, poi_info, trip_summary, zones)
            
            # Save the map
            map_filename = f"{poi_info['name'].replace(' ', '_')}_map.html"
            m.save(os.path.join(output_dir, map_filename))
            print(f"Map saved: {map_filename}")
        else:
            print(f"Trip data files not found for {poi_info['name']}. Skipping map creation.")

    print("All POI maps have been generated and saved in the output directory.")