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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def save_frames_as_images(html_path, output_dir):
    """Save individual frames as PNG images with proper timing"""
    # Get duration from shared config
    duration_seconds = ANIMATION_CONFIG['total_seconds']
    fps = ANIMATION_CONFIG['fps']
    
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=1920')
    firefox_options.add_argument('--height=1080')
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    
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
        frames_to_capture = int(duration_seconds * fps)
        
        # Clear existing frames
        for file in os.listdir(output_dir):
            if file.startswith('frame_'):
                os.remove(os.path.join(output_dir, file))
        
        # Get the initial animation time
        start_time = driver.execute_script("return performance.now()")
        
        for i in range(frames_to_capture):
            current_frame = i + 1
            progress = (current_frame * 100) / frames_to_capture
            
            # Synchronize with animation timing
            expected_time = start_time + (i * 1000 / fps)  # Convert to milliseconds
            current_time = driver.execute_script("return performance.now()")
            
            if current_time < expected_time:
                time.sleep((expected_time - current_time) / 1000)  # Convert back to seconds
            
            # Take screenshot
            screenshot = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            
            # Convert to RGBA if needed
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Save frame
            frame_path = os.path.join(output_dir, f'frame_{i:05d}.png')
            image.save(frame_path, 'PNG')
            
            # Print progress
            if current_frame % 30 == 0 or current_frame == frames_to_capture:
                logger.info(f"Progress: {progress:.1f}% ({current_frame}/{frames_to_capture} frames)")
            
            # Update progress bar in browser
            driver.execute_script(f"document.querySelector('.progress').style.width = '{progress}%'")
            
            time.sleep(1/30)  # Maintain 30 FPS
        
        logger.info("Frame capture completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during frame capture: {str(e)}")
        raise
    
    finally:
        driver.quit()

def create_video_from_frames(frame_dir, output_path):
    """Create video from frames using parallel processing"""
    fps = ANIMATION_CONFIG['fps']
    frame_files = sorted([f for f in os.listdir(frame_dir) if f.startswith('frame_')])
    if not frame_files:
        raise ValueError("No frames found in directory")
    
    logger.info(f"Found {len(frame_files)} frames to process")
    first_frame = cv2.imread(os.path.join(frame_dir, frame_files[0]), cv2.IMREAD_UNCHANGED)
    height, width = first_frame.shape[:2]
    
    # Calculate expected durations from shared config
    total_frames = len(frame_files)
    total_duration = total_frames / fps
    hour_duration = total_duration / ANIMATION_CONFIG['hours_per_day']
    
    logger.info(f"Animation timing:")
    logger.info(f"Total frames: {total_frames}")
    logger.info(f"FPS: {fps}")
    logger.info(f"Total duration: {total_duration:.2f} seconds ({total_duration/60:.1f} minutes)")
    logger.info(f"Hours in animation: {ANIMATION_CONFIG['hours_per_day']}")
    logger.info(f"Duration per hour: {hour_duration:.2f} seconds")
    
    # Try different codecs in order of preference
    codecs = [('avc1', '.mp4'), ('mp4v', '.mp4'), ('vp09', '.webm')]
    
    for codec, ext in codecs:
        try:
            output_file = output_path.rsplit('.', 1)[0] + ext
            fourcc = cv2.VideoWriter_fourcc(*codec)
            out = cv2.VideoWriter(output_file, fourcc, fps, (width, height), True)
            
            if not out.isOpened():
                logger.warning(f"Failed to initialize VideoWriter with codec {codec}")
                continue
            
            logger.info(f"Creating video with codec {codec}")
            
            # Pre-load frames in parallel
            def load_frame(frame_file):
                frame_path = os.path.join(frame_dir, frame_file)
                frame = cv2.imread(frame_path, cv2.IMREAD_UNCHANGED)
                if frame.shape[2] == 4:  # RGBA
                    bgr = frame[:, :, :3]
                    alpha = frame[:, :, 3]
                    white_bg = np.ones_like(bgr) * 255
                    alpha_3d = np.stack([alpha, alpha, alpha], axis=2) / 255.0
                    return (bgr * alpha_3d + white_bg * (1 - alpha_3d)).astype(np.uint8)
                return frame
            
            # Process frames in chunks to balance memory usage and performance
            chunk_size = 100
            with ThreadPoolExecutor(max_workers=mp.cpu_count()) as executor:
                for i in range(0, len(frame_files), chunk_size):
                    chunk = frame_files[i:i+chunk_size]
                    frames = list(executor.map(load_frame, chunk))
                    
                    for frame in frames:
                        out.write(frame)
                    
                    progress = min(100, (i + len(chunk)) * 100 / len(frame_files))
                    logger.info(f"Video encoding progress: {progress:.1f}% ({i + len(chunk)}/{len(frame_files)} frames)")
            
            out.release()
            logger.info(f"Video successfully created at: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Failed with codec {codec}: {str(e)}")
            continue
    
    raise RuntimeError("Failed to create video with any available codec")

def record_animation_mac(html_path, output_path, duration_seconds):
    """Record animation using headless Firefox and ffmpeg"""
    logger.info("Starting Firefox for screen recording...")
    
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=1920')
    firefox_options.add_argument('--height=1080')
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    
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
        
        fps = ANIMATION_CONFIG['fps']
        frames_to_capture = int(duration_seconds * fps)
        frame_interval = 1.0 / fps  # Time between frames in seconds
        
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
        start_time = time.time()
        
        # Capture frames
        for i in range(frames_to_capture):
            # Calculate when this frame should be captured
            target_time = start_time + (i * frame_interval)
            current_time = time.time()
            
            # Wait if we're ahead of schedule
            if current_time < target_time:
                time.sleep(target_time - current_time)
            
            # Take screenshot
            screenshot = driver.get_screenshot_as_png()
            image = Image.open(io.BytesIO(screenshot))
            
            # Save frame
            frame_path = os.path.join(temp_dir, f'frame_{i:05d}.png')
            image.save(frame_path, 'PNG')
            
            # Print progress
            if i % 30 == 0 or i == frames_to_capture - 1:
                progress = ((i + 1) * 100) / frames_to_capture
                logger.info(f"Recording progress: {progress:.1f}% ({i + 1}/{frames_to_capture} frames)")
        
        # Use ffmpeg to create video with exact frame rate
        output_file = output_path.rsplit('.', 1)[0] + '.mp4'
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file if it exists
            '-framerate', str(fps),
            '-i', os.path.join(temp_dir, 'frame_%05d.png'),
            '-c:v', 'libx264',
            '-preset', 'slow',  # Higher quality encoding
            '-pix_fmt', 'yuv420p',
            '-crf', '18',  # Higher quality (lower is better, 18-28 is good range)
            '-vf', f'fps={fps}',  # Force exact output framerate
            output_file
        ]
        
        logger.info("Creating video from frames...")
        subprocess.run(ffmpeg_cmd, check=True)
        
        # Clean up temporary files
        import shutil
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