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
    
    # Set to 8K resolution (7680x4320)
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=7680')
    firefox_options.add_argument('--height=4320')
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    # Add hardware acceleration options
    firefox_options.set_preference('layers.acceleration.force-enabled', True)
    firefox_options.set_preference('gfx.canvas.azure.accelerated', True)
    firefox_options.set_preference('media.hardware-video-decoding.force-enabled', True)
    
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info("Starting Firefox WebDriver at 8K resolution...")
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

        # Apply browser zoom using CSS transform
        driver.execute_script("""
            // Apply strong browser zoom using CSS transforms
            document.body.style.transformOrigin = 'center center';
            document.body.style.transform = 'scale(4.0)'; // 400% zoom (4x)
            
            // Adjust scroll position to center the view if needed
            try {
                // Find the main canvas or container
                const mapContainer = document.querySelector('.deck-container') || 
                                   document.querySelector('#deck-container') ||
                                   document.querySelector('canvas').parentElement;
                
                if (mapContainer) {
                    // Calculate center points
                    const containerRect = mapContainer.getBoundingClientRect();
                    const centerX = containerRect.width / 2;
                    const centerY = containerRect.height / 2;
                    
                    // Scroll to center of interest
                    window.scrollTo({
                        left: centerX * 4 - window.innerWidth / 2,
                        top: centerY * 4 - window.innerHeight / 2,
                        behavior: 'instant'
                    });
                }
            } catch (e) {
                // Silent fail for scroll adjustment
            }
        """)
        
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
                driver.execute_script("""
                    const progressElement = document.querySelector('.progress');
                    if (progressElement) {
                        progressElement.style.width = '""" + str(progress) + """%';
                    }
                """)
            
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
    """Create video from frames using hardware acceleration with 8K settings"""
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
    logger.info(f"Resolution: {width}x{height}")
    
    # Try hardware-accelerated encoding first
    output_file = output_path.rsplit('.', 1)[0] + '.mp4'
    
    # Determine available hardware acceleration
    system = platform.system()
    if system == 'Darwin':  # macOS
        # Use videotoolbox encoder which supports Metal Performance Shaders (MPS)
        encoder = 'hevc_videotoolbox'
    elif system == 'Windows':
        encoder = 'h264_nvenc'  # NVIDIA GPU
    else:  # Linux
        encoder = 'h264_vaapi'  # Intel GPU
    
    try:
        # Use 8K-optimized bitrate settings
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file
            '-framerate', str(target_fps),
            '-i', os.path.join(frame_dir, 'frame_%05d.png'),
            '-c:v', encoder,
            '-b:v', '120M',  # Bitrate for 8K
            '-maxrate', '140M',
            '-bufsize', '140M',
            '-allow_sw', '1',  # Allow software processing if needed
            '-pix_fmt', 'yuv420p',
            '-tag:v', 'hvc1',  # For better compatibility
            '-movflags', '+faststart',
            output_file
        ]
        
        logger.info(f"Creating 8K video with hardware acceleration ({encoder})...")
        subprocess.run(ffmpeg_cmd, check=True)
        logger.info(f"8K video successfully created at: {output_file}")
        return output_file
        
    except subprocess.CalledProcessError:
        logger.warning(f"Hardware acceleration failed, falling back to software encoding...")
        
        # Fall back to software encoding with 8K optimized settings
        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            '-framerate', str(target_fps),
            '-i', os.path.join(frame_dir, 'frame_%05d.png'),
            '-c:v', 'libx264',
            '-preset', 'medium',  # Balance between speed and quality
            '-crf', '20',  # Good quality
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_file
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
        logger.info(f"8K video successfully created at: {output_file}")
        return output_file

