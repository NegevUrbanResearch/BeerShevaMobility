import pandas as pd
import geopandas as gpd
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
from config import (
    BASE_DIR, DATA_DIR, PROCESSED_DIR,
    RAW_ZONES_FILE, RAW_TRIPS_FILE,
    ZONES_WITH_CITIES_FILE, TRIPS_WITH_CITIES_FILE
)

def create_city_level_zones(zones_gdf):
    """Create city-level zones by aggregating statistical areas"""
    print("Creating city-level zones...")
    
    # Create city ID for each statistical zone
    zones_gdf['city_id'] = zones_gdf['SEMEL_YISHUV'].apply(lambda x: f"C{int(x):05d}")
    
    # Debug: Print sample of city IDs
    print("\nSample city IDs:")
    print(zones_gdf[['SHEM_YISHUV_ENGLISH', 'SEMEL_YISHUV', 'city_id']].head())
    
    # Create city-level zones by dissolving
    city_zones = zones_gdf.dissolve(
        by='city_id',
        aggfunc={
            'SHEM_YISHUV_ENGLISH': 'first',
            'SEMEL_YISHUV': 'first',
            'YISHUV_STAT11': 'first'
        }
    ).reset_index()
    
    # Keep only necessary columns
    keep_columns = ['city_id', 'SHEM_YISHUV_ENGLISH', 'geometry']
    city_zones = city_zones[keep_columns]
    
    print(f"\nCreated {len(city_zones)} city zones")
    return city_zones

def clean_spatial_file(zones_gdf, city_zones):
    """Clean spatial file and combine with city zones"""
    print("\nCleaning spatial file...")
    
    # Keep only necessary columns from statistical zones
    keep_columns = ['YISHUV_STAT11', 'SHEM_YISHUV_ENGLISH', 'geometry']
    zones_clean = zones_gdf[keep_columns].copy()
    
    # Debug: Print sample of statistical zones
    print("\nSample statistical zones:")
    print(zones_clean.head())
    
    # Rename city_id to YISHUV_STAT11 for consistency
    city_zones = city_zones.rename(columns={'city_id': 'YISHUV_STAT11'})
    
    # Combine statistical and city zones
    combined_zones = pd.concat([zones_clean, city_zones], ignore_index=True)
    
    print(f"\nFinal zones count: {len(combined_zones)}")
    print("Sample combined zones:")
    print(combined_zones.head())
    
    return combined_zones

def create_city_name_mapping(zones_df, df):
    """Create a mapping of city names with fuzzy matching"""
    print("\nCreating city name mapping...")
    
    # Convert tract columns to string and ensure proper formatting
    df['from_tract'] = df['from_tract'].fillna('0')
    df['to_tract'] = df['to_tract'].fillna('0')
    df['from_tract'] = df['from_tract'].astype(str).apply(lambda x: '0' if x in ['0', '0.0', 'nan'] else x)
    df['to_tract'] = df['to_tract'].astype(str).apply(lambda x: '0' if x in ['0', '0.0', 'nan'] else x)
    
    # Debug: Print sample of input data
    print("\nSample of input data:")
    print("\nTrips data head:")
    print(df[['from_name', 'from_tract', 'to_name', 'to_tract']].head(10))
    print("\nUnique from_tract values:", df['from_tract'].unique()[:10])
    print("\nUnique to_tract values:", df['to_tract'].unique()[:10])
    
    # Get unique city names from zones and normalize them
    zone_cities = zones_df[zones_df['YISHUV_STAT11'].str.startswith('C', na=False)]
    city_names = zone_cities['SHEM_YISHUV_ENGLISH'].str.upper().str.strip()
    
    print("\nSample of zone cities:")
    print(zone_cities[['YISHUV_STAT11', 'SHEM_YISHUV_ENGLISH']].head())
    
    # Get unique city names from trips data where tract is 0
    from_cities = df.loc[df['from_tract'] == '0', 'from_name'].dropna()
    to_cities = df.loc[df['to_tract'] == '0', 'to_name'].dropna()
    
    print("\nSample of cities from trips (from_name):")
    print(from_cities.head())
    print("\nSample of cities from trips (to_name):")
    print(to_cities.head())
    
    trip_cities = pd.concat([from_cities, to_cities]).unique()
    
    print(f"\nTotal unique cities found in trips data: {len(trip_cities)}")
    print("Sample of trip cities:")
    print(trip_cities[:10])
    
    # Remove 'Unknown' and POI names
    poi_names = ['BGU', 'Soroka Hospital', 'Assuta Hospital', 'BIG', 'Yes Planet', 
                'HaNegev Mall', 'Grand Kenyon', 'Sami Shimon collage', 'Unknown',
                'Naot Hovav', 'Gev Yam', 'Emek Shara industrial area', 'Omer industrial area']
    trip_cities = [city for city in trip_cities if city not in poi_names]
    
    print(f"\nCities after removing POIs: {len(trip_cities)}")
    print("Sample of cleaned cities:")
    print(trip_cities[:10])
    
    # Create mapping dictionary
    city_to_id = {}
    unmatched_cities = []
    
    for trip_city in trip_cities:
        if pd.isna(trip_city):
            continue
            
        trip_city_norm = str(trip_city).upper().strip()
        
        # Debug: Print matching attempt
        print(f"\nTrying to match: '{trip_city_norm}'")
        print(f"Available city names: {city_names.head()}")
        
        # Try exact match first
        exact_match = zone_cities[
            city_names == trip_city_norm
        ]['YISHUV_STAT11'].iloc[0] if trip_city_norm in city_names.values else None
        
        if exact_match:
            city_to_id[trip_city] = exact_match
            print(f"Exact match found: {exact_match}")
        else:
            # Try fuzzy matching
            matches = process.extractBests(
                trip_city_norm,
                city_names.values,
                score_cutoff=80,
                limit=1
            )
            
            if matches:
                matched_name = matches[0][0]
                matched_id = zone_cities[
                    city_names == matched_name
                ]['YISHUV_STAT11'].iloc[0]
                city_to_id[trip_city] = matched_id
                print(f"Fuzzy match: '{trip_city}' -> '{matched_name}' (ID: {matched_id})")
            else:
                unmatched_cities.append(trip_city)
                print("No match found")
    
    # Print statistics
    print(f"\nMatching Statistics:")
    print(f"Total cities in raw data: {len(trip_cities)}")
    print(f"Successfully matched: {len(city_to_id)}")
    print(f"Unmatched: {len(unmatched_cities)}")
    
    if unmatched_cities:
        print("\nUnmatched cities:")
        print(unmatched_cities)
    
    return city_to_id

