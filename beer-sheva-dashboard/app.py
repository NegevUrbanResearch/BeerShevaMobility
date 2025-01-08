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
                    background-color: #000000 !important;
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
        
        # Filter out unwanted POIs by coordinates
        coords_to_exclude = [
            (31.2244375, 34.8010625),  # Yes Planet
            (31.2698125, 34.7815625),  # K collage
            (31.1361875, 34.7898125),  # Ramat Hovav Industry
        ]
        
        # Create mask for filtering (using approximate float comparison)
        mask = ~self.poi_df.apply(lambda row: any(
            abs(row['lat'] - lat) < 0.0001 and abs(row['lon'] - lon) < 0.0001
            for lat, lon in coords_to_exclude
        ), axis=1)
        
        self.poi_df = self.poi_df[mask]
        
        # Load trip data after filtering POIs
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
                style={'fontSize': '2.4rem'}
            ),
            dbc.CardBody([
                html.Div([
                    # Donut chart - increased by additional 5%
                    html.Img(
                        id=f'{id_prefix}-donut',
                        style={
                            'position': 'absolute',
                            'left': '0',
                            'top': '0',
                            'objectFit': 'contain',
                            'backgroundColor': '#2d2d2d',
                            'width': '277px',  # Increased from 264px
                            'height': '277px',  # Increased from 264px
                            'display': 'block'
                        }
                    ),
                    # Legend - increased by additional 5%
                    html.Img(
                        id=f'{id_prefix}-legend',
                        style={
                            'position': 'absolute',
                            'left': '277px',  # Adjusted to match new donut width
                            'top': '0',
                            'objectFit': 'contain',
                            'backgroundColor': '#2d2d2d',
                            'width': '245px' if id_prefix == 'frequency' else '208px',  # Increased from 231px/198px
                            'height': '277px',  # Increased from 264px
                            'display': 'block'
                        }
                    )
                ], id=f'{id_prefix}-container', style={
                    'height': '277px',  # Increased from 264px
                    'width': '520px' if id_prefix == 'frequency' else '485px',  # Increased from 495px/462px
                    'position': 'relative',
                    'backgroundColor': '#2d2d2d',
                    'overflow': 'hidden',
                    'margin': '0 auto',
                    'fontSize': '0'
                })
            ], className="bg-dark p-0", style={
                'height': '277px',  # Increased from 264px
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'padding': '0 !important',
                'backgroundColor': '#2d2d2d'
            })
        ], className="bg-dark border-secondary mb-4")  # Increased margin-bottom

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
                    html.Div(id='map-debug-info', style={'display': 'none'})
                ])
            ]),
            
            # Header Row - reduce margin
            dbc.Row([
                dbc.Col([
                    html.Div([
                        # Container for centered title
                        html.Div([
                            html.H1("Beer Sheva Mobility Dashboard", 
                                style={
                                    'fontSize': '4rem',
                                    'color': '#fff',
                                    'marginBottom': '0',
                                    'textAlign': 'center',  # Center the text
                                    'width': '100%'  # Take full width of container
                                }
                            ),
                        ], style={
                            'position': 'absolute',  # Position absolutely
                            'left': '0',
                            'right': '0',
                            'zIndex': '0'  # Place behind controls
                        }),
                        # Controls on the right
                        html.Div([
                            dbc.RadioItems(
                                id='trip-type-selector',
                                options=[
                                    {'label': 'Inbound', 'value': 'inbound'},
                                    {'label': 'Outbound', 'value': 'outbound'}
                                ],
                                value='inbound',
                                inline=False,
                                style={
                                    'color': 'white',
                                    'fontSize': '1.8rem'
                                },
                                inputStyle={
                                    'marginRight': '8px'
                                },
                                labelStyle={
                                    'display': 'block',
                                    'marginBottom': '5px',
                                    'fontWeight': '300'
                                }
                            )
                        ], style={
                            'display': 'inline-block',
                            'verticalAlign': 'top',
                            'marginTop': '0.5rem',
                            'position': 'relative',  # Position relative to container
                            'zIndex': '1'  # Place in front of title
                        })
                    ], style={
                        'display': 'flex',
                        'justifyContent': 'flex-end',  # Align controls to the right
                        'alignItems': 'flex-start',
                        'maxWidth': '1525px',
                        'margin': '0 auto',
                        'padding': '0 15px',
                        'position': 'relative'  # Enable absolute positioning of children
                    })
                ], width=12)
            ], className="mb-1"),
            
            # Main Content Row - reduce top margin
            dbc.Row([
                # Map Column - adjusted container height and positioning
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Span("Interactive Map", id="map-title"),
                            html.Span(id="selected-poi", style={'marginLeft': '10px', 'fontWeight': 'normal'})
                        ], className="bg-dark text-white py-1 border-secondary", style={'fontSize': '2.4rem'}),
                        dbc.CardBody([
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
                            ], style={
                                'height': '100%',
                                'width': '100%',
                                'position': 'relative'
                            })
                        ], className="bg-dark p-0", style={
                            'height': '595px',  # Fixed container height
                            'padding': '0 !important'
                        })
                    ], className="bg-dark border-secondary h-100", style={
                        'height': '100%'
                    })
                ], width=7, className="pe-2"),
                
                # Charts Column - adjusted width
                dbc.Col([
                    html.Div([
                        self.create_chart_container("Repeat Trips", "frequency"),
                        self.create_chart_container("Travel Mode", "mode")
                    ], style={'maxWidth': '578px', 'margin': '0 auto'})  # Increased from 550px
                ], width=5, className="ps-2")  # Increased from width=4
                
            ], className="g-2 mb-4", style={'marginTop': '0.4rem'})  # Reduced from 2rem
            
        ], fluid=True, className="p-3", style={'backgroundColor': '#000000', 'minHeight': '100vh'})

    def setup_callbacks(self):
        @self.app.callback(
            [dash.Output('map', 'figure'),
             dash.Output('mode-donut', 'src'),
             dash.Output('mode-legend', 'src'),
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
                
                # Load chart pairs
                mode_donut, mode_legend = self.chart_creator.load_chart_pair(
                    selected_poi.replace(' ', '_'), 'avg_trip_mode')
                frequency_donut, frequency_legend = self.chart_creator.load_chart_pair(
                    selected_poi.replace(' ', '_'), 'avg_trip_frequency')
                
                return (map_fig,
                       mode_donut, mode_legend,
                       frequency_donut, frequency_legend)
            except Exception as e:
                logger.error(f"Error updating dashboard: {str(e)}")
                logger.error(traceback.format_exc())
                return go.Figure(), '', '', '', ''

        @self.app.callback(
            dash.Output('selected-poi', 'children'),
            [dash.Input('map', 'clickData')]
        )
        def update_map_title(click_data):
            if not click_data or 'points' not in click_data:
                return ""
            clicked_poi = click_data['points'][0].get('customdata')
            if not clicked_poi:
                return ""
            # Remove dashes and format the POI name
            formatted_poi = clicked_poi.replace('-', ' ')
            return f"Selection: {formatted_poi}"

    def run_server(self, debug=True):
        self.app.run_server(debug=debug)

if __name__ == '__main__':
    dashboard = DashboardApp()
    dashboard.app.run_server(host='0.0.0.0', debug=True)