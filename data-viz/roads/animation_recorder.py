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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def save_frames_as_images(html_path, output_dir, duration_seconds=60):
    """Save individual frames as PNG images with robust progress tracking"""
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=1920')
    firefox_options.add_argument('--height=1080')
    # Enable WebGL
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
        frames_to_capture = duration_seconds * 30
        
        # Clear existing frames
        for file in os.listdir(output_dir):
            if file.startswith('frame_'):
                os.remove(os.path.join(output_dir, file))
        
        for i in range(frames_to_capture):
            current_frame = i + 1
            progress = (current_frame * 100) / frames_to_capture
            
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

def create_video_from_frames(frame_dir, output_path, fps=30):
    """Create video from frames using parallel processing"""
    frame_files = sorted([f for f in os.listdir(frame_dir) if f.startswith('frame_')])
    if not frame_files:
        raise ValueError("No frames found in directory")
    
    logger.info(f"Found {len(frame_files)} frames to process")
    first_frame = cv2.imread(os.path.join(frame_dir, frame_files[0]), cv2.IMREAD_UNCHANGED)
    height, width = first_frame.shape[:2]
    
    # Calculate expected durations
    total_frames = len(frame_files)
    total_duration = total_frames / fps
    hour_duration = total_duration / 24
    
    logger.info(f"Animation timing:")
    logger.info(f"Total frames: {total_frames}")
    logger.info(f"FPS: {fps}")
    logger.info(f"Total duration: {total_duration:.2f} seconds")
    logger.info(f"Hours in animation: 24")
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

def main():
    from config import OUTPUT_DIR
    
    # Process big model
    html_path = os.path.join(OUTPUT_DIR, "projection_animation_big.html")
    frames_dir_big = os.path.join(OUTPUT_DIR, "animation_frames_big")
    save_frames_as_images(os.path.abspath(html_path), frames_dir_big)
    output_path_big = os.path.join(OUTPUT_DIR, "projection_animation_big.mp4")
    create_video_from_frames(frames_dir_big, output_path_big)
    
    # Process small model
    html_path = os.path.join(OUTPUT_DIR, "projection_animation_small.html")
    frames_dir_small = os.path.join(OUTPUT_DIR, "animation_frames_small")
    save_frames_as_images(os.path.abspath(html_path), frames_dir_small)
    output_path_small = os.path.join(OUTPUT_DIR, "projection_animation_small.mp4")
    create_video_from_frames(frames_dir_small, output_path_small)
    
    logger.info(f"Videos saved to:\n{output_path_big}\n{output_path_small}")

if __name__ == "__main__":
    main() 