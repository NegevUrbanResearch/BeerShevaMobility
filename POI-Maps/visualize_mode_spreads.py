import os
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def load_poi_data(poi_names, mode_spreads_dir):
    """Load and process data for specified POIs"""
    poi_data = {}
    filename_mapping = {
        'Soroka': 'Soroka_Hospital_mode_spread.csv',
        'Gav Yam': 'Gev_Yam_mode_spread.csv',
        'BGU': 'BGU_mode_spread.csv'
    }
    
    for poi_name in poi_names:
        file_path = os.path.join(mode_spreads_dir, filename_mapping.get(poi_name, ''))
        try:
            df = pd.read_csv(file_path)
            poi_data[poi_name] = df
            logger.info(f"Loaded data for {poi_name}")
        except FileNotFoundError:
            logger.error(f"Could not find data file: {file_path}")
    return poi_data

def create_mode_spread_visualization(poi_data):
    """Create an interactive visualization of mode spreads"""
    # Create figure with secondary y-axis
    fig = make_subplots(rows=len(poi_data), cols=1,
                       subplot_titles=[f"<b>{poi}</b>" for poi in poi_data.keys()],
                       vertical_spacing=0.12)
    
    # Enhanced color mapping and styling
    colors = {
        'car': '#2E86C1',        # Deep blue
        'public transit': '#F39C12',  # Orange
        'bike': '#27AE60',       # Green
        'ped': '#E74C3C',        # Red
        'train': '#8E44AD'       # Purple
    }
    
    row = 1
    for poi_name, df in poi_data.items():
        # Add stacked area chart for percentages
        for mode in df['mode'].unique():
            mode_data = df[df['mode'] == mode]
            fig.add_trace(
                go.Scatter(
                    x=mode_data['hour'],
                    y=mode_data['percentage'],
                    name=f"{mode.title()}",  # Capitalize mode names
                    mode='lines',
                    stackgroup='one',
                    line=dict(width=1),
                    fillcolor=colors.get(mode, '#333333'),
                    hovertemplate="<b>%{y:.1f}%</b> at %{x}:00<br>",
                    showlegend=(row == 1)  # Only show legend for first POI
                ),
                row=row, col=1
            )
        
        # Update layout for each subplot
        fig.update_xaxes(
            title_text="Hour of Day",
            range=[0, 23],
            row=row, col=1,
            gridcolor='rgba(128, 128, 128, 0.2)',
            ticktext=[f"{i:02d}:00" for i in range(0, 24, 3)],
            tickvals=list(range(0, 24, 3))
        )
        fig.update_yaxes(
            title_text="Mode Share (%)",
            range=[0, 100],
            row=row, col=1,
            gridcolor='rgba(128, 128, 128, 0.2)',
            ticksuffix="%"
        )
        row += 1
    
    # Update overall layout
    fig.update_layout(
        height=250 * len(poi_data),  # Slightly reduced height
        title=dict(
            text="<b>Mode Share Distribution by Hour</b>",
            x=0.5,
            xanchor='center',
            font=dict(size=24)
        ),
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=1.02,
            bgcolor='rgba(255, 255, 255, 0.8)',
            bordercolor='rgba(128, 128, 128, 0.2)',
            borderwidth=1
        ),
        paper_bgcolor='white',
        plot_bgcolor='white',
        font=dict(
            family="Arial, sans-serif",
            size=12
        ),
        margin=dict(t=100, r=150, b=50, l=50)
    )
    
    return fig

def main():
    # Directory containing mode spread CSVs
    mode_spreads_dir = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset/output/mode_spreads'
    
    # Specify POIs to visualize
    poi_names = ['BGU', 'Soroka', 'Gav Yam']
    
    # Load data
    poi_data = load_poi_data(poi_names, mode_spreads_dir)
    
    if not poi_data:
        logger.error("No data was loaded. Exiting.")
        return
    
    # Create visualization
    fig = create_mode_spread_visualization(poi_data)
    
    # Save as interactive HTML with config options
    html_output = os.path.join(mode_spreads_dir, 'mode_spreads_visualization.html')
    fig.write_html(
        html_output,
        config={'displayModeBar': True, 'responsive': True}
    )
    logger.info(f"Saved interactive visualization to {html_output}")
    
    # Save as high-resolution static image for slides
    png_output = os.path.join(mode_spreads_dir, 'mode_spreads_visualization.png')
    fig.write_image(
        png_output,
        width=1600,  # Increased resolution
        height=400 * len(poi_data),
        scale=2  # Higher DPI
    )
    logger.info(f"Saved static visualization to {png_output}") 