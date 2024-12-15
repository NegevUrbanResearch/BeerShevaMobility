import boto3
import pandas as pd
import os
from datetime import datetime
from botocore import UNSIGNED
from botocore.config import Config

def download_fsq_places_data():
    """
    Downloads and filters Foursquare Places data for Israel locations.
    Uses AWS SDK to access the public S3 bucket and filters the data.
    """
    # S3 paths from the documentation
    bucket_name = "fsq-os-places-us-east-1"
    places_prefix = "release/dt=2024-12-03/places/parquet"
    
    # Output directory
    output_dir = "shapes/data/output"
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Initialize S3 client with unsigned config for public access
        s3_client = boto3.client('s3', 
                               config=Config(signature_version=UNSIGNED),
                               region_name='us-east-1')
        
        print("Listing parquet files...")
        # List all parquet files in the directory
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=places_prefix
        )
        
        # Create a temporary directory for downloads
        temp_dir = os.path.join(output_dir, 'temp_parquet')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # Download and process each parquet file
        dfs = []
        for obj in response.get('Contents', []):
            if obj['Key'].endswith('.parquet'):
                local_file = os.path.join(temp_dir, os.path.basename(obj['Key']))
                print(f"Downloading {obj['Key']}...")
                
                # Download the file
                s3_client.download_file(
                    bucket_name,
                    obj['Key'],
                    local_file
                )
                
                # Read the parquet file
                df = pd.read_parquet(local_file)
                
                # Filter for Israel
                israel_df = df[df['country'] == 'Israel'].copy()
                if len(israel_df) > 0:
                    dfs.append(israel_df)
                
                # Clean up the temporary file
                os.remove(local_file)
        
        # Combine all dataframes
        if dfs:
            israel_places = pd.concat(dfs, ignore_index=True)
            
            # Filter for active places and select columns
            israel_places = israel_places[
                israel_places['date_closed'].isna()
            ][[
                'fsq_place_id',
                'name',
                'latitude',
                'longitude',
                'address',
                'city',
                'region',
                'country',
                'postcode',
                'fsq_category_ids',
                'phone',
                'website',
                'email',
                'date_refreshed'
            ]]
            
            # Save to CSV in the output directory
            csv_filename = os.path.join(output_dir, f'israel_places_{datetime.now().strftime("%Y%m%d")}.csv')
            israel_places.to_csv(csv_filename, index=False)
            
            print(f"\nSuccessfully downloaded {len(israel_places)} places in Israel")
            print(f"Data saved to {csv_filename}")
            
            # Print some basic statistics
            print("\nBasic Statistics:")
            print(f"Total number of places: {len(israel_places)}")
            print(f"Number of cities: {israel_places['city'].nunique()}")
            print("\nMost common cities:")
            print(israel_places['city'].value_counts().head())
            
        else:
            print("No places found in Israel in the dataset")
            
        # Clean up temporary directory
        os.rmdir(temp_dir)
            
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    download_fsq_places_data()