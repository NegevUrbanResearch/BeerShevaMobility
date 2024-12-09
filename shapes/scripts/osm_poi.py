import requests
import json
import time
from pathlib import Path
from datetime import datetime

def download_amenities(output_file='shapes/data/output/israel_amenities.geojson'):
    # Overpass API endpoint
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    # Query to get all amenities in Israel
    # Using area filter to restrict to Israel boundaries
    overpass_query = """
    [out:json][timeout:300];
    area["ISO3166-1"="IL"][admin_level=2]->.israel;
    (
      node["amenity"](area.israel);
      way["amenity"](area.israel);
      relation["amenity"](area.israel);
    );
    out body;
    >;
    out skel qt;
    """
    
    try:
        print("Sending request to Overpass API...")
        response = requests.post(overpass_url, data=overpass_query)
        response.raise_for_status()
        
        data = response.json()
        
        # Convert to GeoJSON
        features = []
        
        for element in data['elements']:
            if element['type'] == 'node':
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [element['lon'], element['lat']]
                    },
                    "properties": {
                        "id": element['id'],
                        "type": element['type'],
                        **element.get('tags', {})
                    }
                }
                features.append(feature)
        
        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "count": len(features),
                "source": "OpenStreetMap via Overpass API"
            }
        }
        
        # Save to file
        output_path = Path(output_file)
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
            
        print(f"Successfully downloaded {len(features)} amenities")
        print(f"Data saved to {output_file}")
        
        # Basic statistics
        amenity_types = {}
        for feature in features:
            amenity_type = feature['properties'].get('amenity', 'unknown')
            amenity_types[amenity_type] = amenity_types.get(amenity_type, 0) + 1
            
        print("\nAmenity type distribution:")
        for amenity_type, count in sorted(amenity_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"{amenity_type}: {count}")
            
    except requests.exceptions.RequestException as e:
        print(f"Error downloading data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    download_amenities()