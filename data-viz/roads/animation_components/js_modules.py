def get_animation_core_js():
    """Core animation logic and setup"""
    return """
    let trailLength = 2;
    let animationSpeed = 4;
    let animation;
    
    function animate() {
        console.log('Animation Configuration:', {
            totalFrames: LOOP_LENGTH,
            baseSpeed: animationSpeed,
            actualDurationSeconds: (LOOP_LENGTH * 60) / animationSpeed / 60,
            trailLength
        });

        let lastTime = 0;
        let activeTripsCount = 0;
        
        animation = popmotion.animate({
            from: 0,
            to: LOOP_LENGTH,
            duration: (LOOP_LENGTH * 60) / animationSpeed,
            repeat: Infinity,
            onUpdate: time => updateAnimation(time, lastTime, activeTripsCount)
        });
    }
    """

def get_layer_definitions_js():
    """Deck.gl layer definitions"""
    return """
    function createDarkOverlayLayer() {
        return new deck.PolygonLayer({
            id: 'dark-overlay',
            data: [{
                contour: [
                    [INITIAL_VIEW_STATE.longitude - 1, INITIAL_VIEW_STATE.latitude - 1],
                    [INITIAL_VIEW_STATE.longitude + 1, INITIAL_VIEW_STATE.latitude - 1],
                    [INITIAL_VIEW_STATE.longitude + 1, INITIAL_VIEW_STATE.latitude + 1],
                    [INITIAL_VIEW_STATE.longitude - 1, INITIAL_VIEW_STATE.latitude + 1]
                ]
            }],
            getPolygon: d => d.contour,
            getFillColor: [0, 0, 0, 255 * OVERLAY_OPACITY],
            getLineColor: [0, 0, 0, 0],
            extruded: false,
            pickable: false,
            opacity: 1,
            zIndex: 0
        });
    }

    function createTripsLayer(time) {
        return new deck.TripsLayer({
            id: 'trips',
            data: TRIPS_DATA,
            getPath: d => d.path,
            getTimestamps: d => getValidTimestamps(d, time),
            getColor: getPathColor,
            opacity: 0.8,
            widthMinPixels: 2,
            jointRounded: true,
            capRounded: true,
            trailLength,
            currentTime: time % ANIMATION_DURATION,
            updateTriggers: {
                getTimestamps: [time, trailLength]
            }
        });
    }
    """

def get_utility_functions_js():
    """Utility functions for the animation"""
    return """
    function getPathColor(path) {
        const destination = path[path.length - 1];
        const [destLon, destLat] = destination;
        
        const distToBGU = Math.hypot(destLon - BGU_INFO.lon, destLat - BGU_INFO.lat);
        const distToGavYam = Math.hypot(destLon - GAV_YAM_INFO.lon, destLat - GAV_YAM_INFO.lat);
        const distToSoroka = Math.hypot(destLon - SOROKA_INFO.lon, destLat - SOROKA_INFO.lat);
        
        if (distToBGU < POI_RADIUS) return [0, 255, 90];
        if (distToGavYam < POI_RADIUS) return [0, 191, 255];
        if (distToSoroka < POI_RADIUS) return [170, 0, 255];
        
        return [253, 128, 93];
    }

    function getValidTimestamps(d, currentTime) {
        const time = currentTime % ANIMATION_DURATION;
        return d.timestamps.map(times => {
            const validTimes = times.filter(t => 
                t <= time && 
                t > time - trailLength
            );
            return validTimes.length > 0 ? validTimes[0] : null;
        });
    }
    """ 