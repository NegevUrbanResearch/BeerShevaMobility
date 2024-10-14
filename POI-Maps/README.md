# POI-Maps

This project processes and visualizes Point of Interest (POI) data to create maps of inbound trips to various locations.

## Project Structure

- `preprocess.py`: Preprocesses the raw data and geocodes POI locations.
- `revised_maps.py`: Creates interactive maps for each POI showing inbound trips.


## Required Data Sources

- Excel files containing trip data (Proprietary)
- GDB file with statistical area spatial data (Download from [here](https://www.cbs.gov.il/he/Pages/geo-layers.aspx))
- CSV file with POI locations and coordinates (pulled from Google Maps API)


## Note on Data Privacy

This project uses sensitive data. Ensure you have the necessary permissions to use and share the data. Do not commit any raw data files to the repository.