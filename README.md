# Beer Sheva Mobility Analysis

Mobility data pipeline, analysis, and HTML visualizations for Beer Sheva POIs. Processed outputs in `output/dashboard_data/` are consumed by a separate JS frontend.

## Structure

| Directory | Purpose |
|-----------|---------|
| `src/mobility/` | Shared config, data loading, and utilities |
| `pipeline/` | ETL scripts that produce `output/dashboard_data/` |
| `viz/` | Deck.gl HTML visualizations and projection renders |
| `analysis/` | Exploratory analysis, catchment maps, slides |
| `data/` | Raw and processed input data (not in git) |
| `shapes/data/` | Spatial layers (zones, buildings, entrances) |
| `output/` | Generated outputs for the frontend and visualizations |

## Quick start

```bash
pip install -r requirements.txt

python pipeline/pre_preprocess_data.py
python pipeline/preprocess_data.py
python pipeline/temporal_preprocessing.py
```

Frontend-facing files land in `output/dashboard_data/` (`*_trips.csv`, `zones.geojson`, temporal CSVs, etc.).

See `pipeline/README.md` for the full pipeline and visualization commands.

## Dataset

Mobility data prepared by PGL Transportation Engineering and Planning Ltd., collected by Decell:

- **Time period**: November 2019 – February 2020; July 2021
- **Coverage**: Hundreds of thousands of unique users (18+)
- **Scope**: 13 Points of Interest

## Data privacy

Raw trip data is not included in this repository. Do not commit proprietary data files.
