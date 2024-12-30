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
        container = dbc.Card([
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
                        style={
                            'position': 'absolute',
                            'left': '0',
                            'top': '0',
                            'objectFit': 'contain',
                            'backgroundColor': '#2d2d2d',
                            'width': '160px',
                            'height': '160px',
                            'display': 'block'
                        }
                    ),
                    # Legend - wider for frequency chart
                    html.Img(
                        id=f'{id_prefix}-legend',
                        style={
                            'position': 'absolute',
                            'left': '160px',
                            'top': '0',
                            'objectFit': 'contain',
                            'backgroundColor': '#2d2d2d',
                            'width': '140px' if id_prefix == 'frequency' else '110px',
                            'height': '160px',
                            'display': 'block'
                        }
                    )
                ], id=f'{id_prefix}-container', style={
                    'height': '160px',
                    'width': '300px' if id_prefix == 'frequency' else '270px',
                    'position': 'relative',
                    'backgroundColor': '#2d2d2d',
                    'overflow': 'hidden',
                    'margin': '0 auto',
                    'fontSize': '0'
                })
            ], className="bg-dark p-0", style={
                'height': '160px',
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'padding': '0 !important',
                'backgroundColor': '#2d2d2d'
            })
        ], className="bg-dark border-secondary mb-2")

        # Add clientside callback to log container dimensions
        self.app.clientside_callback(
            """
            function(n) {
                const container = document.getElementById(n);
                if (container) {
                    const rect = container.getBoundingClientRect();
                    console.log(`Container ${n} dimensions:`, {
                        width: rect.width,
                        height: rect.height,
                        top: rect.top,
                        left: rect.left
                    });
                }
                return window.dash_clientside.no_update;
            }
            """,
            dash.Output(f'{id_prefix}-container', 'data-dimensions', allow_duplicate=True),
            dash.Input(f'{id_prefix}-container', 'id'),
            prevent_initial_call=True
        )

        return container

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
                            }),
                        # Add a div to store map dimensions
                        html.Div(id='map-debug-info', style={'display': 'none'})
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
                    # Map Column
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader(
                                "Interactive Map", 
                                className="bg-dark text-white py-1 border-secondary",
                                style={'fontSize': '1.2rem'}
                            ),
                            dbc.CardBody([
                                # Container div with debug ID
                                html.Div([
                                    dcc.Graph(
                                        id='map',
                                        config={
                                            'displayModeBar': True,
                                            'scrollZoom': True,
                                            'responsive': True
                                        },
                                        style={
                                            'height': '100%',
                                            'width': '100%'
                                        }
                                    )
                                ], id='map-container', style={
                                    'height': '600px',
                                    'width': '100%',
                                    'position': 'relative'
                                })
                            ], className="bg-dark p-0", id='map-card-body')
                        ], className="bg-dark border-secondary h-100", id='map-card')
                    ], width=8, className="pe-2"),
                    
                    # Charts Column
                    dbc.Col([
                        html.Div([
                            self.create_chart_container("Repeat Trips", "frequency"),
                            self.create_chart_container("Travel Mode", "mode"),
                            self.create_chart_container("Trip Purpose", "purpose")
                        ], style={'maxWidth': '340px', 'margin': '0 auto'})  # Constrain width
                    ], width=4, className="ps-2")
                    
                ], className="g-2 mb-4")
                
            ], fluid=True, className="p-3", style={'backgroundColor': '#1a1a1a', 'minHeight': '100vh'})

            # Enhanced debug callbacks
            self.app.clientside_callback(
                """
                function(n) {
                    function logDimensions(element, label) {
                        if (element) {
                            const rect = element.getBoundingClientRect();
                            console.log(`${label} dimensions:`, {
                                width: rect.width,
                                height: rect.height,
                                top: rect.top,
                                left: rect.left,
                                timestamp: new Date().getTime()
                            });
                        }
                    }

                    // Log dimensions of all relevant containers
                    logDimensions(document.getElementById('map-container'), 'Map container');
                    logDimensions(document.getElementById('map-card-body'), 'Map card body');
                    logDimensions(document.getElementById('map-card'), 'Map card');
                    
                    // Log the actual map element
                    const mapElement = document.querySelector('.js-plotly-plot');
                    logDimensions(mapElement, 'Plotly map element');

                    if (window.dash_clientside) {
                        // Trigger resize after a delay
                        setTimeout(function() {
                            console.log('Triggering resize event:', new Date().getTime());
                            window.dispatchEvent(new Event('resize'));
                            
                            // Log dimensions again after resize
                            setTimeout(function() {
                                console.log('Post-resize dimensions:');
                                logDimensions(mapElement, 'Plotly map element (post-resize)');
                            }, 100);
                        }, 50);
                    }
                    return window.dash_clientside.no_update;
                }
                """,
                dash.Output('map-debug-info', 'data-debug'),
                [dash.Input('map', 'id'),
                dash.Input('map', 'figure')],
                prevent_initial_call=False  # Changed to false to catch initial render
            )
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