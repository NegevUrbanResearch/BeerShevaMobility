import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set the correct directories
BASE_DIR = '/Users/noamgal/Downloads/NUR/Beer-Sheva-Mobility-Dataset'
DATA_DIR = os.path.join(BASE_DIR, 'output', 'mode_spreads')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output', 'visualizations')

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
logger.info(f"Output directory created/verified at: {OUTPUT_DIR}")

def load_and_process_data(poi_name):
    file_path = os.path.join(DATA_DIR, f'{poi_name}_mode_spread.csv')
    logger.info(f"Loading data for {poi_name} from: {file_path}")
    df = pd.read_csv(file_path)
    
    # Pivot the data
    df_pivot = df.pivot(index='hour', columns='mode', values='percentage').fillna(0)
    
    # Filter for 6 AM to midnight
    df_pivot = df_pivot.loc[6:23]
    
    return df_pivot

# Modern color scheme with brighter colors for dark theme
colors = {
    'car': '#FF6B6B',          # Bright coral
    'public_transit': '#4ECDC4',# Bright turquoise
    'train': '#45B7D1',        # Bright blue
    'ped': '#98FB98',          # Bright green
    'bike': '#FFA07A'          # Bright salmon
}

poi_display_names = {
    'BGU': 'Ben Gurion University',
    'Soroka_Hospital': 'Soroka Hospital',
    'Gev_Yam': 'Gav Yam High-Tech Park'
}

# Create figure with more height for padding
fig = make_subplots(
    rows=3, cols=1,
    subplot_titles=[f"<span style='color: white'>{poi_display_names[poi]}</span>" 
                   for poi in ['BGU', 'Soroka_Hospital', 'Gev_Yam']],
    vertical_spacing=0.12  # Increased spacing between plots
)

# List of POIs to process
pois = ['BGU', 'Soroka_Hospital', 'Gev_Yam']

for idx, poi in enumerate(pois, 1):
    try:
        df = load_and_process_data(poi)
        logger.info(f"Processing visualization for {poi}")

        # Add traces for each mode without patterns
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['car'],
                name='Car',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['car']),  # Thicker line
                fillcolor=f'rgba(255,107,107,0.4)',  # More transparent fill
                stackgroup='one',
                showlegend=(idx == 1)
            ),
            row=idx, col=1
        )

        # Combine public transit and train
        public_transport = df['public_transit'] + df['train']
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=public_transport,
                name='Public Transit',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['public_transit']),
                fillcolor=f'rgba(78,205,196,0.4)',
                stackgroup='one',
                showlegend=(idx == 1)
            ),
            row=idx, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['ped'],
                name='Walking',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['ped']),
                fillcolor=f'rgba(152,251,152,0.4)',
                stackgroup='one',
                showlegend=(idx == 1)
            ),
            row=idx, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['bike'],
                name='Bicycle',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['bike']),
                fillcolor=f'rgba(255,160,122,0.4)',
                stackgroup='one',
                showlegend=(idx == 1)
            ),
            row=idx, col=1
        )

    except Exception as e:
        logger.error(f"Error processing {poi}: {str(e)}")

# Update layout with more margin and centered title
fig.update_layout(
    title=dict(
        text="Transportation Mode Distribution",
        font=dict(size=24, color='white'),
        x=0.5,  # Center the title
        xanchor='center'
    ),
    height=1400,  # Increased height
    width=1400,  # Increased width
    showlegend=True,
    paper_bgcolor='rgb(17,17,17)',
    plot_bgcolor='rgb(17,17,17)',
    hovermode='x unified',
    legend=dict(
        yanchor="middle",
        y=0.5,
        xanchor="right",
        x=1.2,  # Moved legend further right
        orientation="v",
        font=dict(
            color='white',
            size=16
        ),
        bgcolor='rgba(0,0,0,0)',
        itemsizing='constant',
        itemwidth=30
    ),
    margin=dict(l=150, r=200, t=150, b=150),  # Increased margins
)

