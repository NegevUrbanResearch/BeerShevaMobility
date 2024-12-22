import geopandas as gpd
import os
import subprocess
from pathlib import Path
import matplotlib.pyplot as plt

# Constants
UNAR_PATH = '/opt/homebrew/bin/unar'
map_output_dir = "/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset/Shapefiles/maps"
temp_extract_dir = "/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset/Shapefiles/temp_extracted"
os.makedirs(map_output_dir, exist_ok=True)
os.makedirs(temp_extract_dir, exist_ok=True)

# Store all geodataframes in a list
all_gdfs = []

def extract_rar(rar_file, extract_path):
    print(f"\nProcessing {os.path.basename(rar_file)}...")
    try:
        # Check if already extracted
        base_name = Path(rar_file).stem
        target_dir = os.path.join(extract_path, base_name)
        
        if os.path.exists(target_dir):
            print(f"Files already extracted in {target_dir}")
            return True
            
        subprocess.run([UNAR_PATH, '-force-overwrite', '-o', extract_path, rar_file], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error extracting {rar_file}: {e}")
        return False

def process_shapefile(shp_path, output_name):
    try:
        gdf = gpd.read_file(shp_path)
        
        # Add source file name as a column
        gdf['source_file'] = output_name
        
        # Save individual map
        output_path = os.path.join(map_output_dir, f"{output_name}.shp")
        gdf.to_file(output_path)
        
        # Print info about the shapefile
        print(f"\n=== {os.path.basename(shp_path)} ===\n")
        print("Columns:")
        print(gdf.columns.tolist())
        print("\nSample data:")
        print(gdf.head())
        print("\nData info:")
        print(gdf.info())
        
        # Add to our collection
        all_gdfs.append(gdf)
        
        return gdf
    except Exception as e:
        print(f"Error processing {shp_path}: {e}")
        return None

def main():
    # List of RAR files to process
    rar_files = [
        "Attraction Centers.rar",
        "RFP_BS.rar",
        "RFP_BS_Phase_20.12.21.rar",
        "Be'er_Sheva_Shapefiles.rar",
        "Be'er Sheva Shapefiles.rar"
    ]
    
    base_path = "/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset/Shapefiles"
    
    for rar_name in rar_files:
        rar_path = os.path.join(base_path, rar_name)
        if not os.path.exists(rar_path):
            print(f"File not found: {rar_path}")
            continue
            
        if extract_rar(rar_path, temp_extract_dir):
            # Handle special case for "Shapefiles - Export" directory
            if "Sheva_Shapefiles" in rar_name:
                extract_base = os.path.join(temp_extract_dir, "Shapefiles - Export")
            else:
                extract_base = os.path.join(temp_extract_dir, Path(rar_name).stem)
                
            # Find and process all .shp files in the extracted directory
            for shp_file in Path(extract_base).glob("**/*.shp"):
                output_name = f"{Path(rar_name).stem}_{shp_file.stem}"
                process_shapefile(str(shp_file), output_name)
    
    # Add code to create JPEG visualizations
    # Create output directory for plots
    plot_dir = os.path.join(map_output_dir, "plots")
    os.makedirs(plot_dir, exist_ok=True)
    
    # Plot each shapefile
    for gdf in all_gdfs:
        title = gdf['source_file'].iloc[0]
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # Plot the geometries
        gdf.plot(ax=ax)
        
        # Add labels for each geometry using ID
        for idx, row in gdf.iterrows():
            # Get the centroid of the geometry for label placement
            centroid = row.geometry.centroid
            ax.annotate(str(row['ID']), 
                       xy=(centroid.x, centroid.y),
                       xytext=(3, 3),  # 3 points offset
                       textcoords="offset points",
                       fontsize=8,
                       color='red')
        
        ax.set_title(title)
        plt.savefig(os.path.join(plot_dir, f"{title}.jpg"), 
                   bbox_inches='tight', 
                   dpi=300)
        plt.close()

    # Combine all geodataframes
    if all_gdfs:
        print("\nCreating combined shapefile...")
        # Check if all GDFs have the same CRS
        crs_list = [gdf.crs for gdf in all_gdfs]
        if len(set(crs_list)) > 1:
            print("Warning: Different CRS detected. Reprojecting to the CRS of the first shapefile...")
            target_crs = all_gdfs[0].crs
            for i in range(1, len(all_gdfs)):
                all_gdfs[i] = all_gdfs[i].to_crs(target_crs)
        
        combined_gdf = gpd.pd.concat(all_gdfs, ignore_index=True)
        
        # Save combined shapefile
        combined_output = os.path.join(map_output_dir, "combined_shapes.shp")
        combined_gdf.to_file(combined_output)
        
        print("\nCombined shapefile created with info:")
        print(combined_gdf.info())
    else:
        print("No shapefiles were processed successfully.")

if __name__ == "__main__":
    main()
