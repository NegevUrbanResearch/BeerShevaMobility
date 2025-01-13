import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
import time
import io
import cv2
import numpy as np
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from PIL import Image
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from animation_config import ANIMATION_CONFIG
import subprocess
import platform
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def save_frames_as_images(html_path, output_dir):
    """Save individual frames as PNG images with proper timing"""
    # Get duration from shared config
    duration_seconds = ANIMATION_CONFIG['total_seconds']
    source_fps = ANIMATION_CONFIG['fps']  # Original FPS from config (30)
    target_fps = 30  # Restore to original FPS
    
    # Calculate total frames needed
    frames_to_capture = int(duration_seconds * target_fps)
    
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=3840')
    firefox_options.add_argument('--height=2160')
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    # Add hardware acceleration options
    firefox_options.set_preference('layers.acceleration.force-enabled', True)
    firefox_options.set_preference('gfx.canvas.azure.accelerated', True)
    firefox_options.set_preference('media.hardware-video-decoding.force-enabled', True)
    
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info("Starting Firefox WebDriver...")
    driver = webdriver.Firefox(options=firefox_options)
    
    try:
        logger.info(f"Loading page: file://{html_path}")
        driver.get(f'file://{html_path}')
        
        # Wait for initialization with improved checks
        logger.info("Waiting for animation to initialize...")
        max_wait_time = 60
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                # Check for canvas
                deck_canvas = driver.find_element(By.CSS_SELECTOR, 'canvas')
                if not deck_canvas:
                    logger.info("Canvas element not found yet...")
                    time.sleep(1)
                    continue
                
                # Check WebGL context
                webgl_status = driver.execute_script("""
                    const canvas = document.querySelector('canvas');
                    if (!canvas) return 'No canvas found';
                    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                    if (!gl) return 'No WebGL context';
                    return 'WebGL available';
                """)
                logger.info(f"WebGL status: {webgl_status}")
                
                initialized = driver.execute_script("""
                    if (typeof deck === 'undefined') {
                        return 'deck.gl not loaded';
                    }
                    if (!window.deckglLoaded) {
                        return 'deck.gl not initialized';
                    }
                    if (!window.animationStarted) {
                        return 'animation not started';
                    }
                    return true;
                """)
                
                logger.info(f"Initialization check: {initialized}")
                
                if initialized is True:
                    break
                    
            except Exception as e:
                logger.warning(f"Initialization check error: {str(e)}")
                
            time.sleep(1)
        
        if time.time() - start_time >= max_wait_time:
            logger.error("Initialization timeout - Debug info:")
            logger.error(f"Page title: {driver.title}")
            logger.error(f"Page source preview: {driver.page_source[:500]}...")
            raise TimeoutError("Animation failed to initialize within timeout period")
        
        logger.info("Animation initialized successfully!")
        
        # Calculate frame timing
        frame_interval = 1.0 / target_fps
        source_frame_interval = 1.0 / source_fps
        
        # Get the initial animation time
        start_time = driver.execute_script("return performance.now()")
        
        # Create a thread pool for parallel image processing
        with ThreadPoolExecutor(max_workers=mp.cpu_count()) as executor:
            futures = []
            
            for i in range(frames_to_capture):
                current_frame = i + 1
                progress = (current_frame * 100) / frames_to_capture
                
                # Calculate timing
                source_frame = int((i * source_fps) / target_fps)
                expected_time = start_time + (source_frame * source_frame_interval * 1000)
                current_time = driver.execute_script("return performance.now()")
                
                if current_time < expected_time:
                    time.sleep((expected_time - current_time) / 1000)
                
                # Capture frame
                screenshot = driver.get_screenshot_as_png()
                
                # Process image in parallel
                frame_path = os.path.join(output_dir, f'frame_{i:05d}.png')
                futures.append(executor.submit(process_frame, screenshot, frame_path))
                
                # Print progress every 30 frames
                if current_frame % 30 == 0 or current_frame == frames_to_capture:
                    logger.info(f"Progress: {progress:.1f}% ({current_frame}/{frames_to_capture} frames)")
                
                # Update progress bar
                driver.execute_script(f"document.querySelector('.progress').style.width = '{progress}%'")
            
            # Wait for all image processing to complete
            for future in futures:
                future.result()
        
        logger.info("Frame capture completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during frame capture: {str(e)}")
        raise
    
    finally:
        driver.quit()

def process_frame(screenshot_data, output_path):
    """Process a single frame in parallel"""
    image = Image.open(io.BytesIO(screenshot_data))
    
    # Convert to RGBA if needed
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Optimize image saving
    image.save(output_path, 'PNG', optimize=True)

