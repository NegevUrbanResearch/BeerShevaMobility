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
    seconds_per_hour = 30  # Each hour takes 30 seconds
    hours_per_day = 24
    frames_per_hour = fps * seconds_per_hour
    animation_duration = frames_per_hour * hours_per_day
    total_seconds = animation_duration / fps

    # Mode-specific settings
    mode_settings = {
        'car': {
            'speed_multiplier': 2.0,        # Cars move faster
            'path_multiplier': 30,          # Car path stretching
            'trail_length': 5,              # Longer trail for cars
            'min_width': 2,                 # Minimum line width
            'max_width': 4,                 # Maximum line width
            'opacity': 0.8,                 # Slightly more opaque
            'animation_offset': 0,          # No offset for cars
        },
        'walk': {
            'speed_multiplier': 1.0,        # Base walking speed
            'path_multiplier': 45,          # Walking path stretching
            'trail_length': 3,              # Shorter trail for walking
            'min_width': 1,                 # Thinner lines for walking
            'max_width': 2,                 # Maximum width for walking
            'opacity': 0.7,                 # Slightly more transparent
            'animation_offset': 0,          # No offset for walking
        }
    }

    # Direction-specific settings
    direction_settings = {
        'inbound': {
            'start_hour': 6,               # Morning rush hour start
            'peak_hours': [8, 9],          # Morning peak
            'flow_multiplier': 1.0,        # Base flow rate
        },
        'outbound': {
            'start_hour': 16,              # Afternoon rush hour start
            'peak_hours': [17, 18],        # Evening peak
            'flow_multiplier': 1.0,        # Base flow rate
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
    logger.info(f"Seconds per hour: {seconds_per_hour}")
    logger.info(f"Frames per hour: {frames_per_hour}")
    logger.info(f"Total frames: {animation_duration}")
    logger.info(f"Total animation duration: {total_seconds:.1f} seconds")

    # Combined configuration dictionary
    return {
        # Timing parameters
        'fps': fps,
        'seconds_per_hour': seconds_per_hour,
        'hours_per_day': hours_per_day,
        'frames_per_hour': frames_per_hour,
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
        
        # WebGL settings
        'blend_mode': {
            'src_rgb': 'src alpha',
            'dst_rgb': 'one minus src alpha',
            'src_alpha': 'src alpha',
            'dst_alpha': 'one minus src alpha'
        },
        
        # Debug settings
        'show_stats': True,               # Show performance stats
        'debug_mode': False,              # Additional debug information
        'log_level': logging.INFO         # Logging level
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