import matplotlib
matplotlib.use('Agg')  # Use the 'Agg' backend
import matplotlib.pyplot as plt

import plotly.graph_objs as go
import pandas as pd
import numpy as np
import base64
import os
from config import OUTPUT_DIR, COLOR_SCHEME, CHART_COLORS, BASE_DIR

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

    def create_pie_chart(self, df, category, title):
        if category == 'frequency':
            columns = [col for col in df.columns if col.startswith('frequency_')]
        elif category == 'mode':
            columns = [col for col in df.columns if col.startswith('mode_')]
        elif category == 'purpose':
            columns = [col for col in df.columns if col.startswith('purpose_')]
        else:
            return None

        data = self.calculate_mean_percentages(df, columns)
        
        fig, ax = plt.subplots(figsize=(12, 8))  # Increase figure size for better readability
        colors = [self.color_scheme['primary'], self.color_scheme['secondary']] + ['#28A745', '#FFC107', '#17A2B8', '#6C757D']
        
        sorted_data = data.sort_values(ascending=False)
        
        wedges, texts, autotexts = ax.pie(sorted_data.values, 
                                          labels=None,  # Remove labels from pie chart
                                          colors=colors[:len(sorted_data)],
                                          autopct=lambda pct: f'{pct:.1f}%' if pct > 3 else '',
                                          pctdistance=0.8,
                                          startangle=90,
                                          wedgeprops=dict(width=0.5))
        
        # Adjust autotext sizes
        for autotext in autotexts:
            autotext.set_color(self.color_scheme['text'])
            autotext.set_fontsize(15)  # Increased from 10
        
        # Add a legend with increased font size
        legend_labels = [f'{label}: {value:.1f}%' for label, value in sorted_data.items()]
        ax.legend(wedges, legend_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0.5), fontsize=15)  # Increased from 10
        
        ax.set_title(title, color=self.color_scheme['text'], fontsize=24, pad=20)  # Increased from 16
        
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

    def create_time_chart(self, df):
        time_columns = [col for col in df.columns if col.startswith('arrival_')]
        
        if not time_columns:
            return go.Figure()

        time_data = (df[time_columns] * df['total_trips'].values[:, None]).sum() / df['total_trips'].sum()
        time_data = time_data.sort_index()
        
        hours = [col.split('_')[1] for col in time_data.index]
        
        fig = go.Figure(data=[go.Bar(
            x=hours,
            y=time_data.values,
            marker_color=self.chart_colors[0]
        )])
        
        fig.update_layout(
            title='Trip Distribution by Hour',
            xaxis_title='Hour',
            yaxis_title='Percentage of Trips',
            paper_bgcolor=self.color_scheme['background'],
            plot_bgcolor=self.color_scheme['background'],
            font_color=self.color_scheme['text'],
            font=dict(size=18)  # Increased font size
        )
        
        return fig

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
    
    print(f"Testing create_time_chart() for {test_poi} ({test_trip_type}):")
    fig = chart_creator.create_time_chart(test_df)
    
    # Save the test time chart
    import plotly.io as pio
    pio.write_html(fig, file='test_time_chart.html', auto_open=True)
    print("Test time chart saved as 'test_time_chart.html'")
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
