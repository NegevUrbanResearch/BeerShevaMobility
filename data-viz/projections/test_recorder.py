import os
import sys
import logging
import time
import subprocess
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import psutil
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import io
from animation_config import ANIMATION_CONFIG, OUTPUT_DIR
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_memory():
    """Check system memory usage"""
    try:
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024 * 1024 * 1024)
        total_gb = memory.total / (1024 * 1024 * 1024)
        usage_percent = memory.percent
        
        logger.info(f"Memory status: {usage_percent:.1f}% used, {available_gb:.1f}GB available out of {total_gb:.1f}GB")
        return available_gb >= 4.0 and usage_percent <= 85
    except Exception as e:
        logger.error(f"Error checking memory: {e}")
        return True

def get_animation_settings():
    """Get animation settings from config"""
    
    
    settings = {
        'fps': ANIMATION_CONFIG['fps'],                    # 30 fps
        'seconds_per_hour': ANIMATION_CONFIG['seconds_per_hour'],  # 30 seconds
        'total_seconds': ANIMATION_CONFIG['total_seconds'],        # 720 seconds
        'total_frames': int(ANIMATION_CONFIG['animation_duration']),  # 21,600 frames
    }
    
    logger.info("\nAnimation settings:")
    logger.info(f"FPS: {settings['fps']}")
    logger.info(f"Seconds per hour: {settings['seconds_per_hour']}")
    logger.info(f"Total duration: {settings['total_seconds']} seconds")
    logger.info(f"Total frames: {settings['total_frames']}")
    
    return settings

def validate_recording(output_path, expected_duration):
    """Validate the recorded video matches expected duration"""
    try:
        result = subprocess.run([
            'ffprobe', 
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            output_path
        ], capture_output=True, text=True)
        
        actual_duration = float(result.stdout.strip())
        if abs(actual_duration - expected_duration) > 1.0:  # 1 second tolerance
            logger.error(f"Recording duration mismatch: expected {expected_duration}s, got {actual_duration}s")
            return False
        return True
    except Exception as e:
        logger.error(f"Error validating recording: {e}")
        return False

def record_animation(html_path, output_path, duration_seconds=None):
    """Record animation using headless Firefox and optimized frame capture"""
    settings = get_animation_settings()
    
    if not check_memory():
        logger.error("Insufficient memory to start recording")
        return False
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if os.path.exists(output_path) and validate_recording(output_path, settings['total_seconds']):
        logger.info(f"Valid recording already exists: {output_path}")
        return True
    
    logger.info(f"Starting recording for {html_path}")
    
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=1920')
    firefox_options.add_argument('--height=1080')
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    
    driver = None
    temp_dir = None
    frames_queue = queue.Queue(maxsize=300)  # Buffer for frames
    recording_complete = threading.Event()
    
    try:
        temp_dir = os.path.join(os.path.dirname(output_path), f"temp_frames_{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)
        
        driver = webdriver.Firefox(options=firefox_options)
        driver.get(f'file://{html_path}')
        
        WebDriverWait(driver, 60).until(
            lambda d: d.execute_script("return window.animationStarted === true")
        )
        
        logger.info("Animation initialized, starting capture...")
        
        def capture_frames():
            start_time = time.time()
            frame_time = start_time
            frames_captured = 0
            
            while frames_captured < settings['total_frames']:
                current_time = time.time()
                frame_time += 1.0 / settings['fps']
                
                # Take screenshot and queue it
                screenshot = driver.get_screenshot_as_png()
                frames_queue.put((frames_captured, screenshot))
                frames_captured += 1
                
                if frames_captured % 30 == 0:
                    progress = (frames_captured * 100) / settings['total_frames']
                    logger.info(f"Capture progress: {progress:.1f}%")
                    driver.execute_script(f"document.querySelector('.progress').style.width = '{progress}%'")
                
                # Calculate sleep time to maintain exact FPS
                sleep_time = frame_time - current_time
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            recording_complete.set()
        
        def save_frames():
            while not (recording_complete.is_set() and frames_queue.empty()):
                try:
                    frame_num, screenshot = frames_queue.get(timeout=1)
                    image = Image.open(io.BytesIO(screenshot))
                    frame_path = os.path.join(temp_dir, f'frame_{frame_num:05d}.png')
                    image.save(frame_path, 'PNG')
                    frames_queue.task_done()
                except queue.Empty:
                    continue
        
        # Start capture and save threads
        capture_thread = threading.Thread(target=capture_frames)
        save_thread = threading.Thread(target=save_frames)
        
        capture_thread.start()
        save_thread.start()
        
        # Wait for completion
        capture_thread.join()
        save_thread.join()
        
        logger.info("Frame capture complete, creating video...")
        
        # Use FFmpeg to create video with exact timing
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-framerate', str(settings['fps']),
            '-i', os.path.join(temp_dir, 'frame_%05d.png'),
            '-c:v', 'h264_videotoolbox',
            '-b:v', '8M',
            '-maxrate', '10M',
            '-bufsize', '20M',
            '-pix_fmt', 'yuv420p',
            '-frames:v', str(settings['total_frames']),
            output_path
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
        
        if not validate_recording(output_path, settings['total_seconds']):
            logger.error("Recording validation failed!")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error during recording: {str(e)}")
        if os.path.exists(output_path):
            os.remove(output_path)
        raise
        
    finally:
        if driver:
            driver.quit()
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)

