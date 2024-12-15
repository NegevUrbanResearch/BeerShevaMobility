# Beer Sheva Mobility Data Visualization

This dashboard allows users to view maps and graphs of bout outbound and inbound trips for all 13 POI in the Beer Sheva Mobility Dataset. The maps show trip totals and the corresponding pie charts show the mode, purpose, frequency, and temporal distribution of the trips.

## Required Data Sources

- Excel files containing trip data (Proprietary)
- GDB file with statistical area spatial data (Download from [here](https://www.cbs.gov.il/he/Pages/geo-layers.aspx))
- CSV file with POI locations and coordinates (pulled from Google Maps API)

## Required Data Files

### Raw Data
- `statisticalareas_demography2019.gdb`: Statistical areas GIS data
- `All-Stages.xlsx`: Raw trip data
- `poi_with_exact_coordinates.csv`: POI locations

### Processed Data (generated)
- `zones_with_cities.geojson`: Combined zone data
- `trips_with_cities.xlsx`: Processed trip data
- Various POI-specific CSV files for trips and temporal distributions

## Usage

1. Run initial data preparation:
   ```
   python pre_preprocess_data.py
   ```

2. Preprocess the data:
   ```
   python preprocess_data.py
   ```

3. Run the dashboard:
   ```
   python app.py
   ```

4. Open a web browser and go to `http://127.0.0.1:8050/` to view the dashboard.

## Docker Setup

### Prerequisites
- Docker installed on your system
- Required data files in the `data/raw` directory:
  - `statisticalareas_demography2019.gdb`
  - `All-Stages.xlsx`
  - `poi_with_exact_coordinates.csv`

### Building and Running with Docker

1. Build the Docker image:
```
"docker build -t beer-sheva-dashboard ."
```

2. Run the container:
```
"docker run -d \
  -p 8050:8050 \
  -v $(pwd)/data/raw:/app/data/raw \
  --name beer-sheva-dashboard \
  beer-sheva-dashboard"
```

3. Access the dashboard at `http://localhost:8050`

### Managing the Container

- Stop the container:
```
"docker stop beer-sheva-dashboard"
```

- Start an existing container:
```
"docker start beer-sheva-dashboard"
```

- Remove the container:
```
"docker rm beer-sheva-dashboard"
```

### Troubleshooting

- View container logs:
```
"docker logs beer-sheva-dashboard"
```

- Access container shell:
```
"docker exec -it beer-sheva-dashboard bash"
```

Note: Make sure all required data files are present in the `data/raw` directory before building the image. The preprocessing scripts will run during the build process.