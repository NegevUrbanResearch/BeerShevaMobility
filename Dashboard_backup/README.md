# Beer Sheva Mobility Dashboard

This dashboard allows users to view maps and graphs of bout outbound and inbound trips for all 13 POI in the Beer Sheva Mobility Dataset. The maps show trip totals and the corresponding pie charts show the mode, purpose, frequency, and temporal distribution of the trips.

## Required Data Sources

- Excel files containing trip data (Proprietary)
- GDB file with statistical area spatial data (Download from [here](https://www.cbs.gov.il/he/Pages/geo-layers.aspx))
- CSV file with POI locations and coordinates (pulled from Google Maps API)

## Usage

1. Preprocess the data:
   ```
   python preprocess_data.py
   ```

2. Run the dashboard:
   ```
   python app.py
   ```

3. Open a web browser and go to `http://127.0.0.1:8050/` to view the dashboard.

## File Structure

- `app.py`: Main dashboard application
- `data_loader.py`: Data loading utilities
- `chart_utils.py`: Chart creation functions
- `map_utils.py`: Map creation functions
- `config.py`: Configuration settings
- `preprocess_data.py`: Data preprocessing script