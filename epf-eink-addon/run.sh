#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: EPF E-Ink Photo Frame
# Startup script with configuration management
# ==============================================================================

bashio::log.info "Starting EPF E-Ink Add-on..."

# ==============================================================================
# Read configuration from Home Assistant
# ==============================================================================

export IMMICH_API_KEY=$(bashio::config 'immich_api_key')
export IMMICH_URL=$(bashio::config 'immich_url')
export ALBUM_NAME=$(bashio::config 'album_name' 'EPF')
export ROTATION_ANGLE=$(bashio::config 'rotation_angle' '0')
export COLOR_ENHANCE=$(bashio::config 'color_enhance' '1.0')
export CONTRAST=$(bashio::config 'contrast' '1.0')
export SLEEP_DURATION=$(bashio::config 'sleep_duration' '3600')
export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export IMAGE_QUALITY=$(bashio::config 'image_quality' '85')

# Flask configuration
export FLASK_APP=/app/app.py
export FLASK_ENV=production
export PORT=5000

# ==============================================================================
# Validation
# ==============================================================================

if [ -z "${IMMICH_API_KEY}" ]; then
    bashio::log.fatal "IMMICH_API_KEY is required!"
    bashio::log.fatal "Please configure your Immich API key in the add-on configuration."
    exit 1
fi

if [ -z "${IMMICH_URL}" ]; then
    bashio::log.fatal "IMMICH_URL is required!"
    bashio::log.fatal "Please configure your Immich URL in the add-on configuration."
    exit 1
fi

# ==============================================================================
# Log configuration (ohne Secrets)
# ==============================================================================

bashio::log.info "Configuration loaded:"
bashio::log.info "  Immich URL: ${IMMICH_URL}"
bashio::log.info "  Album: ${ALBUM_NAME}"
bashio::log.info "  Rotation: ${ROTATION_ANGLE}°"
bashio::log.info "  Color Enhance: ${COLOR_ENHANCE}"
bashio::log.info "  Contrast: ${CONTRAST}"
bashio::log.info "  Sleep Duration: ${SLEEP_DURATION}s"
bashio::log.info "  Log Level: ${LOG_LEVEL}"
bashio::log.info "  Image Quality: ${IMAGE_QUALITY}%"

# ==============================================================================
# Start Flask Server
# ==============================================================================

bashio::log.info "Starting Flask server on port ${PORT}..."

cd /app || exit 1

# Start with Gunicorn for better performance
exec gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level ${LOG_LEVEL} \
    app:app
