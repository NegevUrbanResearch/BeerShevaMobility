import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
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

# Set dark style
plt.style.use('dark_background')
sns.set_context("notebook", font_scale=1.2)

# Modern dark theme color palette
colors = {
    'car': '#FF6B6B',          # Coral red
    'public_transit': '#4ECDC4',# Turquoise
    'train': '#45B7D1',        # Light blue
    'ped': '#98FB98',          # Pale green
    'bike': '#FFA07A'          # Light salmon
}

poi_display_names = {
    'BGU': 'Ben Gurion University',
    'Soroka_Hospital': 'Soroka Hospital',
    'Gev_Yam': 'Gav Yam High-Tech Park'
}

def load_and_process_data(poi_name):
    file_path = os.path.join(DATA_DIR, f'{poi_name}_mode_spread.csv')
    logger.info(f"Loading data for {poi_name} from: {file_path}")
    df = pd.read_csv(file_path)
    
    # Filter for business hours (6 AM to midnight)
    df = df[df['hour'].between(6, 23)]
    
    # Calculate average percentages for each mode during business hours
    mode_averages = df.groupby('mode')['percentage'].mean()
    
    return mode_averages

# Create figure with three subplots
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(20, 8))
fig.suptitle('Average Mode Distribution\nAt Innovation District POI', 
             fontsize=20, y=1.05, color='white', fontweight='bold')

# List of POIs to process
pois = ['BGU', 'Soroka_Hospital', 'Gev_Yam']
axes = [ax1, ax2, ax3]

for poi, ax in zip(pois, axes):
    try:
        mode_averages = load_and_process_data(poi)
        logger.info(f"Processing visualization for {poi}")
        
        # Create pie chart
        wedges, texts, autotexts = ax.pie(
            mode_averages,
            labels=mode_averages.index,
            colors=[colors[mode.lower()] for mode in mode_averages.index],
            autopct='%1.1f%%',
            pctdistance=0.85,
            wedgeprops=dict(width=0.5, edgecolor='none'),  # Create donut chart effect
        )
        
        # Enhance text properties
        plt.setp(autotexts, size=10, weight="bold", color="white")
        plt.setp(texts, size=10, color="white")
        
        # Add title
        ax.set_title(poi_display_names[poi], 
                    pad=20, 
                    fontsize=14, 
                    fontweight='bold', 
                    color='white')
        
    except Exception as e:
        error_msg = f"Error processing {poi}: {str(e)}"
        logger.error(error_msg)
        ax.text(0.5, 0.5, error_msg,
                ha='center', va='center', transform=ax.transAxes,
                color='white')

# Add a single legend for all subplots
legend_elements = [plt.Line2D([0], [0], marker='o', color='w', 
                            markerfacecolor=color, label=mode.title(), 
                            markersize=10)
                  for mode, color in colors.items()]
fig.legend(handles=legend_elements, 
          loc='center', 
          bbox_to_anchor=(0.5, -0.05),
          ncol=len(colors),
          frameon=False,
          fontsize=12)

# Adjust layout
plt.tight_layout()

# Save the figure with high resolution
output_file = os.path.join(OUTPUT_DIR, 'mode_spread_pie_comparison.png')
plt.savefig(output_file, 
            dpi=300, 
            bbox_inches='tight', 
            facecolor='black',
            edgecolor='none')
logger.info(f"Visualization saved to: {output_file}")
plt.close()

logger.info("Visualization process complete!") 