# Beer Sheva Mobility Analysis

A comprehensive mobility data analysis and visualization platform for Beer Sheva, focusing on Points of Interest (POIs) and travel patterns.

## Project Components

### 1. EDA (@EDA)
Tools for analyzing and visualizing specific Points of Interest:
- Utility scripts for loading, preprocessing, and exploring data
- Geospatial analysis of POIs
- Static maps of trip patterns
- Detecting and summarizing trip patterns

### 2. Interactive Dashboard (@Dashboard)
Web interface for exploring mobility data:
- Interactive maps showing trip distributions
- Charts for visualizing trip modes, purposes, and frequencies
- Time-based analysis of trip patterns

### 3. Advanced Visualizations (@roads)
Dynamic visualizations of mobility patterns:
- Animated trip flows
- Walking route analysis
- Road usage heatmaps
- Temporal distribution analysis
- Building-level visualizations

## Dataset

The analysis uses mobility data for Beer Sheva prepared by PGL Transportation Engineering and Planning Ltd. and collected by Decell:

- **Time Period**: November 2019 - February 2020, July 2021
- **Coverage**: Hundreds of thousands of unique users (18+)
- **Scope**: 13 Points of Interest
- **Data Points**: 
  - Origin/Destination
  - Trip Purpose
  - Travel Mode
  - Travel Time
  - Entry/Exit times
  - Trip Frequency

## Required Data Sources

1. Trip Data:
   - Excel files containing trip data (Proprietary)
   - Statistical area spatial data (GDB format)
   - POI coordinates (CSV from Google Maps API)

2. Spatial Data:
   - Building footprints (OpenStreetMap)
   - Road network data (OTP model built locally)
   - Statistical area boundaries

## Note on Data Privacy

This project uses sensitive mobility data. Raw data files are not included in the repository. Ensure you have necessary permissions before using or sharing any data.
