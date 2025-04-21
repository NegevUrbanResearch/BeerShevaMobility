# Projections Animation System

This directory contains scripts for generating high-resolution animated visualizations of mobility patterns in Beer Sheva. The system focuses on creating detailed video recordings of peak traffic hours.

## Core Components

### 1. Configuration
- `animation_config.py`: Central configuration file defining:
  - Animation timing parameters
  - Mode-specific settings (car/walk)
  - Direction settings (inbound/outbound)
  - POI colors and styling

### 2. Animation Generation
- `8k_recorder.py`: High-resolution video generator
  - Creates 8K (7680x4320) resolution videos
  - Focuses on peak hours (7:00-7:30am for inbound, 5:00-5:30pm for outbound)
  - Generates MP4 files
  - Output: `projection_animation_{model}_{mode}_{direction}_{time}_8k_zoomed.mp4`

- `anim_transparent.py`: Transparent background version
  - Creates animations with transparent backgrounds
  - Useful for overlaying on other visualizations
  - Maintains same resolution and timing as main recorder

### 3. Data Processing
- `trip_processing.py`: Trip data processor
  - Processes raw trip data
  - Generates route geometries
  - Creates temporal distributions
  - Output: Various GeoJSON and CSV files

## Time Controls

### Peak Hours (8K Recording)
1. Morning Peak (Inbound)
   - Single segment: 7:00-7:30 AM

2. Evening Peak (Outbound)
   - Single segment: 5:00-5:30 PM


## Output Files

### High-Resolution Videos
- Format: MP4
- Resolution: 8K (7680x4320)
- Time segments: 
  - Inbound: 7:00-7:30 AM
  - Outbound: 5:00-5:30 PM
- Example: `projection_animation_big_car_inbound_7-7:30am_8k_zoomed.mp4`

## Usage

1. Process trip data:
```bash
python trip_processing.py
```

2. Generate high-resolution videos:
```bash
python 8k_recorder.py
```

3. Create transparent versions (optional):
```bash
python anim_transparent.py
```

## Dependencies
- Python 3.x
- Geopandas
- Selenium
- OpenCV
- Pillow
- Firefox (for recording)
- FFmpeg (for video processing)

## Notes
- 8K recording requires significant system resources
- Peak hour segments are optimized for presentation quality
- All animations maintain consistent timing across modes
- Hardware acceleration is used when available for better performance 