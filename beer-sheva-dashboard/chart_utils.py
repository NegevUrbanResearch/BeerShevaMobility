import matplotlib
matplotlib.use('Agg')  # Use the 'Agg' backend
import matplotlib.pyplot as plt
import plotly.graph_objs as go
import pandas as pd
import numpy as np
import base64
import os
import logging

from config import OUTPUT_DIR, COLOR_SCHEME, CHART_COLORS, BASE_DIR

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChartCreator:
    def __init__(self, color_scheme, chart_colors):
        self.color_scheme = color_scheme
        self.chart_colors = chart_colors
        self.output_dir = OUTPUT_DIR

    def calculate_mean_percentages(self, df, columns):
        data = df[columns]
        total = data.sum(axis=1)
        percentages = data.div(total, axis=0) * 100
        return percentages.mean()

    def clean_category_name(self, category):
        if '_' in category:
            category = category.split('_', 1)[1]
        return ' '.join(word.capitalize() for word in category.replace('_', ' ').split())
   
    def create_chart_pair(self, df, category, title):
        """Creates both a donut chart and its legend as separate images"""
        logger.info(f"Creating chart pair for {category}")
        
        # Get the correct columns based on category
        if category == 'frequency':
            columns = [col for col in df.columns if col.startswith('frequency_')]
        elif category == 'mode':
            columns = [col for col in df.columns if col.startswith('mode_')]
        elif category == 'purpose':
            columns = [col for col in df.columns if col.startswith('purpose_')]
        else:
            logger.warning(f"Invalid category: {category}")
            return None, None

        # Calculate percentages
        data = self.calculate_mean_percentages(df, columns)
        nonzero_data = data[data > 0.05]
        nonzero_data.index = nonzero_data.index.map(self.clean_category_name)
        sorted_data = nonzero_data.sort_values(ascending=False)
        
        # Colors
        colors = ['#4A90E2', '#50E3C2', '#F5A623', '#7ED321', '#B8E986', '#9013FE']

        # Create donut chart with adjusted size and simplified design
        donut_fig = plt.figure(figsize=(4, 4), dpi=100)  # Reduced figure size
        ax = donut_fig.add_subplot(111)
        
        wedges, _, _ = ax.pie(sorted_data.values,
                            labels=None,
                            colors=colors[:len(sorted_data)],
                            autopct='',
                            pctdistance=0.75,
                            wedgeprops=dict(width=0.5))
        
        # Add center circle for donut effect
        centre_circle = plt.Circle((0,0), 0.45, fc=self.color_scheme['background'])
        ax.add_artist(centre_circle)
        
        # Removed percentage text from center
        
        ax.set_facecolor(self.color_scheme['background'])
        donut_fig.patch.set_facecolor(self.color_scheme['background'])
        plt.tight_layout(pad=0.1)  # Reduced padding

        # Create legend with optimized spacing and larger elements
        legend_fig = plt.figure(figsize=(4, 6), dpi=100)
        legend_ax = legend_fig.add_subplot(111)
        
        # Create larger proxy artists for legend
        legend_elements = [plt.Rectangle((0, 0), 1, 1.5, facecolor=colors[i])  # Increased size
                        for i in range(len(sorted_data))]

        # Create legend with optimized styling
        legend = legend_ax.legend(legend_elements,
                                [f'{label} ({value:.1f}%)' for label, value in sorted_data.items()],
                                loc='center',
                                frameon=True,
                                framealpha=1,
                                facecolor='#333333',
                                edgecolor='#444444',
                                fontsize=18,  # Increased font size
                                labelcolor='white',
                                borderpad=0.5,  # Reduced padding
                                handletextpad=1.0,  # Reduced padding between handle and text
                                handlelength=1.5,  # Increased handle size
                                handleheight=1.2,  # Increased handle height
                                borderaxespad=0,
                                ncol=1,
                                mode="expand")

        # Adjust legend box appearance
        legend.get_frame().set_linewidth(1)
        
        # Optimize spacing between items
        plt.setp(legend.get_texts(), linespacing=1.2)  # Reduced line spacing
        
        # Hide axis and set background
        legend_ax.set_axis_off()
        legend_ax.set_facecolor(self.color_scheme['background'])
        legend_fig.patch.set_facecolor(self.color_scheme['background'])

        # Maximize legend size within figure
        legend_fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)
        
        return donut_fig, legend_fig

    def save_chart_pair(self, donut_fig, legend_fig, poi_name, chart_type):
        """Saves both the donut chart and legend as separate files with proper DPI"""
        if donut_fig is None or legend_fig is None:
            return

        chart_dir = os.path.join(self.output_dir, 'poi_charts', f"{poi_name}-charts")
        os.makedirs(chart_dir, exist_ok=True)
        
        # Save donut chart with adjusted padding
        donut_path = os.path.join(chart_dir, f"{poi_name}_{chart_type}_donut.png")
        donut_fig.savefig(donut_path,
                        facecolor=self.color_scheme['background'],
                        edgecolor='none',
                        dpi=150,
                        bbox_inches='tight',
                        pad_inches=0.1)  # Reduced padding
        plt.close(donut_fig)
        
        # Save legend with adjusted padding
        legend_path = os.path.join(chart_dir, f"{poi_name}_{chart_type}_legend.png")
        legend_fig.savefig(legend_path,
                        facecolor=self.color_scheme['background'],
                        edgecolor='none',
                        dpi=150,
                        bbox_inches='tight',
                        pad_inches=0.1)  # Reduced padding
        plt.close(legend_fig)

    def create_and_save_charts(self, poi_name, df):
        """Creates and saves all chart pairs"""
        for category, title in [('mode', 'Travel Modes'), 
                              ('purpose', 'Trip Purposes'), 
                              ('frequency', 'Trip Frequencies')]:
            donut_fig, legend_fig = self.create_chart_pair(df, category, title)
            self.save_chart_pair(donut_fig, legend_fig, poi_name.replace(' ', '_'), f'avg_trip_{category}')

    def load_chart_pair(self, poi_name, chart_type):
        """Loads both donut and legend images and returns their encoded versions"""
        chart_dir = os.path.join(self.output_dir, 'poi_charts', f"{poi_name}-charts")
        
        donut_path = os.path.join(chart_dir, f"{poi_name}_{chart_type}_donut.png")
        legend_path = os.path.join(chart_dir, f"{poi_name}_{chart_type}_legend.png")
        
        try:
            with open(donut_path, 'rb') as donut_file:
                donut_encoded = base64.b64encode(donut_file.read()).decode('utf-8')
            with open(legend_path, 'rb') as legend_file:
                legend_encoded = base64.b64encode(legend_file.read()).decode('utf-8')
            return f'data:image/png;base64,{donut_encoded}', f'data:image/png;base64,{legend_encoded}'
        except FileNotFoundError as e:
            logger.warning(f"Chart image not found: {e}")
            return '', ''

