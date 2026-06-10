# Mobility Pipeline

Generates frontend data and inputs for HTML visualizations.

## Setup

From the repo root:

```bash
pip install -r requirements.txt
```

## Run order

1. **Spatial prep** (optional, one-time): `python pipeline/spatial/fetch_buildings.py`
2. **Preprocess raw trips**: `python pipeline/pre_preprocess_data.py`
3. **Build trip CSVs**: `python pipeline/preprocess_data.py`
4. **Temporal distributions**: `python pipeline/temporal_preprocessing.py`
5. **Car routes** (requires local OTP): `python pipeline/otp_car_proj.py`
6. **Walking routes** (requires local OTP): `python pipeline/otp_walk.py`
7. **Walking arc data**: `python pipeline/walk_temporal.py`

Outputs land in `output/dashboard_data/` for use by the JS frontend.

## HTML visualizations

From repo root after the pipeline completes:

```bash
python viz/trips/trips_arc_glow.py
python viz/trips/line_roads.py
python viz/trips/walk_trips_viz.py
```
