"""
Optimized recorder script for capturing animation segments in 8K resolution
with consistent speed and proper viewport
"""
import os
import sys
import logging
import time
import io
import cv2
import numpy as np
import gc

# Add parent directory to Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from PIL import Image
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor
import subprocess
import platform
import shutil
import psutil
from config import OUTPUT_DIR
from projections.anim_transparent import ANIMATION_CONFIG

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def monitor_memory():
    """Monitor and log memory usage"""
    process = psutil.Process(os.getpid())
    mem_gb = process.memory_info().rss / 1024 / 1024 / 1024
    logger.info(f"Current memory usage: {mem_gb:.2f} GB")
    return mem_gb

def record_hour_segment(html_path, output_dir, hour, fps=30, browser_type='firefox'):
    """
    Record a full hour segment in 8K resolution with consistent speed
    
    Parameters:
    - html_path: Path to the HTML file
    - output_dir: Directory to save output frames
    - hour: Hour of day to record (0-23)
    - fps: Frames per second to capture
    - browser_type: 'firefox' or 'chrome'
    """
    # Calculate frame range for hour
    frames_per_hour = ANIMATION_CONFIG['frames_per_hour']
    start_frame = hour * frames_per_hour
    end_frame = (hour + 1) * frames_per_hour
    frames_to_capture = end_frame - start_frame
    
    # 8K Resolution settings
    width = 7680   # 8K width
    height = 4320  # 8K height
    
    # Log memory before starting
    monitor_memory()
    
    # Browser setup for 8K
    if browser_type == 'firefox':
        options = FirefoxOptions()
        options.add_argument('--headless')
        options.add_argument(f'--width={width}')
        options.add_argument(f'--height={height}')
        
        # Performance settings for 8K rendering
        options.set_preference('webgl.force-enabled', True)
        options.set_preference('webgl.disabled', False)
        options.set_preference('layers.acceleration.force-enabled', True)
        options.set_preference('gfx.canvas.azure.accelerated', True)
        options.set_preference('media.hardware-video-decoding.force-enabled', True)
        
        # Memory settings for large resolution
        options.set_preference('javascript.options.mem.max', 4096)  # 4GB JS heap
        
        driver = webdriver.Firefox(options=options)
    else:  # chrome
        options = ChromeOptions()
        options.add_argument('--headless')
        options.add_argument(f'--window-size={width},{height}')
        options.add_argument('--disable-gpu')  # For headless
        options.add_argument('--enable-webgl')
        options.add_argument('--js-flags=--max-old-space-size=4096')  # 4GB JS heap
        
        driver = webdriver.Chrome(options=options)
    
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Load page
        logger.info(f"Loading: {html_path}")
        driver.get(f'file://{html_path}')
        
        # Wait for animation to initialize
        logger.info("Waiting for animation to initialize...")
        wait = WebDriverWait(driver, 120)  # Increased timeout for 8K
        
        # Check initialization
        max_attempts = 60  # More attempts for 8K resolution
        for attempt in range(max_attempts):
            initialized = driver.execute_script("""
                return (window.animationStarted === true && 
                        window.deckglLoaded === true &&
                        typeof window.setAnimationFrame === 'function')
            """)
            
            if initialized:
                logger.info("Animation initialized")
                break
                
            if attempt == max_attempts - 1:
                raise TimeoutError("Animation failed to initialize")
                
            time.sleep(2)  # Longer wait between checks for 8K
        
        # Configure viewport for 8K (ensure full visibility)
        driver.execute_script("""
            // Ensure proper viewport handling for 8K
            document.body.style.margin = '0';
            document.body.style.padding = '0';
            document.body.style.overflow = 'hidden';
            
            // Force WebGL to use hardware acceleration if available
            const canvas = document.querySelector('canvas');
            if (canvas) {
                const gl = canvas.getContext('webgl2', {
                    antialias: true,
                    preserveDrawingBuffer: true,
                    powerPreference: 'high-performance'
                });
            }
            
            // Center view without zooming
            try {
                const container = document.getElementById('container');
                if (container) {
                    container.style.width = '100vw';
                    container.style.height = '100vh';
                    container.style.overflow = 'hidden';
                }
            } catch(e) {
                console.error('Error adjusting container:', e);
            }
        """)
        
        # Set speed multiplier for consistent playback
        driver.execute_script("window.setAnimationSpeed(1.0);")
        
        # Log activity
        logger.info(f"Starting 8K recording hour {hour}:00-{hour+1}:00 (frames {start_frame}-{end_frame})...")
        monitor_memory()
        
        # Warm up the renderer with several frames
        logger.info("Warming up renderer...")
        for i in range(10):
            warmup_frame = start_frame + (i % 10)
            driver.execute_script(f"window.setAnimationFrame({warmup_frame});")
            time.sleep(0.5)  # Longer warm-up time for 8K
        
        # Determine optimal batch size based on available memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        batch_size = max(10, min(100, int(available_memory_gb * 10)))
        logger.info(f"Using batch size of {batch_size} frames based on {available_memory_gb:.2f}GB available memory")
        
        # Process frames in batches to manage memory
        start_time = time.time()
        for batch_start in range(0, frames_to_capture, batch_size):
            batch_end = min(batch_start + batch_size, frames_to_capture)
            logger.info(f"Processing batch {batch_start//batch_size + 1}, frames {batch_start}-{batch_end-1}")
            
            # Process frames in parallel within the batch
            with ThreadPoolExecutor(max_workers=mp.cpu_count()) as executor:
                futures = []
                
                for i in range(batch_start, batch_end):
                    # Set exact frame to render
                    frame = start_frame + i
                    driver.execute_script(f"window.setAnimationFrame({frame});")
                    
                    # Wait for rendering to complete (longer for 8K)
                    max_wait = 1.0  # seconds
                    render_wait_start = time.time()
                    render_complete = False
                    
                    while time.time() - render_wait_start < max_wait and not render_complete:
                        try:
                            render_complete = driver.execute_script("return window.isFrameRendered();")
                            if render_complete:
                                break
                        except Exception as e:
                            logger.warning(f"Error checking render state: {e}")
                        time.sleep(0.05)
                    
                    # Take screenshot
                    screenshot = driver.get_screenshot_as_png()
                    
                    # Process in parallel
                    output_path = os.path.join(output_dir, f'frame_{i:05d}.png')
                    futures.append(executor.submit(process_frame, screenshot, output_path))
                    
                    # Log progress
                    if (i - batch_start) % 10 == 0 or i == batch_end - 1:
                        frame_progress = 100 * (i + 1) / frames_to_capture
                        elapsed = time.time() - start_time
                        rate = (i + 1) / elapsed if elapsed > 0 else 0
                        remaining = (frames_to_capture - i - 1) / rate if rate > 0 else 0
                        logger.info(f"Progress: {frame_progress:.1f}% ({i+1}/{frames_to_capture}) | " 
                                 f"Speed: {rate:.1f} fps | ETA: {remaining:.1f}s")
                
                # Wait for all processing to complete
                for future in futures:
                    future.result()
            
            # Force garbage collection between batches
            gc.collect()
            monitor_memory()
        
        logger.info("Frame capture completed")
        return frames_to_capture, fps
        
    except Exception as e:
        logger.error(f"Error during recording: {str(e)}")
        raise
        
    finally:
        driver.quit()
        gc.collect()