def test_chart_creator():
    from data_loader import DataLoader
    
    loader = DataLoader(BASE_DIR, OUTPUT_DIR)
    poi_df = loader.load_poi_data()
    trip_data = loader.load_trip_data()
    
    chart_creator = ChartCreator(COLOR_SCHEME, CHART_COLORS)
    
    # Test with the first POI and trip type
    test_poi = poi_df['name'].iloc[0]
    test_trip_type = 'inbound'
    test_df = trip_data[(test_poi, test_trip_type)]
    
    print("\nTesting create_pie_chart() and save_pie_chart():")
    for category, title in [('mode', 'Average Trip Modes'), 
                            ('purpose', 'Average Trip Purposes'), 
                            ('frequency', 'Average Trip Frequencies')]:
        fig = chart_creator.create_pie_chart(test_df, category, f'{test_poi} - {title}')
        chart_creator.save_pie_chart(fig, test_poi.replace(' ', '_'), f'avg_trip_{category}')
        print(f"Created and saved {category} chart")
    
    print("\nTesting load_pie_chart():")
    for chart_type in ['avg_trip_mode', 'avg_trip_purpose', 'avg_trip_frequency']:
        src = chart_creator.load_pie_chart(test_poi.replace(' ', '_'), chart_type)
        print(f"Loaded {chart_type} chart: {'Success' if src else 'Failed'}")

if __name__ == "__main__":
    test_chart_creator()