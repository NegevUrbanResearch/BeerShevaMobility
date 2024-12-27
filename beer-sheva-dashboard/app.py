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
            '<style>body { font-size: 1.5rem; } .Select-value-label { color: black !important; font-size: 1.5rem; }</style></head>'
        )
        self.cache = Cache(self.app.server, config={'CACHE_TYPE': 'SimpleCache'})
        
        # Updated DataLoader initialization - no arguments needed
        self.data_loader = DataLoader()
        self.chart_creator = ChartCreator(COLOR_SCHEME, CHART_COLORS)
        self.map_creator = MapCreator(COLOR_SCHEME)
        
        self.zones = self.data_loader.load_zones()
        self.poi_df = self.data_loader.load_poi_data()
        self.trip_data = self.data_loader.load_trip_data()
        
        # Clean POI names and update trip_data keys
        self.poi_df, self.trip_data = self.data_loader.clean_poi_names(self.poi_df, self.trip_data)
        
        # Update dropdown options with cleaned names
        self.poi_options = [{'label': row['name'], 'value': row['name']} 
                           for _, row in self.poi_df.iterrows()]
        self.poi_coordinates = dict(zip(self.poi_df['name'], 
                                      zip(self.poi_df['lat'], self.poi_df['lon'])))
        
        self.setup_layout()
        self.setup_callbacks()

    def setup_layout(self):
        self.app.layout = dbc.Container([
            # Debug info row - Updated selector
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
            
            # Header Row
            dbc.Row([
                dbc.Col(html.H1("Beer Sheva Mobility Dashboard", 
                            className="text-center mb-2", 
                            style={'fontSize': '2rem', 'color': '#fff'}), 
                    width=12)
            ], justify="center", className="mb-2"),
            
            # Controls Row
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dcc.Dropdown(
                                id='poi-selector',
                                options=self.poi_options,
                                value=self.poi_options[0]['value'],
                                className="mb-1"
                            ),
                            dbc.RadioItems(
                                id='trip-type-selector',
                                options=[
                                    {'label': 'Inbound', 'value': 'inbound'},
                                    {'label': 'Outbound', 'value': 'outbound'}
                                ],
                                value='inbound',
                                inline=True,
                                className="d-flex justify-content-center"
                            )
                        ])
                    ], className="bg-dark border-secondary")
                ], width={"size": 6, "offset": 3}, className="mb-2")
            ]),
            
            # Main Content Row
            dbc.Row([
                # Map Column (65% width)
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Interactive Map", 
                                    className="bg-dark text-white py-1 border-secondary"),
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
                        ], className="bg-dark p-0")
                    ], className="bg-dark h-100 border-secondary")
                ], width=7, className="pe-2"),
                
                # Charts Column (35% width)
                dbc.Col([
                    *[dbc.Card([
                        dbc.CardHeader(title, 
                                    className="bg-dark text-white py-1 border-secondary"),
                        dbc.CardBody([
                            html.Div([
                                html.Img(
                                    id=f'{id_prefix}-chart',
                                    className="w-100 h-100",
                                    style={
                                        'objectFit': 'contain',
                                        'maxHeight': '180px'
                                    }
                                )
                            ], className="d-flex align-items-center justify-content-center bg-dark")
                        ], className="bg-dark p-2")
                    ], className="bg-dark border-secondary mb-3")
                    for title, id_prefix in [
                        ("Trip Frequency", "frequency"),
                        ("Travel Mode", "mode"),
                        ("Trip Purpose", "purpose")
                    ]]
                ], width=5, className="ps-2")
            ], className="g-2")
        ], fluid=True, 
        className="p-2",
        style={'backgroundColor': '#1a1a1a'})

        # Add window size debug callback with defensive checks
        self.app.clientside_callback(
            """
            function updateDebugInfo(figure) {
                const width = window.innerWidth;
                const height = window.innerHeight;
                
                // Only try to measure elements that exist
                let containerWidth = 'N/A';
                let mapHeight = 'N/A';
                
                const container = document.querySelector('.container-fluid');
                if (container) {
                    containerWidth = container.offsetWidth;
                }
                
                const mapElem = document.getElementById('map');
                if (mapElem) {
                    mapHeight = mapElem.offsetHeight;
                }
                
                return `Window: ${width}x${height}px | Container: ${containerWidth}px | Map: ${mapHeight}px`;
            }
            """,
            Output('debug-info', 'children'),
            Input('map', 'figure')
        )

        # Updated CSS with proper dark theme classes
        self.app.index_string = self.app.index_string.replace(
            '</head>',
            '''
            <style>
            body { 
                background-color: #1a1a1a !important;
                color: #ffffff;
                margin: 0;
                padding: 0;
            }
            
            .bg-dark {
                background-color: #2d2d2d !important;
            }
            
            .border-secondary {
                border: 1px solid #404040 !important;
            }
            
            /* Dropdown styling */
            .Select-control { 
                background-color: #383838 !important; 
                border-color: #404040 !important;
                color: white !important;
            }
            
            .Select-menu-outer { 
                background-color: #383838 !important; 
                border-color: #404040 !important;
                color: white !important;
                z-index: 1000;
            }
            
            .Select-value-label { 
                color: white !important; 
            }
            
            .Select-option { 
                background-color: #383838 !important; 
                color: white !important;
                padding: 8px;
            }
            
            .Select-option:hover { 
                background-color: #454545 !important; 
            }
            
            /* Radio button styling */
            .form-check-label { 
                color: #ffffff !important;
                margin-left: 8px;
            }
            
            .form-check-input { 
                background-color: #383838 !important;
                border-color: #404040 !important;
            }
            
            .form-check-input:checked { 
                background-color: #0d6efd !important;
                border-color: #0d6efd !important;
            }
            
            /* Card styling */
            .card {
                background-color: #2d2d2d !important;
                border: 1px solid #404040 !important;
            }
            
            .card-header {
                background-color: #383838 !important;
                border-bottom: 1px solid #404040 !important;
                padding: 8px 16px;
            }
            
            .card-body {
                background-color: #2d2d2d !important;
                padding: 8px;
            }
            
            /* Plot styling */
            .js-plotly-plot {
                background-color: #2d2d2d !important;
            }
            
            .modebar {
                background-color: rgba(45, 45, 45, 0.8) !important;
            }
            
            .modebar-btn {
                color: #fff !important;
            }
            </style>
            </head>
            ''')

    def setup_callbacks(self):
        @self.app.callback(
            [dash.Output('map', 'figure'),
             dash.Output('mode-chart', 'src'),
             dash.Output('purpose-chart', 'src'),
             dash.Output('frequency-chart', 'src'),
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
                
                logger.info("Dashboard update completed successfully")
                return map_fig, mode_chart_src, purpose_chart_src, frequency_chart_src, selected_poi
            except Exception as e:
                logger.error(f"Error updating dashboard: {str(e)}")
                logger.error(traceback.format_exc())
                # Return empty figures/charts in case of error
                return go.Figure(), '', '', '', selected_poi

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