def process_frame(screenshot_data, output_path):
    """Process a single frame with optimizations for 8K"""
    try:
        image = Image.open(io.BytesIO(screenshot_data))
        
        # Optimize PNG saving for 8K
        image.save(output_path, 'PNG', optimize=True, compression_level=6)
        
        # Explicitly delete to help memory management
        del image
        return output_path
    except Exception as e:
        logger.error(f"Error processing frame: {e}")
        raise

def create_8k_video(frames_dir, output_path, fps):
    """Create 8K video from frames with appropriate bitrate"""
    frame_files = sorted([f for f in os.listdir(frames_dir) if f.startswith('frame_')])
    if not frame_files:
        raise ValueError("No frames found in directory")
    
    # Count frames
    frame_count = len(frame_files)
    logger.info(f"Creating 8K video from {frame_count} frames at {fps} fps")
    
    # Get dimensions from first frame to confirm 8K
    first_frame = cv2.imread(os.path.join(frames_dir, frame_files[0]))
    height, width = first_frame.shape[:2]
    logger.info(f"Frame resolution: {width}x{height}")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Define output file
    output_file = output_path if output_path.endswith('.mp4') else output_path + '.mp4'
    
    # 8K requires higher bitrate for good quality
    bitrate = '120M'  # 120 Mbps for 8K
    
    # Try hardware acceleration first
    try:
        # Choose encoder based on platform
        if platform.system() == 'Darwin':  # macOS
            # For macOS, h265/HEVC is better for 8K
            encoder = 'hevc_videotoolbox'
            codec_opts = [
                '-tag:v', 'hvc1',  # For better compatibility
                '-allow_sw', '1'    # Allow software fallback
            ]
        elif platform.system() == 'Windows':
            # For Windows with NVIDIA GPU
            encoder = 'h264_nvenc'
            codec_opts = [
                '-rc:v', 'vbr',
                '-cq', '20'
            ]
        else:  # Linux
            # For Linux with Intel GPU
            encoder = 'h264_vaapi'
            codec_opts = [
                '-vaapi_device', '/dev/dri/renderD128'
            ]
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-framerate', str(fps),
            '-i', os.path.join(frames_dir, 'frame_%05d.png'),
            '-c:v', encoder,
            '-b:v', bitrate,
            '-maxrate', '140M',  # 140 Mbps max
            '-bufsize', '160M',  # 160 Mbps buffer
            '-pix_fmt', 'yuv420p'
        ]
        
        # Add codec specific options
        ffmpeg_cmd.extend(codec_opts)
        
        # Add output file path
        ffmpeg_cmd.append(output_file)
        
        logger.info(f"Creating 8K video with hardware acceleration ({encoder})")
        subprocess.run(ffmpeg_cmd, check=True)
        
    except subprocess.CalledProcessError:
        logger.info("Hardware acceleration failed, using software encoding")
        
        # Fall back to software encoding (higher quality but slower)
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-framerate', str(fps),
            '-i', os.path.join(frames_dir, 'frame_%05d.png'),
            '-c:v', 'libx264',
            '-preset', 'slow',  # Slower but better quality for 8K
            '-crf', '18',       # Higher quality (lower is better)
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_file
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
    
    # Check final video size
    video_size_mb = os.path.getsize(output_file) / (1024 * 1024)
    logger.info(f"8K Video created: {output_file} ({video_size_mb:.2f} MB)")
    return output_file

