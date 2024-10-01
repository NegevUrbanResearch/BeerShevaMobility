import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
import os
import branca.colormap as cm
import numpy as np
import requests
import time

def geocode_plus_code(plus_code):
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": plus_code,
        "key": "api-key-here"  # Replace with your Google Maps API key
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
    return None

def load_poi_locations(excel_file):
    try:
        poi_df = pd.read_excel(excel_file)
        print(f"Loaded {len(poi_df)} POIs from the Excel file.")
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return {}

    poi_locations = {}
    successful_geocodes = 0
    failed_geocodes = 0

    for _, row in poi_df.iterrows():
        plus_code = row['Plus-Code']
        if "Israel" not in plus_code:
            plus_code += " Israel"
        print(f"\nProcessing POI: {row['Name']} (Plus Code: {plus_code})")
        
        try:
            location = geocode_plus_code(plus_code)
            if location:
                lat, lon = location
                poi_locations[str(row['ID'])] = {
                    'name': row['Name'],
                    'lat': lat,
                    'lon': lon
                }
                print(f"Successfully geocoded: {row['Name']}")
                print(f"  Plus Code: {plus_code}")
                print(f"  Latitude: {lat}, Longitude: {lon}")
                successful_geocodes += 1
            else:
                print(f"Could not geocode Plus Code for {row['Name']}")
                failed_geocodes += 1
        except Exception as e:
            print(f"Error geocoding Plus Code for {row['Name']}: {e}")
            failed_geocodes += 1
        
        time.sleep(0.5)  # Add a small delay between requests to avoid rate limiting

    print(f"\nGeocoding summary:")
    print(f"- Successful geocodes: {successful_geocodes}")
    print(f"- Failed geocodes: {failed_geocodes}")
    print(f"- Total POIs processed: {len(poi_df)}")

    return poi_locations

def create_poi_map(poi_id, poi_info, inbound_trips, outbound_trips, zones):
    print(f"\nCreating map for POI: {poi_info['name']} (ID: {poi_id})")
    
    # Print column names for debugging
    print("Inbound trips columns:", inbound_trips.columns)
    print("Outbound trips columns:", outbound_trips.columns)
    
    # Combine inbound and outbound trips
    inbound_trips['trip_type'] = 'inbound'
    outbound_trips['trip_type'] = 'outbound'
    all_trips = pd.concat([inbound_trips, outbound_trips])
    
    # Calculate outside trips (assuming '0' represents trips from outside)
    outside_trips = all_trips[all_trips['from_tract'] == '0']['total_trips'].sum()
    
    # Remove outside trips from the main dataset
    all_trips = all_trips[all_trips['from_tract'] != '0']
    
    # Group by from_tract and sum the trips
    trip_summary = all_trips.groupby('from_tract').agg({
        'total_trips': 'sum',
        'trip_type': lambda x: ', '.join(set(x))
    }).reset_index()
    
    # Merge trip data with zones based on YISHUV_STAT11 and from_tract
    zones_with_data = zones.merge(trip_summary, left_on='YISHUV_STAT11', right_on='from_tract', how='left')
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
    
    # Ensure YISHUV_STAT11 is included in the GeoJSON properties
    zones_with_data = zones_with_data.to_crs(epsg=4326)
    zones_with_data['YISHUV_STAT11'] = zones_with_data['YISHUV_STAT11'].astype(str)
    
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
            <b>Trip Types:</b> {row['trip_type']}<br>
            """
            folium.Marker(
                location=[row.geometry.centroid.y, row.geometry.centroid.x],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.DivIcon(html=f"<div style='font-size: 10pt'>{row['total_trips']:.0f}</div>")
            ).add_to(marker_cluster)
    
    # Add outside trips information
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
    poi_locations_file = os.path.join(base_dir, 'POI-PlusCode.xlsx')
    zones_file = os.path.join(base_dir, 'statisticalareas_demography2019.gdb')
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
        inbound_file = os.path.join(base_dir, 'output', f"{poi_info['name']}_inbound_trips.csv")
        outbound_file = os.path.join(base_dir, 'output', f"{poi_info['name']}_outbound_trips.csv")
        
        if os.path.exists(inbound_file) and os.path.exists(outbound_file):
            inbound_trips = pd.read_csv(inbound_file)
            outbound_trips = pd.read_csv(outbound_file)
            
            print(f"\nInbound trips for {poi_info['name']}:")
            print(inbound_trips.head())
            print(f"\nOutbound trips for {poi_info['name']}:")
            print(outbound_trips.head())
            
            m = create_poi_map(poi_id, poi_info, inbound_trips, outbound_trips, zones)
            
            # Save the map
            map_filename = f"{poi_info['name'].replace(' ', '_')}_map.html"
            m.save(os.path.join(output_dir, map_filename))
            print(f"Map saved: {map_filename}")
        else:
            print(f"Trip data files not found for {poi_info['name']}. Skipping map creation.")

    print("All POI maps have been generated and saved in the output directory.")