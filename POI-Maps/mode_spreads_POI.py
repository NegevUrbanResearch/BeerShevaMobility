import pandas as pd
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# File paths
base_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
excel_file = os.path.join(base_dir, 'All-Stages.xlsx')
output_dir = os.path.join(base_dir, 'output', 'mode_spreads')
poi_locations_file = os.path.join(base_dir, 'output/processed_poi_data/poi_with_exact_coordinates.csv')

def parse_time(time_str):
    try:
        # Try parsing as HH:MM:SS
        return pd.to_datetime(time_str, format='%H:%M:%S').time()
    except ValueError:
        try:
            # Try parsing as float (assuming it's fraction of a day)
            hours = float(time_str) * 24
            return pd.to_datetime(f"{int(hours):02d}:{int(hours % 1 * 60):02d}:00").time()
        except ValueError:
            return None

def process_poi_trips(df, poi_id, poi_name):
    logger.info(f"Processing inbound trips for {poi_name} (ID: {poi_id})")
    
    # Get inbound trips to this POI
    poi_trips = df[df['to_tract'] == poi_id].copy()
    
    if len(poi_trips) == 0:
        logger.warning(f"No trips found for {poi_name}")
        return None
    
    # Merge bus and link into public transit
    poi_trips['mode'] = poi_trips['mode'].replace({'bus': 'Public transit', 'link': 'Public transit'})
    
    # Convert time to hour using the parse_time function
    poi_trips['time_bin'] = poi_trips['time_bin'].apply(parse_time)
    poi_trips = poi_trips.dropna(subset=['time_bin'])
    poi_trips['hour'] = poi_trips['time_bin'].apply(lambda x: x.hour)
    
    # Create pivot table of modes by hour
    mode_spread = pd.pivot_table(
        poi_trips,
        values='count',
        index=['hour', 'mode'],
        aggfunc='sum',
        fill_value=0
    ).reset_index()
    
    # Calculate total trips per hour for percentage calculation
    hour_totals = mode_spread.groupby('hour')['count'].sum().reset_index()
    hour_totals.columns = ['hour', 'total_trips']
    
    # Merge totals back and calculate percentages
    mode_spread = mode_spread.merge(hour_totals, on='hour')
    mode_spread['percentage'] = mode_spread['count'] / mode_spread['total_trips'] * 100
    
    # Sort by hour and mode for better readability
    mode_spread = mode_spread.sort_values(['hour', 'mode'])
    
    return mode_spread

def main():
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Load data (referencing Dashboard/data_loader.py lines 20-31)
        logger.info("Loading data...")
        df = pd.read_excel(excel_file, sheet_name='StageB1')
        poi_df = pd.read_csv(poi_locations_file)
        
        # Clean and pad tract IDs (referencing Dashboard/preprocess_data.py lines 34-36)
        df['from_tract'] = df['from_tract'].apply(lambda x: f"{int(float(x)):06d}" if pd.notna(x) else '000000')
        df['to_tract'] = df['to_tract'].apply(lambda x: f"{int(float(x)):06d}" if pd.notna(x) else '000000')
        
        logger.info("Processing mode spreads for each POI...")
        
        for _, poi in poi_df.iterrows():
            poi_id = str(poi['ID']).zfill(6)
            poi_name = poi['name']
            
            mode_spread = process_poi_trips(df, poi_id, poi_name)
            
            if mode_spread is not None:
                # Save to CSV
                output_file = os.path.join(output_dir, f"{poi_name.replace(' ', '_')}_inbound_mode_spread.csv")
                mode_spread.to_csv(output_file, index=False)
                
                logger.info(f"Saved inbound mode spread for {poi_name}")
                logger.info(f"Sample of mode distribution:")
                logger.info("\n" + str(mode_spread.head()))
                logger.info(f"Total trips: {mode_spread['count'].sum()}")
            
        logger.info("All POI inbound mode spreads have been processed and saved to CSV files.")
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        raise

if __name__ == "__main__":
    main() 