def record_rush_hour(html_path, output_path, direction):
    """
    Record a full rush hour segment in 8K
    
    Parameters:
    - html_path: Path to the HTML file
    - output_path: Path for the output video
    - direction: 'inbound' (morning) or 'outbound' (evening)
    """
    # Determine hour based on direction
    hour = 7 if direction == 'inbound' else 17  # 7am or 5pm
    time_desc = "7am-8am" if direction == 'inbound' else "5pm-6pm"
    
    # Create temp directory for frames
    temp_dir = os.path.join(os.path.dirname(output_path), f"temp_hour_{hour}")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        logger.info(f"Recording 8K rush hour: {time_desc}")
        
        # Record frames
        total_frames, fps = record_hour_segment(
            html_path=html_path,
            output_dir=temp_dir,
            hour=hour,
            fps=ANIMATION_CONFIG['fps']
        )
        
        # Create 8K video
        create_8k_video(temp_dir, output_path, fps)
        
        # Clean up temp files unless requested to keep them
        if not os.environ.get('KEEP_FRAMES', False):
            logger.info(f"Cleaning up temporary frames in {temp_dir}")
            shutil.rmtree(temp_dir)
        else:
            logger.info(f"Keeping temporary frames in {temp_dir}")
        
        logger.info(f"8K rush hour recording completed: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error recording rush hour: {str(e)}")
        raise

def main():
    """Record rush hour segments in 8K for all combinations"""
    modes = ['car', 'walk']
    directions = ['inbound', 'outbound']
    models = ['big', 'small']
    
    for mode in modes:
        for direction in directions:
            for model_size in models:
                # Define paths
                html_path = os.path.join(
                    OUTPUT_DIR, 
                    f"projection_animation_{model_size}_{mode}_{direction}.html"
                )
                
                # Time description based on direction
                time_desc = "7am-8am" if direction == 'inbound' else "5pm-6pm"
                
                # Output filename
                output_path = os.path.join(
                    OUTPUT_DIR, 
                    f"8K_rush_hour_{model_size}_{mode}_{direction}_{time_desc}.mp4"
                )
                
                logger.info(f"\nProcessing 8K recording: {model_size} {mode} {direction}")
                
                # Record rush hour in 8K
                record_rush_hour(
                    os.path.abspath(html_path),
                    output_path,
                    direction
                )

if __name__ == "__main__":
    main()