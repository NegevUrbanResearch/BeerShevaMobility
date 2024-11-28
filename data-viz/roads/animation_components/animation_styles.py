def get_base_styles():
    """Return base CSS styles for the animation"""
    return """
        body { margin: 0; padding: 0; }
        #container { width: 100vw; height: 100vh; position: relative; }
        .control-panel {
            position: absolute;
            top: 20px;
            left: 20px;
            background: #000000;
            padding: 12px;
            border-radius: 5px;
            color: #FFFFFF;
            font-family: Arial;
        }
        .methodology-container {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #000000;
            padding: 12px;
            border-radius: 5px;
            color: #FFFFFF;
            font-family: Arial;
            max-width: 300px;
        }
        .time-display {
            position: absolute;
            top: 80px;
            left: 20px;
            background: #000000;
            padding: 12px;
            border-radius: 5px;
            color: #FFFFFF;
            font-family: Arial;
        }
    """

def get_animation_constants():
    """Return JavaScript constants for animation"""
    return """
        const GL = {
            SRC_ALPHA: 0x0302,
            ONE_MINUS_SRC_ALPHA: 0x0303,
            FUNC_ADD: 0x8006
        };
        
        const ambientLight = new deck.AmbientLight({
            color: [255, 255, 255],
            intensity: 1.0
        });

        const pointLight = new deck.PointLight({
            color: [255, 255, 255],
            intensity: 2.0,
            position: [34.8, 31.25, 8000]
        });

        const lightingEffect = new deck.LightingEffect({ambientLight, pointLight});
        
        const INITIAL_VIEW_STATE = {
            longitude: 34.8113,
            latitude: 31.2627,
            zoom: 13,
            pitch: 60,
            bearing: 0
        };
        
        const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json';
        const OVERLAY_OPACITY = 0.5;
    """