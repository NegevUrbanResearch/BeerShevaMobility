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

# Update the mode display names
mode_display_names = {
    'car': 'Car',
    'public_transit': 'Public Transit',  # Combined name for public transit
    'train': 'Public Transit',  # Will be combined with public_transit
    'ped': 'Walking',
    'bike': 'Bicycle'
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

# Create figure with three subplots at 2560x1440
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(25.6, 14.4))  # 2560/100, 1440/100 for inches
fig.suptitle('Average Mode Distribution\nAt Innovation District POI', 
             fontsize=20, y=1.02, color='white', fontweight='bold')

# List of POIs to process
pois = ['BGU', 'Soroka_Hospital', 'Gev_Yam']
axes = [ax1, ax2, ax3]

for poi, ax in zip(pois, axes):
    try:
        mode_averages = load_and_process_data(poi)
        
        # Combine public transit and train before creating pie chart
        if 'train' in mode_averages and 'public_transit' in mode_averages:
            mode_averages['public_transit'] += mode_averages['train']
            mode_averages = mode_averages.drop('train')
        
        # Update labels with display names
        labels = [mode_display_names[mode.lower()] for mode in mode_averages.index]
        
        # Create pie chart
        wedges, texts, autotexts = ax.pie(
            mode_averages,
            labels=labels,  # Use updated labels
            colors=[colors[mode.lower()] for mode in mode_averages.index],
            autopct='%1.1f%%',
            pctdistance=0.85,
            wedgeprops=dict(width=0.5, edgecolor='none'),
        )
        
        # Enhance text properties with larger font
        plt.setp(autotexts, size=12, weight="bold", color="white")
        plt.setp(texts, size=12, color="white")
        
        # Add title
        ax.set_title(poi_display_names[poi], 
                    pad=20, 
                    fontsize=14, 
                    fontweight='bold', 
                    color='white')
        
        # Update legend creation for combined plot
        legend_elements = [plt.Line2D([0], [0], marker='o', color='w', 
                                    markerfacecolor=colors[mode], 
                                    label=mode_display_names[mode], 
                                    markersize=12)  # Increased marker size
                          for mode in ['car', 'public_transit', 'ped', 'bike']]  # Removed 'train'
        
        ax.legend(handles=legend_elements, 
                 loc='center', 
                 bbox_to_anchor=(0.5, -0.02),  # Moved legend closer to the chart
                 ncol=len(legend_elements),
                 frameon=False,
                 fontsize=14)  # Increased font size
        
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

# Adjust layout with more padding
plt.tight_layout(rect=[0.1, 0.1, 0.9, 0.9])

# Save the combined visualization at 2560x1440
output_file = os.path.join(OUTPUT_DIR, 'mode_spread_pie_comparison.jpg')
plt.savefig(output_file, 
            dpi=100,  # 100 DPI * 25.6" = 2560px
            bbox_inches='tight',
            facecolor='black',
            edgecolor='none',
            format='jpg',
            pad_inches=0.5)
logger.info(f"Visualization saved to: {output_file}")
plt.close()

# Create individual pie charts
for poi in pois:
    try:
        mode_averages = load_and_process_data(poi)
        
        # Combine public transit and train
        if 'train' in mode_averages and 'public_transit' in mode_averages:
            mode_averages['public_transit'] += mode_averages['train']
            mode_averages = mode_averages.drop('train')
        
        # Update labels with display names
        labels = [mode_display_names[mode.lower()] for mode in mode_averages.index]
        
        # Create individual figure at 2560x1440
        individual_fig, ax = plt.subplots(figsize=(25.6, 14.4))  # 2560/100, 1440/100 for inches
        
        wedges, texts, autotexts = ax.pie(
            mode_averages,
            labels=labels,  # Use updated labels
            colors=[colors[mode.lower()] for mode in mode_averages.index],
            autopct='%1.1f%%',
            pctdistance=0.85,
            wedgeprops=dict(width=0.5, edgecolor='none'),
        )
        
        # Enhance text properties with larger font
        plt.setp(autotexts, size=14, weight="bold", color="white")
        plt.setp(texts, size=14, color="white")
        
        # Add title
        ax.set_title(f'Average Mode Distribution\nat {poi_display_names[poi]}', 
                    pad=10,  # Reduced padding
                    fontsize=16, 
                    fontweight='bold', 
                    color='white')
        
        # Update legend for individual plots
        legend_elements = [plt.Line2D([0], [0], marker='o', color='w', 
                                    markerfacecolor=colors[mode], 
                                    label=mode_display_names[mode], 
                                    markersize=12)  # Increased marker size
                          for mode in ['car', 'public_transit', 'ped', 'bike']]
        
        ax.legend(handles=legend_elements, 
                 loc='center', 
                 bbox_to_anchor=(0.5, -0.03),  # Moved legend closer to chart
                 ncol=len(legend_elements),
                 frameon=False,
                 fontsize=14)  # Increased font size
        
        # Save individual visualization at 2560x1440
        individual_output_file = os.path.join(OUTPUT_DIR, f'mode_spread_pie_{poi}.jpg')
        plt.savefig(individual_output_file, 
                    dpi=100,  # 100 DPI * 25.6" = 2560px
                    bbox_inches='tight',
                    facecolor='black',
                    edgecolor='none',
                    format='jpg',
                    pad_inches=0.5)
        logger.info(f"Individual visualization for {poi} saved to: {individual_output_file}")
        plt.close()
        
    except Exception as e:
        error_msg = f"Error processing individual visualization for {poi}: {str(e)}"
        logger.error(error_msg)

logger.info("All visualizations complete!") 