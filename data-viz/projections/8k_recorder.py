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
import subprocess
import platform
import shutil
# Import configuration from anim_transparent.py
from anim_transparent import ANIMATION_CONFIG, OUTPUT_DIR
import traceback

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

def record_animation_mac_enhanced(html_path, output_path, duration_seconds, start_time_offset=0, animation_speed=0.05):
    """
    Record animation with guaranteed 30 FPS output and detailed FPS logging
    to verify proper capture rate accounting for time warping.
    """
    logger.info(f"Starting forced 30 FPS recording with animation speed={animation_speed}x")
    
    # Setup Firefox
    firefox_options = FirefoxOptions()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--width=7680')
    firefox_options.add_argument('--height=4320')
    firefox_options.set_preference('webgl.force-enabled', True)
    firefox_options.set_preference('webgl.disabled', False)
    firefox_options.set_preference('layers.acceleration.force-enabled', True)
    
    driver = webdriver.Firefox(options=firefox_options)
    
    try:
        # Load animation
        driver.get(f'file://{html_path}')
        
        # Wait for animation to initialize
        logger.info("Waiting for animation to initialize...")
        WebDriverWait(driver, 60).until(
            lambda d: d.execute_script("return window.animationStarted === true")
        )
        
        # Configure animation with slower speed
        driver.execute_script(f"""
            window.setAnimationSpeed({animation_speed});
            console.log("Animation speed reduced to {animation_speed}x for smoother rendering");
            document.body.style.transformOrigin = 'center center';
            document.body.style.transform = 'scale(4.0)';
        """)
        
        # Create temporary directory
        temp_dir = os.path.join(os.path.dirname(output_path), "temp_frames")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Calculate frame counts
        target_fps = 30  # FIXED at exactly 30 FPS for output
        frames_to_capture = int(duration_seconds * target_fps)
        
        # Get animation configuration
        animation_duration = ANIMATION_CONFIG['animation_duration']
        animation_total_seconds = ANIMATION_CONFIG['total_seconds']
        animation_frames_per_second = animation_duration / animation_total_seconds
        start_frame = int(start_time_offset * animation_frames_per_second)
        
        logger.info(f"Recording configuration:")
        logger.info(f"- Animation speed: {animation_speed}x")
        logger.info(f"- Target output FPS: 30 (fixed)")
        logger.info(f"- Animation frames per second: {animation_frames_per_second:.2f}")
        logger.info(f"- Starting from animation frame: {start_frame}")
        logger.info(f"- Frames to capture: {frames_to_capture}")
        logger.info(f"- Expected final duration: {duration_seconds:.2f} seconds")
        
        # FPS tracking variables
        fps_log_interval = 10  # Log FPS every 10 frames
        capture_start_time = time.time()
        last_log_time = capture_start_time
        frames_since_last_log = 0
        
        # Capture frames with precise timing
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            
            for i in range(frames_to_capture):
                frame_start_time = time.time()
                
                # Calculate exact animation frame for this output frame
                animation_frame = start_frame + int((i / target_fps) * animation_frames_per_second)
                
                # Request the specific frame
                driver.execute_script(f"""
                    renderComplete = false;
                    window.setAnimationFrame({animation_frame});
                """)
                
                # Wait for frame to complete rendering
                try:
                    WebDriverWait(driver, 15).until(
                        lambda d: d.execute_script("return window.isFrameRendered() === true")
                    )
                except Exception as e:
                    logger.warning(f"Timeout waiting for frame {animation_frame} to render")
                    time.sleep(1.0)
                
                # Capture screenshot
                screenshot = driver.get_screenshot_as_png()
                frame_path = os.path.join(temp_dir, f'frame_{i:05d}.png')
                futures.append(executor.submit(process_frame, screenshot, frame_path))
                
                # Update FPS tracking
                frame_end_time = time.time()
                frame_duration = frame_end_time - frame_start_time
                frames_since_last_log += 1
                
                # Log FPS metrics periodically
                if i % fps_log_interval == 0 or i == frames_to_capture - 1:
                    current_time = time.time()
                    elapsed_since_last_log = current_time - last_log_time
                    total_elapsed = current_time - capture_start_time
                    
                    # Calculate various FPS metrics
                    if elapsed_since_last_log > 0:
                        actual_fps = frames_since_last_log / elapsed_since_last_log
                        effective_fps = actual_fps / animation_speed  # Account for time warping
                        
                        # Calculate estimated final duration
                        if i > 0:
                            estimated_total_time = (total_elapsed / (i+1)) * frames_to_capture
                            estimated_remaining = estimated_total_time - total_elapsed
                        else:
                            estimated_remaining = "calculating..."
                        
                        # Log detailed FPS information
                        logger.info(f"\nFrame {i+1}/{frames_to_capture} ({((i+1)/frames_to_capture*100):.1f}%)")
                        logger.info(f"- Last frame render time: {frame_duration:.2f}s")
                        logger.info(f"- Real-time capture rate: {actual_fps:.2f} fps")
                        logger.info(f"- Effective output rate: {effective_fps:.2f} fps (target: 30 fps)")
                        logger.info(f"- Time elapsed: {total_elapsed:.2f}s")
                        logger.info(f"- Estimated remaining: {estimated_remaining if isinstance(estimated_remaining, str) else f'{estimated_remaining:.2f}s'}")
                        logger.info(f"- Final video will be exactly 30 fps regardless of capture rate")
                        
                        # Reset tracking for next interval
                        last_log_time = current_time
                        frames_since_last_log = 0
                        
                        # Warning if effective FPS is too far from target
                        if effective_fps < 25 or effective_fps > 35:
                            logger.warning(f"⚠️ Effective FPS ({effective_fps:.2f}) is significantly different from target (30)")
                            if effective_fps < 25:
                                logger.warning(f"Consider reducing animation_speed for smoother rendering")
            
            # Wait for processing
            for future in futures:
                future.result()
        
        # Calculate final recording statistics
        total_record_time = time.time() - capture_start_time
        average_real_fps = frames_to_capture / total_record_time
        average_effective_fps = average_real_fps / animation_speed
        
        logger.info(f"\nRecording completed!")
        logger.info(f"- Total frames captured: {frames_to_capture}")
        logger.info(f"- Total recording time: {total_record_time:.2f} seconds")
        logger.info(f"- Average real-time capture rate: {average_real_fps:.2f} fps")
        logger.info(f"- Average effective fps: {average_effective_fps:.2f} fps")
        logger.info(f"- Animation speed used: {animation_speed}x")
        logger.info(f"- Final video will be exactly 30 fps regardless of capture rate")
        
        # Reset animation
        driver.execute_script("window.setNormalPlayback(); window.setAnimationSpeed(1.0);")
        
        # Create video with EXACTLY 30 FPS
        output_file = output_path.rsplit('.', 1)[0] + '.mp4'
        
        try:
            # macOS hardware-accelerated encoding
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',
                '-framerate', '30',  # Force 30 FPS input interpretation
                '-i', os.path.join(temp_dir, 'frame_%05d.png'),
                '-c:v', 'hevc_videotoolbox',
                '-b:v', '120M',
                '-maxrate', '140M',
                '-bufsize', '140M',
                '-r', '30',  # Force 30 FPS output
                '-vsync', 'cfr',  # Constant frame rate
                '-pix_fmt', 'yuv420p',
                '-tag:v', 'hvc1',
                '-movflags', '+faststart',
                output_file
            ]
            
            logger.info("Creating video with exact 30 FPS timing using hardware acceleration...")
            subprocess.run(ffmpeg_cmd, check=True)
            
        except subprocess.CalledProcessError:
            logger.warning("Hardware acceleration failed, falling back to software encoding...")
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',
                '-framerate', '30',  # Force 30 FPS input interpretation
                '-i', os.path.join(temp_dir, 'frame_%05d.png'),
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '20',
                '-r', '30',  # Force 30 FPS output
                '-vsync', 'cfr',  # Constant frame rate
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_file
            ]
            subprocess.run(ffmpeg_cmd, check=True)
        
        # Log final ffmpeg command that was used
        logger.info(f"FFmpeg command used: {' '.join(ffmpeg_cmd)}")
        
        # Clean up
        shutil.rmtree(temp_dir)
        logger.info(f"Successfully created 30 FPS video: {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Error during recording: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    finally:
        driver.quit()

def main():
    # Removed import from config module since it's now imported from anim_transparent
    
    # Recording duration in seconds
    segment_duration = 30  # 30 seconds per animation segment
    
    # Define segments to record for each direction
    # Format: (hour_offset, minute_offset)
    # For 24-hour animation that spans a full day (12 minutes = 720 seconds total)
    # Each hour = 30 seconds, each minute = 0.5 seconds
    inbound_segment = (7, 0)  # 7-8 AM segment for inbound (starts at 7:00 AM)
    outbound_segment = (17, 0)  # 5-6 PM segment for outbound (starts at 5:00 PM)
    
    # Convert time offsets to seconds
    # In a 12-minute (720 second) animation representing 24 hours:
    # Each hour = 30 seconds of animation time
    seconds_per_hour = ANIMATION_CONFIG['seconds_per_hour']
    seconds_per_minute = seconds_per_hour / 60  # Calculate based on seconds_per_hour
    
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
                    hour, minute = inbound_segment
                    time_description = f"{hour}-{hour+1}am"
                else:  # outbound
                    hour, minute = outbound_segment
                    time_description = f"{hour-12}-{hour-11}pm"
                
                # Calculate start time offset in seconds
                start_time_offset = (hour * seconds_per_hour) + (minute * seconds_per_minute)
                
                # Define output filename with time segment info
                output_path = os.path.join(
                    OUTPUT_DIR, 
                    f"projection_animation_{model_size}_{mode}_{direction}_{time_description}_8k_zoomed.mp4"
                )
                
                logger.info(f"\nProcessing {model_size} model {mode} {direction} animation at 8K resolution")
                logger.info(f"Recording segment: {time_description} (offset: {start_time_offset}s, duration: {segment_duration}s)")
                
                if platform.system() == 'Darwin':  # macOS
                    record_animation_mac_enhanced(
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