def record_animation_mac(html_path, output_path, duration_seconds, start_time_offset=0):
    """Record animation using headless Firefox and ffmpeg at 8K resolution
    
    Parameters:
    - html_path: Path to the HTML file
    - output_path: Path to save the output video
    - duration_seconds: Duration to record in seconds
    - start_time_offset: Seconds to skip before starting recording (default: 0)
    """
    logger.info(f"Starting Firefox for 8K screen recording (segment: {start_time_offset}s to {start_time_offset + duration_seconds}s)...")
    
    # Set Firefox options for 8K resolution with standard view proportions
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    
    # Use 8K resolution (7680x4320)
    firefox_options.add_argument('--width=7680')  # 8K width
    firefox_options.add_argument('--height=4320')  # 8K height
    
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
        
        logger.info(f"Animation initialized, applying browser zoom and skipping to {start_time_offset} seconds...")
        
        # Use browser-level zoom to get a much stronger zoom effect
        driver.execute_script("""
            // Apply moderate browser zoom using CSS transforms
            document.body.style.transformOrigin = '0 0';  // Top-left corner as origin
            document.body.style.transform = 'scale(4.0)'; // 400% zoom (4x)
            
            // Force immediate scroll to top-left to reset view position
            window.scrollTo(0, 0);
            
            // Now find the map center and scroll to it
            setTimeout(function() {
                try {
                    // Find the main canvas or container
                    const canvas = document.querySelector('canvas');
                    const mapContainer = document.querySelector('.deck-container') || 
                                       document.querySelector('#deck-container') ||
                                       canvas.parentElement;
                    
                    if (mapContainer) {
                        // Get the center of the map (use the canvas dimensions)
                        const centerX = canvas.width / 2;
                        const centerY = canvas.height / 2;
                        
                        // Adjust for the zoom factor (4x)
                        const zoomFactor = 4.0;
                        const scrollX = (centerX * zoomFactor) - (window.innerWidth / 2);
                        const scrollY = (centerY * zoomFactor) - (window.innerHeight / 2);
                        
                        // Scroll to the calculated center point
                        window.scrollTo(scrollX, scrollY);
                    }
                } catch (e) {
                    // Silent fail for scroll adjustment
                }
            }, 500); // Wait a bit for the transform to take effect
        """)
        
        # Skip to desired start time by advancing the animation time
        if start_time_offset > 0:
            # Set animation time variable to start_time_offset
            driver.execute_script(f"""
                if (window.animationTime !== undefined) {{
                    window.animationTime = {start_time_offset};
                }}
                
                // Try to find animation controllers in common frameworks
                if (window.deck && window.deck.timeline) {{
                    window.deck.timeline.setTime({start_time_offset});
                }}
                
                // Update any progress indicators
                const progressElement = document.querySelector('.progress');
                if (progressElement) {{
                    const totalDuration = {ANIMATION_CONFIG['total_seconds']};
                    const progressPercentage = ({start_time_offset} / totalDuration) * 100;
                    progressElement.style.width = progressPercentage + '%';
                }}
            """)
        
        logger.info(f"Starting 8K recording for {duration_seconds} seconds...")
        
        # Create temporary directory for frames
        temp_dir = os.path.join(os.path.dirname(output_path), "temp_frames")
        os.makedirs(temp_dir, exist_ok=True)
        
        target_fps = ANIMATION_CONFIG['fps']  # Use FPS from config (30)
        frames_to_capture = int(duration_seconds * target_fps)
        frame_interval = 1.0 / target_fps
        
        logger.info(f"Recording configuration:")
        logger.info(f"Resolution: 7680x4320 (8K)")
        logger.info(f"Target FPS: {target_fps}")
        logger.info(f"Total frames to capture: {frames_to_capture}")
        logger.info(f"Recording duration: {duration_seconds} seconds")
        
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
                driver.execute_script(f"""
                    const progressElement = document.querySelector('.progress');
                    if (progressElement) {{
                        progressElement.style.width = '{progress}%';
                    }}
                """)
            
            # Wait for all image processing to complete
            for future in futures:
                future.result()
        
        # Calculate actual duration
        actual_duration = time.perf_counter() - start_time
        logger.info(f"Recording completed in {actual_duration:.2f} seconds")
        
        # Use ffmpeg to create video with exact frame rate
        output_file = output_path.rsplit('.', 1)[0] + '.mp4'
        
        # Determine hardware acceleration codec
        system = platform.system()
        if system == 'Darwin':  # macOS
            # For MPS acceleration on macOS, can use h265 (HEVC) for better quality
            encoder = 'hevc_videotoolbox'
        elif system == 'Windows':
            encoder = 'h264_nvenc'  # NVIDIA GPU
        else:  # Linux
            encoder = 'h264_vaapi'  # Intel GPU
        
        try:
            # For 8K quality
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file if it exists
                '-framerate', str(target_fps),
                '-i', os.path.join(temp_dir, 'frame_%05d.png'),
                '-c:v', encoder,
                '-b:v', '120M',  # High bitrate for 8K
                '-maxrate', '140M',
                '-bufsize', '140M',
                '-allow_sw', '1',  # Allow software processing if needed
                '-pix_fmt', 'yuv420p',
                '-tag:v', 'hvc1',  # For better compatibility
                '-movflags', '+faststart',
                output_file
            ]
            
            logger.info(f"Creating 8K video with hardware acceleration ({encoder})...")
            subprocess.run(ffmpeg_cmd, check=True)
            
        except subprocess.CalledProcessError:
            logger.warning("Hardware acceleration failed, falling back to software encoding...")
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',
                '-framerate', str(target_fps),
                '-i', os.path.join(temp_dir, 'frame_%05d.png'),
                '-c:v', 'libx264',
                '-preset', 'medium',  # Balance between speed and quality
                '-crf', '20',  # Good quality
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_file
            ]
            subprocess.run(ffmpeg_cmd, check=True)
        
        # Clean up temporary files
        shutil.rmtree(temp_dir)
        
        logger.info(f"8K recording completed: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Error during recording: {str(e)}")
        raise
        
    finally:
        driver.quit()

