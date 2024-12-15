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
        # Remove prefixes like 'mode_', 'purpose_', 'frequency_'
        if '_' in category:
            category = category.split('_', 1)[1]
        
        # Replace underscores with spaces and capitalize each word
        category = ' '.join(word.capitalize() for word in category.replace('_', ' ').split())
        
        return category

    def create_pie_chart(self, df, category, title):
        logger.info(f"Creating pie chart for {category}")
        
        if category == 'frequency':
            columns = [col for col in df.columns if col.startswith('frequency_')]
        elif category == 'mode':
            columns = [col for col in df.columns if col.startswith('mode_')]
        elif category == 'purpose':
            columns = [col for col in df.columns if col.startswith('purpose_')]
        else:
            logger.warning(f"Invalid category: {category}")
            return None

        data = self.calculate_mean_percentages(df, columns)
        
        # Filter out values less than 0.04% and log the results
        nonzero_data = data[data > 0.05]
        logger.info(f"Original categories: {len(data)}, Categories > 0.1%: {len(nonzero_data)}")
        logger.debug(f"Category percentages: {nonzero_data.to_dict()}")

        # Clean category names
        nonzero_data.index = nonzero_data.index.map(self.clean_category_name)
        
        fig, ax = plt.subplots(figsize=(12, 8))
        colors = [self.color_scheme['primary'], self.color_scheme['secondary']] + ['#28A745', '#FFC107', '#17A2B8', '#6C757D']
        
        sorted_data = nonzero_data.sort_values(ascending=False)
        
        wedges, texts, autotexts = ax.pie(sorted_data.values, 
                                          labels=None,
                                          colors=colors[:len(sorted_data)],
                                          autopct=lambda pct: f'{pct:.1f}%' if pct > 3 else '',
                                          pctdistance=0.8,
                                          startangle=90,
                                          wedgeprops=dict(width=0.5))
        
        # Adjust autotext sizes
        for autotext in autotexts:
            autotext.set_color(self.color_scheme['text'])
            autotext.set_fontsize(22)
        
        # Add a legend with increased font size and moved to upper right
        legend_labels = [f'{label}: {value:.1f}%' for label, value in sorted_data.items()]
        ax.legend(wedges, legend_labels, 
                 title=category.capitalize(), 
                 loc="upper right", 
                 bbox_to_anchor=(1.3, 1.1), 
                 fontsize=22,
                 title_fontsize=24)
        
        # Title
        ax.set_title(category.capitalize(), 
                    color=self.color_scheme['text'], 
                    fontsize=26,
                    pad=20)
        
        fig.patch.set_facecolor(self.color_scheme['background'])
        ax.set_facecolor(self.color_scheme['background'])
        
        plt.tight_layout()
        
        return fig

    def save_pie_chart(self, fig, poi_name, chart_type):
        if fig is None:
            return

        chart_dir = os.path.join(self.output_dir, 'poi_charts', f"{poi_name}-charts")
        os.makedirs(chart_dir, exist_ok=True)
        
        filename = f"{poi_name}_{chart_type}.png"
        filepath = os.path.join(chart_dir, filename)
        
        print(f"Saving chart at: {filepath}")
        fig.savefig(filepath, facecolor=self.color_scheme['background'], edgecolor='none', bbox_inches='tight', dpi=300)
        plt.close(fig)

    def load_pie_chart(self, poi_name, chart_type):
        image_path = os.path.join(self.output_dir, 'poi_charts', f"{poi_name}-charts", f"{poi_name}_{chart_type}.png")
        print(f"Attempting to load chart from: {image_path}")
        try:
            with open(image_path, 'rb') as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
            return f'data:image/png;base64,{encoded_image}'
        except FileNotFoundError:
            print(f"Warning: Chart image not found: {image_path}")
            return ''

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