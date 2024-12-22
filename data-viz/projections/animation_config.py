"""Shared configuration for animation timing"""
import logging

logger = logging.getLogger(__name__)

def calculate_animation_duration():
    """Calculate animation duration and related timing parameters"""
    fps = 30
    seconds_per_hour = 30  # Each hour takes 30 seconds
    hours_per_day = 24
    frames_per_hour = fps * seconds_per_hour
    animation_duration = frames_per_hour * hours_per_day
    total_seconds = animation_duration / fps
    
    # Log configuration
    logger.info(f"\nAnimation timing configuration:")
    logger.info(f"FPS: {fps}")
    logger.info(f"Seconds per hour: {seconds_per_hour}")
    logger.info(f"Frames per hour: {frames_per_hour}")
    logger.info(f"Total frames: {animation_duration}")
    logger.info(f"Total animation duration: {total_seconds:.1f} seconds")
    
    return {
        'fps': fps,
        'seconds_per_hour': seconds_per_hour,
        'hours_per_day': hours_per_day,
        'frames_per_hour': frames_per_hour,
        'animation_duration': animation_duration,
        'total_seconds': total_seconds,
        'trip_duration_multiplier': {
            'car': 2.0,    # Cars move faster
            'walk': 3.0    # Pedestrians move slower
        },
        'path_length_multiplier': {
            'car': 30,     # Car path stretching
            'walk': 45     # Walking path stretching
        }
    }

# Calculate once at module import
ANIMATION_CONFIG = calculate_animation_duration() 