def verify_all_files_exist(output_dir, modes, directions, models):
    """Verify all expected HTML files exist"""
    missing_files = []
    for mode in modes:
        for direction in directions:
            for model_size in models:
                html_path = os.path.join(
                    output_dir,
                    f"projection_animation_{model_size}_{mode}_{direction}.html"
                )
                if not os.path.exists(html_path):
                    missing_files.append(html_path)
    
    if missing_files:
        logger.error("Missing HTML files:")
        for file in missing_files:
            logger.error(f"  - {file}")
        raise FileNotFoundError("Some HTML files are missing")

def verify_completed_recordings(output_dir, modes, directions, models):
    """Check which recordings are completed"""
    completed = set()
    for mode in modes:
        for direction in directions:
            for model_size in models:
                mp4_path = os.path.join(
                    output_dir,
                    f"projection_animation_{model_size}_{mode}_{direction}.mp4"
                )
                if os.path.exists(mp4_path) and validate_recording(
                    mp4_path, 
                    get_animation_settings()['total_seconds']
                ):
                    completed.add((mode, direction, model_size))
    return completed

def process_animation(mode, direction, model_size, base_dir):
    """Process a single animation"""
    html_path = os.path.join(
        base_dir,
        f"projection_animation_{model_size}_{mode}_{direction}.html"
    )
    output_path = os.path.join(
        base_dir,
        f"projection_animation_{model_size}_{mode}_{direction}.mp4"
    )
    
    logger.info(f"\nProcessing {model_size} model {mode} {direction} animation")
    return record_animation(
        os.path.abspath(html_path),
        output_path
    )

def main():

    
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        logger.error("FFmpeg/FFprobe not installed. Please install: brew install ffmpeg")
        sys.exit(1)
    
    modes = ['car', 'walk']
    directions = ['inbound', 'outbound']
    models = ['big', 'small']
    
    verify_all_files_exist(OUTPUT_DIR, modes, directions, models)
    
    completed = verify_completed_recordings(OUTPUT_DIR, modes, directions, models)
    if completed:
        logger.info("\nAlready completed recordings:")
        for mode, direction, model_size in completed:
            logger.info(f"  - {model_size} model {mode} {direction}")
    
    combinations = [
        (mode, direction, model_size, OUTPUT_DIR)
        for mode in modes
        for direction in directions
        for model_size in models
        if (mode, direction, model_size) not in completed
    ]
    
    if not combinations:
        logger.info("All recordings completed!")
        return
    
    logger.info(f"\nRemaining recordings to process: {len(combinations)}")
    
    # Calculate optimal number of parallel processes
    memory = psutil.virtual_memory()
    gb_per_process = 3.0  # Estimated GB needed per recording process
    
    # Get number of physical CPU cores (not counting hyperthreading)
    physical_cores = len(set([i & ~1 for i in range(mp.cpu_count())]))
    
    # Calculate max workers based on resources
    max_by_cpu = max(1, physical_cores - 1)  # Leave one core free
    max_by_memory = max(1, int(memory.available / (gb_per_process * 1024 * 1024 * 1024)))
    max_workers = min(3, max_by_cpu, max_by_memory)  # Cap at 3 parallel processes
    
    logger.info(f"System resources:")
    logger.info(f"Physical CPU cores: {physical_cores}")
    logger.info(f"Available memory: {memory.available / (1024*1024*1024):.1f} GB")
    logger.info(f"Using {max_workers} parallel workers")
    
    # Process animations in parallel
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i in range(0, len(combinations), max_workers):
            batch = combinations[i:i + max_workers]
            current_futures = [executor.submit(process_animation, *combo) for combo in batch]
            
            # Wait for current batch to complete
            for future in current_futures:
                try:
                    success = future.result()
                    if not success:
                        logger.error("Animation processing failed")
                except Exception as e:
                    logger.error(f"Error in animation process: {e}")
            
            # Short pause between batches to let system resources stabilize
            time.sleep(2)

if __name__ == "__main__":
    main()