def process_trips_data(trips_df, zones_gdf):
    """Map city names to city IDs in trips data"""
    print("\nProcessing trips data...")
    
    # Create city name mapping
    city_mapping = create_city_name_mapping(zones_gdf, trips_df)
    
    # Function to map city names to IDs
    def map_city_to_id(row, column):
        tract_col = 'from_tract' if column == 'from_name' else 'to_tract'
        
        # Convert to float first to handle scientific notation, then to string
        try:
            tract_val = float(row[tract_col])
            if tract_val != 0:  # Only process if it's exactly 0
                return str(row[tract_col])
        except ValueError:
            if str(row[tract_col]) not in ['0', '0.0', 'nan']:
                return str(row[tract_col])
        
        # If we get here, the tract is 0 or equivalent
        mapped_id = city_mapping.get(row[column])
        print(f"Mapping city {row[column]} to {mapped_id} (tract was {row[tract_col]})")
        return mapped_id if mapped_id else '0'
    
    # Map cities in from and to columns
    trips_df['from_tract'] = trips_df.apply(lambda x: map_city_to_id(x, 'from_name'), axis=1)
    trips_df['to_tract'] = trips_df.apply(lambda x: map_city_to_id(x, 'to_name'), axis=1)
    
    # Debug: Print sample of processed trips
    print("\nSample of processed trips:")
    print(trips_df[['from_name', 'from_tract', 'to_name', 'to_tract']].head())
    
    # Print statistics about city mappings
    city_tracts = trips_df[trips_df['from_tract'].str.startswith('C', na=False)]['from_tract'].unique()
    print("\nCity tracts found in from_tract:")
    print(city_tracts)
    
    # Print statistics
    print("\nTrips statistics:")
    print(f"Total trips: {len(trips_df)}")
    print(f"Unique from_tract values: {trips_df['from_tract'].nunique()}")
    print(f"Unique to_tract values: {trips_df['to_tract'].nunique()}")
    print(f"Number of city tracts (starting with C): {len(city_tracts)}")
    
    return trips_df

def main():
    # Load data
    print("Loading data...")
    zones = gpd.read_file(RAW_ZONES_FILE)
    trips = pd.read_excel(RAW_TRIPS_FILE, sheet_name='StageB1')
    
    # Debug: Print initial data info
    print("\nInitial data summary:")
    print(f"Zones shape: {zones.shape}")
    print(f"Trips shape: {trips.shape}")
    
    # Create city zones
    city_zones = create_city_level_zones(zones)
    
    # Clean and combine spatial data
    combined_zones = clean_spatial_file(zones, city_zones)
    
    # Process trips data
    processed_trips = process_trips_data(trips, combined_zones)
    
    # Save processed files
    print("\nSaving processed files...")
    combined_zones.to_file(ZONES_WITH_CITIES_FILE, driver='GeoJSON')
    processed_trips.to_excel(TRIPS_WITH_CITIES_FILE, index=False)
    
    print("\nPre-preprocessing complete!")
    print(f"Files saved to: {PROCESSED_DIR}")

if __name__ == "__main__":
    main() 