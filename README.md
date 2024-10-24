# Beer Sheva Mobility Analysis

This repository contains two main components for analyzing mobility data in Beer Sheva:


1) POI Maps (@POI-Maps): Mapping analysis tools for Points of Interest.
2) Dashboard (@Dashboard): An interactive web dashboard for visualizing mobility patterns.

## Dataset

The analysis is based on a comprehensive mobility dataset for Beer Sheva prepared by PGL Transportation Engineering and Planning Ltd. and collected by Decell. Key features include:

- Time period: November 2019 to February 2020, with additional data from July 2021
- Coverage: Hundreds of thousands of unique users aged 18+
- Scope: 13 Points of Interest (POIs) in Beer Sheva
- Data points: Origin, Destination, Purpose, Mode, Travel Time, Entry/Exit time from POIs, Frequency

The dataset is proprietary and not included in this repository.

## POI Maps (@POI-Maps)

This component focuses on saving local maps and analysis of specific Points of Interest in Beer Sheva.

### Key Features:
- Geospatial analysis of POIs
- Visualization of trip patterns around specific locations

## Dashboard (@Dashboard)

The dashboard provides an interactive web interface for comparing patterns for different points of interest in Beer Sheva.

### Key Features:
- Interactive maps showing trip distributions
- Charts for visualizing trip modes, purposes, and frequencies
- Time-based analysis of trip patterns

## Usage

1. Ensure Docker is installed on your machine.

2. Place the required data files in the `data` folder:
   - `All-Stages.xlsx`
   - `statisticalareas_demography2019.gdb`
   - `poi_with_exact_coordinates.csv`

3. Open a terminal and navigate to the Dashboard folder.

4. Build the Docker image:
   ```
   docker build -t beer-sheva-dashboard .
   ```

5. Run the Docker container:
   ```
   docker run -p 8050:8050 beer-sheva-dashboard
   ```

6. Open a web browser and go to `http://localhost:8050/` to view the dashboard.