def create_video_from_frames(frame_dir, output_path):
    """Create video from frames using hardware acceleration"""
    target_fps = 30  # Restore to original FPS
    frame_files = sorted([f for f in os.listdir(frame_dir) if f.startswith('frame_')])
    if not frame_files:
        raise ValueError("No frames found in directory")
    
    logger.info(f"Found {len(frame_files)} frames to process")
    first_frame = cv2.imread(os.path.join(frame_dir, frame_files[0]), cv2.IMREAD_UNCHANGED)
    height, width = first_frame.shape[:2]
    
    # Calculate expected durations
    total_frames = len(frame_files)
    total_duration = total_frames / target_fps
    
    logger.info(f"Animation timing:")
    logger.info(f"Total frames: {total_frames}")
    logger.info(f"Target FPS: {target_fps}")
    logger.info(f"Total duration: {total_duration:.2f} seconds")
    
    # Try hardware-accelerated encoding first
    output_file = output_path.rsplit('.', 1)[0] + '.mp4'
    
    # Determine available hardware acceleration
    system = platform.system()
    if system == 'Darwin':  # macOS
        encoder = 'h264_videotoolbox'
    elif system == 'Windows':
        encoder = 'h264_nvenc'  # NVIDIA GPU
    else:  # Linux
        encoder = 'h264_vaapi'  # Intel GPU
    
    try:
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file
            '-framerate', str(target_fps),
            '-i', os.path.join(frame_dir, 'frame_%05d.png'),
            '-c:v', encoder,
            '-b:v', '20M',  # Higher bitrate for better quality
            '-maxrate', '25M',
            '-bufsize', '25M',
            '-preset', 'fast',  # Use faster encoding preset
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_file
        ]
        
        logger.info(f"Creating video with hardware acceleration ({encoder})...")
        subprocess.run(ffmpeg_cmd, check=True)
        logger.info(f"Video successfully created at: {output_file}")
        return output_file
        
    except subprocess.CalledProcessError:
        logger.warning(f"Hardware acceleration failed, falling back to software encoding...")
        
        # Fall back to software encoding
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-framerate', str(target_fps),
            '-i', os.path.join(frame_dir, 'frame_%05d.png'),
            '-c:v', 'libx264',
            '-preset', 'faster',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_file
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
        logger.info(f"Video successfully created at: {output_file}")
        return output_file