# Update axes with outside labels
for i in range(1, 4):
    fig.update_xaxes(
        title_text="Hour of Day",
        title_font=dict(color='white', size=14),
        ticktext=[f'{h:02d}:00' for h in range(6, 24, 2)],
        tickvals=list(range(6, 24, 2)),
        gridcolor='rgba(255,255,255,0.2)',
        gridwidth=1,
        tickfont=dict(color='white', size=12),
        row=i, col=1,
        showgrid=True,
        showline=True,
        linecolor='rgba(255,255,255,0.3)',
        range=[5.5, 23.5],
        ticks='outside',  # Move ticks outside
        ticklabelposition='outside'  # Move labels outside
    )
    fig.update_yaxes(
        title_text="Percentage of Trips",
        title_font=dict(color='white', size=14),
        gridcolor='rgba(255,255,255,0.2)',
        gridwidth=1,
        ticksuffix='%',
        range=[-5, 105],
        dtick=20,
        tickfont=dict(color='white', size=12),
        row=i, col=1,
        showgrid=True,
        showline=True,
        linecolor='rgba(255,255,255,0.3)',
        ticks='outside',  # Move ticks outside
        ticklabelposition='outside'  # Move labels outside
    )

# Save the combined visualization
html_file = os.path.join(OUTPUT_DIR, 'mode_spread_comparison_interactive.html')
png_file = os.path.join(OUTPUT_DIR, 'mode_spread_comparison.png')

fig.write_html(html_file)
fig.write_image(png_file, scale=2)  # scale=2 for higher resolution

# Create and save individual visualizations for each POI
for idx, poi in enumerate(pois):
    individual_fig = go.Figure()
    
    try:
        df = load_and_process_data(poi)
        
        # Add car trace
        individual_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['car'],
                name='Car',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['car']),
                fillcolor=f'rgba(255,107,107,0.4)',
                stackgroup='one'
            )
        )

        # Add combined public transport trace
        public_transport = df['public_transit'] + df['train']
        individual_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=public_transport,
                name='Public Transit',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['public_transit']),
                fillcolor=f'rgba(78,205,196,0.4)',
                stackgroup='one'
            )
        )

        # Add pedestrian trace
        individual_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['ped'],
                name='Walking',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['ped']),
                fillcolor=f'rgba(152,251,152,0.4)',
                stackgroup='one'
            )
        )

        # Add bicycle trace
        individual_fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['bike'],
                name='Bicycle',
                fill='tonexty',
                mode='lines',
                line=dict(width=3, color=colors['bike']),
                fillcolor=f'rgba(255,160,122,0.4)',
                stackgroup='one'
            )
        )

        # Update individual figure layout
        individual_fig.update_layout(
            title=dict(
                text=f"Transportation Mode Distribution - {poi_display_names[poi]}",
                font=dict(size=24, color='white'),
                x=0.5,  # Center the title
                xanchor='center'
            ),
            height=800,  # Increased height
            width=1200,  # Increased width
            showlegend=True,
            paper_bgcolor='rgb(17,17,17)',
            plot_bgcolor='rgb(17,17,17)',
            hovermode='x unified',
            margin=dict(l=150, r=200, t=150, b=150),  # Increased margins
            legend=dict(
                yanchor="middle",
                y=0.5,
                xanchor="right",
                x=1.15,
                orientation="v",
                font=dict(color='white', size=16),
                bgcolor='rgba(0,0,0,0)',
                itemsizing='constant',
                itemwidth=30
            )
        )

        # Update axes for individual plots
        individual_fig.update_xaxes(
            title_text="Hour of Day",
            title_font=dict(color='white', size=14),
            ticktext=[f'{h:02d}:00' for h in range(6, 24, 2)],
            tickvals=list(range(6, 24, 2)),
            gridcolor='rgba(255,255,255,0.2)',
            gridwidth=1,
            tickfont=dict(color='white', size=12),
            showgrid=True,
            showline=True,
            linecolor='rgba(255,255,255,0.3)',
            range=[5.5, 23.5],
            ticks='outside',
            ticklabelposition='outside'
        )
        
        individual_fig.update_yaxes(
            title_text="Percentage of Trips",
            title_font=dict(color='white', size=14),
            gridcolor='rgba(255,255,255,0.2)',
            gridwidth=1,
            ticksuffix='%',
            range=[-5, 105],
            dtick=20,
            tickfont=dict(color='white', size=12),
            showgrid=True,
            showline=True,
            linecolor='rgba(255,255,255,0.3)',
            ticks='outside',
            ticklabelposition='outside'
        )

        # Save individual visualization
        individual_html = os.path.join(OUTPUT_DIR, f'mode_spread_{poi}_interactive.html')
        individual_png = os.path.join(OUTPUT_DIR, f'mode_spread_{poi}.png')
        
        individual_fig.write_html(individual_html)
        individual_fig.write_image(individual_png, scale=2)
        
        logger.info(f"Individual visualization for {poi} saved to: {individual_png}")

    except Exception as e:
        logger.error(f"Error creating individual visualization for {poi}: {str(e)}")

logger.info("All visualizations complete!")