def main():
    from config import OUTPUT_DIR
    
    # Recording duration in seconds
    segment_duration = 30  # 30 seconds per animation segment
    
    # Define segments to record for each direction
    # Format: (hour_offset, half_hour_offset)
    # For 24-hour animation that spans a full day (24 minutes = 1440 seconds total)
    # Each half hour = 30 seconds, each minute = 1 second
    inbound_segment = (7, 0)  # 7:00-7:30 AM segment for inbound
    outbound_segment = (17, 0)  # 5:00-5:30 PM segment for outbound
    
    # Convert time offsets to seconds
    # In a 24-minute (1440 second) animation representing 24 hours:
    # Each half hour = 30 seconds of animation time
    seconds_per_half_hour = 30
    seconds_per_minute = 1
    
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
                
                # Choose appropriate time segment based on direction
                if direction == 'inbound':
                    hour, half_hour = inbound_segment
                    time_description = f"{hour}:00-{hour}:30am"
                else:  # outbound
                    hour, half_hour = outbound_segment
                    time_description = f"{hour-12}:00-{hour-12}:30pm"
                
                # Calculate start time offset in seconds
                start_time_offset = (hour * 2 * seconds_per_half_hour) + (half_hour * seconds_per_half_hour)
                
                # Define output filename with time segment info
                output_path = os.path.join(
                    OUTPUT_DIR, 
                    f"projection_animation_{model_size}_{mode}_{direction}_{time_description}_8k_zoomed.mp4"
                )
                
                logger.info(f"\nProcessing {model_size} model {mode} {direction} animation at 8K resolution")
                logger.info(f"Recording segment: {time_description} (offset: {start_time_offset}s, duration: {segment_duration}s)")
                
                if platform.system() == 'Darwin':  # macOS
                    record_animation_mac(
                        os.path.abspath(html_path),
                        output_path,
                        segment_duration,
                        start_time_offset
                    )
                else:
                    # For non-macOS platforms, we'd need to implement similar time-skipping
                    # in the save_frames_as_images function
                    logger.warning("Time segment recording not implemented for non-macOS platforms")
                    frames_dir = os.path.join(
                        OUTPUT_DIR, 
                        f"animation_frames_{model_size}_{mode}_{direction}_{time_description}_8k_zoomed"
                    )
                    save_frames_as_images(os.path.abspath(html_path), frames_dir)
                    create_video_from_frames(frames_dir, output_path)
                
                logger.info(f"Completed 8K recording: {output_path}")

if __name__ == "__main__":
    main()