def record_animation_mac(html_path, output_path, duration_seconds):
    """Record animation using headless Firefox and ffmpeg"""
    logger.info("Starting Firefox for screen recording...")
    
    # Validate expected duration
    expected_duration = ANIMATION_CONFIG['total_seconds']
    if abs(duration_seconds - expected_duration) > 1:  # Allow 1 second tolerance
        raise ValueError(f"Duration mismatch: expected {expected_duration} seconds, got {duration_seconds} seconds")
    
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=1920')
    firefox_options.add_argument('--height=1080')
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    firefox_options.set_preference('layers.acceleration.force-enabled', True)
    firefox_options.set_preference('gfx.canvas.azure.accelerated', True)
    firefox_options.set_preference('media.hardware-video-decoding.force-enabled', True)
    
    driver = webdriver.Firefox(options=firefox_options)
    
    try:
        logger.info(f"Loading page: file://{html_path}")
        driver.get(f'file://{html_path}')
        
        # Wait for initialization
        WebDriverWait(driver, 60).until(
            lambda d: d.execute_script("return window.animationStarted === true")
        )
        
        logger.info("Animation initialized, starting recording...")
        
        # Create temporary directory for frames
        temp_dir = os.path.join(os.path.dirname(output_path), "temp_frames")
        os.makedirs(temp_dir, exist_ok=True)
        
        target_fps = ANIMATION_CONFIG['fps']  # Use FPS from config (30)
        frames_to_capture = int(duration_seconds * target_fps)
        frame_interval = 1.0 / target_fps
        
        # Validate total frames
        expected_frames = int(expected_duration * target_fps)
        if frames_to_capture != expected_frames:
            raise ValueError(f"Frame count mismatch: expected {expected_frames}, calculated {frames_to_capture}")
        
        logger.info(f"Recording configuration:")
        logger.info(f"Target FPS: {target_fps}")
        logger.info(f"Total frames to capture: {frames_to_capture}")
        logger.info(f"Expected duration: {duration_seconds} seconds")
        
        # Inject frame rate control into the page
        driver.execute_script("""
            window.lastFrameTime = performance.now();
            window.frameInterval = %f * 1000;  // Convert to milliseconds
            
            // Override requestAnimationFrame to control frame rate
            const originalRAF = window.requestAnimationFrame;
            window.requestAnimationFrame = function(callback) {
                const now = performance.now();
                const elapsed = now - window.lastFrameTime;
                
                if (elapsed >= window.frameInterval) {
                    window.lastFrameTime = now;
                    return originalRAF(callback);
                }
                
                // Wait until next frame interval
                return setTimeout(() => {
                    window.lastFrameTime = performance.now();
                    originalRAF(callback);
                }, window.frameInterval - elapsed);
            };
        """ % frame_interval)
        
        # Get initial animation time
        start_time = time.perf_counter()
        
        # Create a thread pool for parallel image processing
        with ThreadPoolExecutor(max_workers=mp.cpu_count()) as executor:
            futures = []
            
            # Capture frames
            for i in range(frames_to_capture):
                # Calculate when this frame should be captured
                target_time = start_time + (i * frame_interval)
                current_time = time.perf_counter()
                
                # Wait if we're ahead of schedule
                if current_time < target_time:
                    time.sleep(target_time - current_time)
                
                # Take screenshot
                screenshot = driver.get_screenshot_as_png()
                
                # Process frame in parallel
                frame_path = os.path.join(temp_dir, f'frame_{i:05d}.png')
                futures.append(executor.submit(process_frame, screenshot, frame_path))
                
                # Print progress
                if i % 30 == 0 or i == frames_to_capture - 1:
                    progress = ((i + 1) * 100) / frames_to_capture
                    logger.info(f"Recording progress: {progress:.1f}% ({i + 1}/{frames_to_capture} frames)")
                
                # Update progress bar in browser
                driver.execute_script(f"document.querySelector('.progress').style.width = '{progress}%'")
            
            # Wait for all image processing to complete
            for future in futures:
                future.result()
        
        # Calculate actual duration
        actual_duration = time.perf_counter() - start_time
        logger.info(f"Recording completed in {actual_duration:.2f} seconds")
        
        if abs(actual_duration - duration_seconds) > duration_seconds * 0.1:  # Allow 10% tolerance
            logger.warning(f"Recording duration deviation: expected {duration_seconds:.2f}s, got {actual_duration:.2f}s")
        
        # Use ffmpeg to create video with exact frame rate
        output_file = output_path.rsplit('.', 1)[0] + '.mp4'
        
        # Determine hardware acceleration codec
        system = platform.system()
        if system == 'Darwin':  # macOS
            encoder = 'h264_videotoolbox'
        elif system == 'Windows':
            encoder = 'h264_nvenc'  # NVIDIA GPU
        else:  # Linux
            encoder = 'h264_vaapi'  # Intel GPU
        
        try:
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file if it exists
                '-framerate', str(target_fps),
                '-i', os.path.join(temp_dir, 'frame_%05d.png'),
                '-c:v', encoder,
                '-b:v', '80M',
                '-maxrate', '100M',
                '-bufsize', '100M',
                '-preset', 'fast',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_file
            ]
            
            logger.info(f"Creating video with hardware acceleration ({encoder})...")
            subprocess.run(ffmpeg_cmd, check=True)
            
        except subprocess.CalledProcessError:
            logger.warning("Hardware acceleration failed, falling back to software encoding...")
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',
                '-framerate', str(target_fps),
                '-i', os.path.join(temp_dir, 'frame_%05d.png'),
                '-c:v', 'libx264',
                '-preset', 'faster',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_file
            ]
            subprocess.run(ffmpeg_cmd, check=True)
        
        # Clean up temporary files
        shutil.rmtree(temp_dir)
        
        logger.info(f"Recording completed: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Error during recording: {str(e)}")
        raise
        
    finally:
        driver.quit()

def main():
    from config import OUTPUT_DIR
    
    #modes = ['car', 'walk']
    modes = ['walk']
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
                output_path = os.path.join(
                    OUTPUT_DIR, 
                    f"projection_animation_{model_size}_{mode}_{direction}.mp4"
                )
                
                logger.info(f"\nProcessing {model_size} model {mode} {direction} animation")
                
                if platform.system() == 'Darwin':  # macOS
                    record_animation_mac(
                        os.path.abspath(html_path),
                        output_path,
                        ANIMATION_CONFIG['total_seconds']
                    )
                else:
                    frames_dir = os.path.join(
                        OUTPUT_DIR, 
                        f"animation_frames_{model_size}_{mode}_{direction}"
                    )
                    save_frames_as_images(os.path.abspath(html_path), frames_dir)
                    create_video_from_frames(frames_dir, output_path)
                
                logger.info(f"Completed: {output_path}")

if __name__ == "__main__":
    main() 