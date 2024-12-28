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
        plt.rcParams['figure.facecolor'] = color_scheme['background']
        plt.rcParams['savefig.facecolor'] = color_scheme['background']

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
        """Creates both a donut chart and its legend as separate images with optimized space usage"""
        logger.info(f"Creating chart pair for {category}")
        
        # Get the correct columns and calculate data
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
        nonzero_data = data[data >= 1.0]  # Only keep values >= 1%
        nonzero_data.index = nonzero_data.index.map(self.clean_category_name)
        sorted_data = nonzero_data.sort_values(ascending=False)
        
        colors = ['#4A90E2', '#50E3C2', '#F5A623', '#7ED321', '#B8E986', '#9013FE']

        # Create donut chart with adjusted text positioning
        donut_fig = plt.figure(figsize=(4, 4), dpi=100)
        ax = donut_fig.add_subplot(111)
        
        wedges, texts, autotexts = ax.pie(sorted_data.values,
                                        labels=None,
                                        colors=colors[:len(sorted_data)],
                                        autopct='%1.0f%%',
                                        pctdistance=0.75,
                                        wedgeprops=dict(width=0.6),
                                        textprops={'color': 'white', 'fontsize': 25},  # Increased from 21
                                        radius=1.2)

        # Optimize label placement with adjusted positions
        for i, (wedge, autotext) in enumerate(zip(wedges, autotexts)):
            ang = (wedge.theta2 - wedge.theta1) / 2. + wedge.theta1
            y = np.sin(np.deg2rad(ang))
            x = np.cos(np.deg2rad(ang))

            if sorted_data.values[i] < 5:  # For small values
                autotext.set_color('white')
                autotext.set_fontsize(22)  # Increased from 18
                outside_dist = 1.2
                autotext.set_position((x * outside_dist, y * outside_dist))
            else:
                autotext.set_fontsize(25)  # Increased from 21
                autotext.set_position((x * 0.85, y * 0.85))

        # Add center circle with exact size match
        centre_circle = plt.Circle((0, 0), 0.5, fc=self.color_scheme['background'])
        ax.add_artist(centre_circle)
        
        ax.set_aspect('equal')  # Ensure perfect circle
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)  # Remove all padding
        
        # Create compact legend with larger font
        legend_fig = plt.figure(figsize=(1.8, 3), dpi=100)
        legend_ax = legend_fig.add_subplot(111)
        
        legend_elements = [plt.Rectangle((0, 0), 1, 1, facecolor=colors[i])
                        for i in range(len(sorted_data))]

        legend = legend_ax.legend(legend_elements,
                                sorted_data.index,
                                loc='center',
                                frameon=True,
                                framealpha=1,
                                facecolor='#333333',
                                edgecolor='#444444',
                                fontsize=27,  # Keeping legend size the same
                                labelcolor='white',
                                borderpad=0.2,
                                handletextpad=0.8,
                                handlelength=1.2,
                                handleheight=0.8,
                                borderaxespad=0)

        legend.get_frame().set_linewidth(1)
        plt.setp(legend.get_texts(), linespacing=1.1)  # Tighter line spacing
        
        legend_ax.set_axis_off()
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)  # Remove all padding
        
        return donut_fig, legend_fig

    def save_chart_pair(self, donut_fig, legend_fig, poi_name, chart_type):
        """Saves both the donut chart and legend with minimal padding"""
        if donut_fig is None or legend_fig is None:
            return

        chart_dir = os.path.join(self.output_dir, 'poi_charts', f"{poi_name}-charts")
        os.makedirs(chart_dir, exist_ok=True)
        
        # Save donut chart with zero padding
        donut_path = os.path.join(chart_dir, f"{poi_name}_{chart_type}_donut.png")
        donut_fig.savefig(donut_path,
                        facecolor=self.color_scheme['background'],
                        edgecolor='none',
                        dpi=150,
                        bbox_inches='tight',
                        pad_inches=0)  # No padding
        plt.close(donut_fig)
        
        # Save legend with minimal padding
        legend_path = os.path.join(chart_dir, f"{poi_name}_{chart_type}_legend.png")
        legend_fig.savefig(legend_path,
                        facecolor=self.color_scheme['background'],
                        edgecolor='none',
                        dpi=150,
                        bbox_inches='tight',
                        pad_inches=0)  # No padding
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