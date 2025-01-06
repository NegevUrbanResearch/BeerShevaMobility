# POI-Maps

This project processes and visualizes Point of Interest (POI) data to create maps of inbound trips to various locations.

## Project Structure

### Core Components
- `config.py`: Configuration settings and constants
- `utils/`: Utility functions for data standardization and validation
  - `data_standards.py`: POI and zone naming standards
  - `data_validation.py`: Data validation functions
  - `zone_utils.py`: Zone ID handling utilities

### Analysis Pipeline
1. **Data Preprocessing**:
   - `temporal_preprocessing_new.py`: Process temporal trip patterns
   
2. **Analysis**:
   - `city_counts.py`: Analyze city-level trip patterns
   - `dist_analyzer.py`: Distance-based analysis
   - `spac_explore.py`: Spatial pattern analysis

3. **Visualization**:
   - `catchment_dashboard.py`: Generate catchment area visualizations
   - `city_viz.py`: City-level pattern visualizations
   - `temporal_viz.py`: Temporal pattern visualizations
   - `dist_viz.py`: Distance distribution visualizations

## Required Data Sources
- Excel files containing trip data (Proprietary)
- GDB file with statistical area spatial data (Download from [here](https://www.cbs.gov.il/he/Pages/geo-layers.aspx))
- CSV file with POI locations and coordinates (pulled from Google Maps API)

## Running the Pipeline
1. Ensure all required data files are in place
2. Run preprocessing: `python temporal_preprocessing_new.py`
3. Run analysis scripts in any order
4. Generate visualizations using the respective viz scripts
5. View dashboard outputs in the `output/` directory

## Note on Data Privacy
This project uses sensitive data. Ensure you have the necessary permissions to use and share the data. Do not commit any raw data files to the repository.