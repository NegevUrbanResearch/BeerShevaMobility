import logging
import json
import sys
import os
import re

logger = logging.getLogger(__name__)

def get_debug_panel_html():
    """Return HTML and CSS for debug panel"""
    return """
    <style>
        .debug-panel {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 10px;
            font-family: monospace;
            z-index: 1000;
            max-height: 200px;
            overflow-y: auto;
            display: none;
        }
    </style>
    <div id="debug-panel" class="debug-panel"></div>
    """

def get_debug_js():
    """Return JavaScript for debug logging"""
    return """
    const debugLog = {
        panel: document.getElementById('debug-panel'),
        enabled: new URLSearchParams(window.location.search).get('debug') === 'true',
        log: function(message) {
            console.log(message);
            if (this.enabled) {
                const entry = document.createElement('div');
                entry.textContent = `${new Date().toISOString().substr(11, 8)} - ${message}`;
                this.panel.appendChild(entry);
                if (this.panel.children.length > 50) {
                    this.panel.removeChild(this.panel.firstChild);
                }
                this.panel.scrollTop = this.panel.scrollHeight;
            }
        }
    };
    if (debugLog.enabled) {
        debugLog.panel.style.display = 'block';
    }
    """

def validate_animation_data(trips_data, buildings_data, poi_borders, poi_fills):
    """Validate animation data structures and log debug info"""
    logger.info("\nAnimation Data Summary:")
    logger.info(f"Trips data length: {len(trips_data)}")
    if trips_data:
        logger.info(f"Sample trip timestamps: {trips_data[0]['timestamps'][:5]}")
    logger.info(f"Buildings data length: {len(buildings_data)}")
    logger.info(f"POI borders length: {len(poi_borders)}")
    return True

def format_html_safely(template, format_values):
    """Safely format HTML template with error checking"""
    try:
        # Find all placeholders in template
        placeholders = re.findall(r'%\(([^)]+)\)[sdfg]', template)
        logger.info("\nTemplate placeholders found:")
        for p in placeholders:
            logger.info(f"- {p} {'✓' if p in format_values else '✗'}")
        
        # Check for missing placeholders
        missing = [p for p in placeholders if p not in format_values]
        if missing:
            logger.error(f"Missing format values: {missing}")
            raise ValueError(f"Missing format values: {missing}")
            
        # Log provided values that aren't used
        extra = [k for k in format_values if k not in placeholders]
        if extra:
            logger.warning(f"Unused format values: {extra}")
        
        # Log data sizes before formatting
        logger.info("\nTemplate Format Values Sizes:")
        for key, value in format_values.items():
            if isinstance(value, str):
                logger.info(f"{key}: {len(value)} characters")
            else:
                logger.info(f"{key}: {sys.getsizeof(value)} bytes")
        
        formatted_html = template % format_values
        return formatted_html
        
    except Exception as e:
        logger.error(f"Error formatting HTML template: {str(e)}")
        raise