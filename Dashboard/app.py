# Main dashboard script

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
from flask_caching import Cache
from data_loader import DataLoader
from chart_utils import ChartCreator
from map_utils import MapCreator
from config import COLOR_SCHEME, CHART_COLORS, BASE_DIR, OUTPUT_DIR
import logging
import traceback
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DashboardApp:
    def __init__(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.index_string = self.app.index_string.replace(
            '</head>',
            '<style>body { font-size: 1.5rem; } .Select-value-label { color: black !important; font-size: 1.5rem; }</style></head>'
        )
        self.cache = Cache(self.app.server, config={'CACHE_TYPE': 'SimpleCache'})
        self.data_loader = DataLoader(BASE_DIR, OUTPUT_DIR)
        self.chart_creator = ChartCreator(COLOR_SCHEME, CHART_COLORS)
        self.map_creator = MapCreator(COLOR_SCHEME)
        
        self.zones = self.data_loader.load_zones()
        self.poi_df = self.data_loader.load_poi_data()
        self.trip_data = self.data_loader.load_trip_data()
        
        self.poi_options = [{'label': row['name'], 'value': row['name']} for _, row in self.poi_df.iterrows()]
        self.poi_coordinates = dict(zip(self.poi_df['name'], zip(self.poi_df['lat'], self.poi_df['lon'])))
        
        self.setup_layout()
        self.setup_callbacks()

    def setup_layout(self):
        self.app.layout = dbc.Container([
            dbc.Row([
                dbc.Col(html.H1("Beer Sheva Mobility Dashboard", 
                               className="text-center mb-4", 
                               style={'font-size': '3rem'}), 
                       width=12)
            ], justify="center", className="mb-4"),
            
            # Center the controls with less width
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dcc.Dropdown(
                                id='poi-selector',
                                options=self.poi_options,
                                value=self.poi_options[0]['value'],
                                className="mb-3 text-center"
                            ),
                            dbc.RadioItems(
                                id='trip-type-selector',
                                options=[
                                    {'label': 'Inbound', 'value': 'inbound'},
                                    {'label': 'Outbound', 'value': 'outbound'}
                                ],
                                value='inbound',
                                inline=True,
                                className="text-center"
                            )
                        ])
                    ], className="mb-4")
                ], width={"size": 4, "offset": 4})  
            ], justify="start"),
            
            # Add padding to main content
            dbc.Row([
                dbc.Col([], width=1),  # Left buffer
                dbc.Col([
                    # Map
                    dbc.Row([
                        dbc.Col(dcc.Graph(id='map'), width=12)
                    ], className="mb-4"),
                    
                    # Charts
                    dbc.Row([
                        dbc.Col(html.Img(id='frequency-chart', src='', 
                                       style={'width': '100%', 'height': 'auto'}), 
                               width=4),
                        dbc.Col(html.Img(id='mode-chart', src='', 
                                       style={'width': '100%', 'height': 'auto'}), 
                               width=4),
                        dbc.Col(html.Img(id='purpose-chart', src='', 
                                       style={'width': '100%', 'height': 'auto'}), 
                               width=4)
                    ], className="mb-4"),
                    
                    dbc.Row([
                        dbc.Col(dcc.Graph(id='time-chart'), width=12)
                    ])
                ], width=10),  # Main content
                dbc.Col([], width=1)  # Right buffer
            ])
        ], fluid=True, 
        style={'backgroundColor': COLOR_SCHEME['background'], 
               'color': COLOR_SCHEME['text'], 
               'font-size': '1.5rem',
               'padding': '20px'})

    def setup_callbacks(self):
        @self.app.callback(
            [dash.Output('map', 'figure'),
             dash.Output('mode-chart', 'src'),
             dash.Output('purpose-chart', 'src'),
             dash.Output('frequency-chart', 'src'),
             dash.Output('time-chart', 'figure'),
             dash.Output('poi-selector', 'value')],
            [dash.Input('poi-selector', 'value'),
             dash.Input('trip-type-selector', 'value'),
             dash.Input('map', 'clickData')]
        )
        def update_dashboard(selected_poi, trip_type, click_data):
            ctx = dash.callback_context
            trigger = ctx.triggered[0]['prop_id'].split('.')[0]

            if trigger == 'map' and click_data and 'points' in click_data:
                clicked_poi = click_data['points'][0].get('customdata')
                if clicked_poi and clicked_poi in self.poi_df['name'].values:
                    selected_poi = clicked_poi
                else:
                    # If clicked on a zone or non-POI area, don't update
                    raise PreventUpdate()

            try:
                logger.info(f"Updating dashboard for {selected_poi} ({trip_type})")
                df = self.trip_data[(selected_poi, trip_type)]
                
                map_fig = self.map_creator.create_map(df, selected_poi, trip_type, self.zones, self.poi_coordinates)
                
                # Generate charts on-demand
                self.create_and_save_pie_charts(selected_poi, df)
                
                mode_chart_src = self.chart_creator.load_pie_chart(selected_poi.replace(' ', '_'), 'avg_trip_mode')
                purpose_chart_src = self.chart_creator.load_pie_chart(selected_poi.replace(' ', '_'), 'avg_trip_purpose')
                frequency_chart_src = self.chart_creator.load_pie_chart(selected_poi.replace(' ', '_'), 'avg_trip_frequency')
                
                time_chart = self.chart_creator.create_time_chart(df)
                
                logger.info("Dashboard update completed successfully")
                return map_fig, mode_chart_src, purpose_chart_src, frequency_chart_src, time_chart, selected_poi
            except Exception as e:
                logger.error(f"Error updating dashboard: {str(e)}")
                logger.error(traceback.format_exc())
                # Return empty figures/charts in case of error
                return go.Figure(), '', '', '', go.Figure(), selected_poi

    def run_server(self, debug=True):
        self.app.run_server(debug=debug)

    def create_and_save_pie_charts(self, poi_name, df):
        for category, title in [('mode', 'Average Trip Modes'), 
                                ('purpose', 'Average Trip Purposes'), 
                                ('frequency', 'Average Trip Frequencies')]:
            fig = self.chart_creator.create_pie_chart(df, category, f'{poi_name} - {title}')
            self.chart_creator.save_pie_chart(fig, poi_name.replace(' ', '_'), f'avg_trip_{category}')

if __name__ == '__main__':
    dashboard = DashboardApp()
    dashboard.app.run_server(host='0.0.0.0', debug=True)
