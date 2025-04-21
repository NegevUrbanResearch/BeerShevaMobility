"""Shared configuration for animation timing and route settings"""
import logging

logger = logging.getLogger(__name__)

OUTPUT_DIR = '/Users/noamgal/DSProjects/BeerShevaMobility/data-viz/output/dashboard_data'

def calculate_animation_duration():
    """
    Calculate animation duration and related timing parameters.
    Returns a complete configuration dictionary for all animation settings.
    """
    # Base timing configuration
    fps = 30
    seconds_per_half_hour = 30  # Each half hour takes 30 seconds
    hours_per_day = 24
    half_hours_per_day = hours_per_day * 2  # 48 half-hour intervals
    frames_per_half_hour = fps * seconds_per_half_hour
    animation_duration = frames_per_half_hour * half_hours_per_day
    total_seconds = animation_duration / fps

    # Mode-specific settings
    mode_settings = {
        'car': {
            'speed_multiplier': 1.5,      # Increased from 1.0 for faster car movement
            'path_multiplier': 10,        
            'trail_length': 6,            
            'min_width': 4,               # Increased from 2 for wider car paths
            'max_width': 5,               # Increased from 4 for wider car paths
            'opacity': 0.9,               # Increased from 0.8 for more prominent cars
            'animation_offset': 0,         
            'max_simultaneous_trips': 10,    
            'trip_spacing': 0.1,            
            'random_delay': 0.2,            
            'segment_speed_adjustment': {    
                'min_segment_length': 0.01,  
                'max_segment_length': 0.1,   
                'min_speed_factor': 0.4,     # Less slowdown for cars
                'max_speed_factor': 1.5,     # More speedup for cars
                'smoothing_window': 30,      # Increased from 3 for smoother transitions
                'min_speed_threshold': 0.3   # Minimum speed at intersections
            }
        },
        'walk': {
            'speed_multiplier': 0.3,      # Reduced from 0.5 for slower walking
            'path_multiplier': 10,        
            'trail_length': 4,            
            'min_width': 2,               # Reduced from 2 for narrower walking paths
            'max_width': 2.5,             # Reduced from 4 for narrower walking paths
            'opacity': 0.7,               # Reduced from 0.8 for less prominent walking
            'animation_offset': 0,          
            'max_simultaneous_trips': 10,    
            'trip_spacing': 0.15,           
            'random_delay': 0.3,            
            'segment_speed_adjustment': {    
                'min_segment_length': 0.01,  
                'max_segment_length': 0.1,   
                'min_speed_factor': 0.2,     # More slowdown for walking
                'max_speed_factor': 1.0,     # Less speedup for walking
                'smoothing_window': 30,      # Increased from 3 for smoother transitions
                'min_speed_threshold': 0.3   # Minimum speed at intersections
            }
        }
    }

    # Direction-specific settings with more granular time distribution
    direction_settings = {
        'inbound': {
            'start_hour': 6,               # Morning rush hour start
            'peak_hours': [8, 9],          # Morning peak
            'flow_multiplier': 1.0,        # Base flow rate
            'time_distribution': {         # More granular time distribution
                '6:00-7:00': 0.3,         # Early morning
                '7:00-8:00': 0.8,         # Morning rush
                '8:00-9:00': 1.0,         # Peak hour
                '9:00-10:00': 0.6,        # Post-peak
                '10:00-18:00': 0.2,       # Daytime
                '18:00-24:00': 0.1        # Evening
            }
        },
        'outbound': {
            'start_hour': 16,              # Afternoon rush hour start
            'peak_hours': [17, 18],        # Evening peak
            'flow_multiplier': 1.0,        # Base flow rate
            'time_distribution': {         # More granular time distribution
                '6:00-15:00': 0.2,        # Daytime
                '15:00-16:00': 0.4,       # Pre-rush
                '16:00-17:00': 0.8,       # Evening rush
                '17:00-18:00': 1.0,       # Peak hour
                '18:00-19:00': 0.6,       # Post-peak
                '19:00-24:00': 0.3        # Evening
            }
        }
    }

    # POI Colors (consistent across all visualizations)
    poi_colors = {
        'BGU': [0, 255, 90],              # Bright green
        'Gav Yam': [0, 191, 255],         # Bright blue
        'Soroka Hospital': [170, 0, 255]   # Purple
    }

    # Log configuration details
    logger.info("\nAnimation timing configuration:")
    logger.info(f"FPS: {fps}")
    logger.info(f"Seconds per half hour: {seconds_per_half_hour}")
    logger.info(f"Frames per half hour: {frames_per_half_hour}")
    logger.info(f"Total frames: {animation_duration}")
    logger.info(f"Total animation duration: {total_seconds:.1f} seconds")

    # Combined configuration dictionary
    return {
        # Timing parameters
        'fps': fps,
        'seconds_per_half_hour': seconds_per_half_hour,
        'hours_per_day': hours_per_day,
        'half_hours_per_day': half_hours_per_day,
        'frames_per_half_hour': frames_per_half_hour,
        'animation_duration': animation_duration,
        'total_seconds': total_seconds,
        
        # Mode and direction settings
        'modes': mode_settings,
        'directions': direction_settings,
        'poi_colors': poi_colors,
        
        # Animation settings
        'frame_cache_size': 30,            # Number of frames to cache
        'transition_frames': 15,           # Frames for smooth transitions
        'cache_update_interval': 1000,     # Milliseconds between cache updates
        
        # Trip distribution settings
        'trip_distribution': {
            'random_seed': 42,             # For reproducible randomness
            'min_spacing': 0.1,            # Minimum time between trips
            'max_random_delay': 0.3,       # Maximum random delay
            'distribution_window': 5,      # Window size for trip distribution
        },
        
        # WebGL settings
        'blend_mode': {
            'src_rgb': 'src alpha',
            'dst_rgb': 'one minus src alpha',
            'src_alpha': 'src alpha',
            'dst_alpha': 'one minus src alpha'
        },
        
        # Debug settings
        'show_stats': True,               # Show performance stats
        'debug_mode': True,               # Additional debug information
        'log_level': logging.INFO,        # Logging level
        
        # Logging settings
        'logging': {
            'interval_minutes': 5,         # Log every 5 minutes (changed from 30)
            'log_trip_counts': True,       # Log number of active trips
            'log_speeds': True,            # Log speed statistics
            'log_poi_distribution': True,  # Log trip distribution by POI
            'log_performance': True        # Log performance metrics
        }
    }

# Calculate configuration once at module import
ANIMATION_CONFIG = calculate_animation_duration()

def get_mode_settings(mode):
    """Helper function to get settings for a specific mode"""
    if mode not in ANIMATION_CONFIG['modes']:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {list(ANIMATION_CONFIG['modes'].keys())}")
    return ANIMATION_CONFIG['modes'][mode]

def get_direction_settings(direction):
    """Helper function to get settings for a specific direction"""
    if direction not in ANIMATION_CONFIG['directions']:
        raise ValueError(f"Invalid direction: {direction}. Must be one of {list(ANIMATION_CONFIG['directions'].keys())}")
    return ANIMATION_CONFIG['directions'][direction]

def get_poi_color(poi_name):
    """Helper function to get color for a specific POI"""
    return ANIMATION_CONFIG['poi_colors'].get(poi_name, [255, 255, 255])  # Default to white if POI not found