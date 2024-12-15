import geopandas as gpd

amenties_path = "/Users/noamgal/DSProjects/BeerShevaMobility/shapes/data/output/points_within_buffer.shp"

amenities = gpd.read_file(amenties_path)

print(amenities.head())
print(amenities.columns)
print(len(amenities))