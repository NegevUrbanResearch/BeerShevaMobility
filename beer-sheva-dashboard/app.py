# Main dashboard script

import dash
from dash import html, dcc, Input, Output
import dash_bootstrap_components as dbc
from flask_caching import Cache
from data_loader import DataLoader
from chart_utils import ChartCreator
from map_utils import MapCreator
from config import COLOR_SCHEME, CHART_COLORS
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
            '''
            <style>
                body { 
                    font-size: 1.5rem;
                    background-color: #1a1a1a !important;
                    min-height: 100vh;
                    margin: 0;
                    padding: 0;
                }
                .Select-value-label { 
                    color: black !important;
                    font-size: 1.5rem;
                }
                #root {
                    min-height: 100vh;
                    background-color: #1a1a1a;
                }
            </style>
            </head>
            '''
        )
        self.cache = Cache(self.app.server, config={'CACHE_TYPE': 'SimpleCache'})
        
        self.data_loader = DataLoader()
        self.chart_creator = ChartCreator(COLOR_SCHEME, CHART_COLORS)
        self.map_creator = MapCreator(COLOR_SCHEME)
        
        self.zones = self.data_loader.load_zones()
        self.poi_df = self.data_loader.load_poi_data()
        self.trip_data = self.data_loader.load_trip_data()
        
        self.poi_df, self.trip_data = self.data_loader.clean_poi_names(self.poi_df, self.trip_data)
        self.poi_coordinates = dict(zip(self.poi_df['name'], 
                                      zip(self.poi_df['lat'], self.poi_df['lon'])))
        
        self.setup_layout()
        self.setup_callbacks()

    def create_chart_container(self, title, id_prefix):
        return dbc.Card([
            dbc.CardHeader(
                title,
                className="bg-dark text-white py-1 border-secondary",
                style={'fontSize': '1.2rem'}
            ),
            dbc.CardBody([
                html.Div([
                    # Donut chart
                    html.Img(
                        id=f'{id_prefix}-donut',
                        className="h-100",
                        style={
                            'position': 'absolute',
                            'left': '0',
                            'top': '0',
                            'objectFit': 'contain',
                            'backgroundColor': '#2d2d2d',
                            'width': '60%',
                            'maxHeight': '160px'
                        }
                    ),
                    # Legend
                    html.Img(
                        id=f'{id_prefix}-legend',
                        className="h-100",
                        style={
                            'position': 'absolute',
                            'right': '0',
                            'top': '0',
                            'objectFit': 'contain',
                            'backgroundColor': '#2d2d2d',
                            'width': '40%',
                            'maxHeight': '160px'
                        }
                    )
                ], style={
                    'height': '160px',
                    'position': 'relative',
                    'backgroundColor': '#2d2d2d'
                })
            ], className="bg-dark p-1", style={'height': '160px'})
        ], className="bg-dark border-secondary mb-2")

    def setup_layout(self):
        self.app.layout = dbc.Container([
            # Debug info row
            dbc.Row([
                dbc.Col([
                    html.Div(id='debug-info', 
                        className="text-muted",
                        style={
                            'position': 'fixed', 
                            'top': '0', 
                            'right': '0', 
                            'zIndex': 1000,
                            'backgroundColor': '#2d2d2d',
                            'color': '#fff',
                            'padding': '4px 8px',
                            'fontSize': '12px'
                        })
                ])
            ]),
            
            # Header Row with integrated controls
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H1("Beer Sheva Mobility Dashboard", 
                            style={
                                'fontSize': '2rem', 
                                'color': '#fff',
                                'marginRight': '2rem',
                                'marginBottom': '0.5rem',
                                'textAlign': 'center'
                            }
                        ),
                        html.Div([
                            dbc.RadioItems(
                                id='trip-type-selector',
                                options=[
                                    {'label': 'Inbound', 'value': 'inbound'},
                                    {'label': 'Outbound', 'value': 'outbound'}
                                ],
                                value='inbound',
                                inline=True,
                                style={
                                    'color': 'white',
                                    'fontSize': '1rem'
                                },
                                inputStyle={
                                    'marginRight': '5px'
                                },
                                labelStyle={
                                    'marginRight': '15px',
                                    'fontWeight': '300'
                                }
                            )
                        ], style={
                            'textAlign': 'center',
                            'marginBottom': '1rem'
                        })
                    ])
                ], width=12)
            ], className="mb-3"),
            
            # Main Content Row
            dbc.Row([
                # Map Column (70% width)
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(
                            "Interactive Map", 
                            className="bg-dark text-white py-1 border-secondary",
                            style={'fontSize': '1.2rem'}
                        ),
                        dbc.CardBody([
                            dcc.Graph(
                                id='map',
                                className="h-100 w-100",
                                config={
                                    'displayModeBar': True,
                                    'scrollZoom': True,
                                    'responsive': True
                                },
                                figure={
                                    'layout': {
                                        'template': 'plotly_dark',
                                        'paper_bgcolor': '#2d2d2d',
                                        'plot_bgcolor': '#2d2d2d',
                                        'margin': {"r":0,"t":0,"l":0,"b":0},
                                        'height': 600
                                    }
                                }
                            )
                        ], className="bg-dark p-0", style={'height': '600px'})
                    ], className="bg-dark h-100 border-secondary")
                ], width=8, className="pe-2"),
                
                # Charts Column (30% width)
                dbc.Col([
                    self.create_chart_container("Trip Frequency", "frequency"),
                    self.create_chart_container("Travel Mode", "mode"),
                    self.create_chart_container("Trip Purpose", "purpose")
                ], width=4, className="ps-2")
                
            ], className="g-2", style={'marginBottom': '2rem'})
        ], fluid=True, 
        className="p-3",
        style={
            'backgroundColor': '#1a1a1a',
            'minHeight': '100vh',
            'height': '100%'
        })

    def setup_callbacks(self):
        @self.app.callback(
            [dash.Output('map', 'figure'),
             dash.Output('mode-donut', 'src'),
             dash.Output('mode-legend', 'src'),
             dash.Output('purpose-donut', 'src'),
             dash.Output('purpose-legend', 'src'),
             dash.Output('frequency-donut', 'src'),
             dash.Output('frequency-legend', 'src')],
            [dash.Input('trip-type-selector', 'value'),
             dash.Input('map', 'clickData')]
        )

        def update_dashboard(trip_type, click_data):
            # Initialize with first POI if no click data
            if not click_data or 'points' not in click_data:
                selected_poi = self.poi_df['name'].iloc[0]
            else:
                clicked_poi = click_data['points'][0].get('customdata')
                if not clicked_poi or clicked_poi not in self.poi_df['name'].values:
                    raise PreventUpdate()
                selected_poi = clicked_poi

            try:
                logger.info(f"Updating dashboard for {selected_poi} ({trip_type})")
                df = self.trip_data[(selected_poi, trip_type)]
                
                map_fig = self.map_creator.create_map(df, selected_poi, trip_type, self.zones, self.poi_coordinates)
                
                # Generate charts
                self.chart_creator.create_and_save_charts(selected_poi, df)
                
                # Load all chart pairs
                mode_donut, mode_legend = self.chart_creator.load_chart_pair(
                    selected_poi.replace(' ', '_'), 'avg_trip_mode')
                purpose_donut, purpose_legend = self.chart_creator.load_chart_pair(
                    selected_poi.replace(' ', '_'), 'avg_trip_purpose')
                frequency_donut, frequency_legend = self.chart_creator.load_chart_pair(
                    selected_poi.replace(' ', '_'), 'avg_trip_frequency')
                
                return (map_fig,
                       mode_donut, mode_legend,
                       purpose_donut, purpose_legend,
                       frequency_donut, frequency_legend)
            except Exception as e:
                logger.error(f"Error updating dashboard: {str(e)}")
                logger.error(traceback.format_exc())
                return go.Figure(), '', '', '', '', '', ''

    def run_server(self, debug=True):
        self.app.run_server(debug=debug)

if __name__ == '__main__':
    dashboard = DashboardApp()
    dashboard.app.run_server(host='0.0.0.0', debug=True)