#!/usr/bin/with-contenv bashio

bashio::log.info "Starting EPF E-Ink Add-on..."

export IMMICH_API_KEY=$(bashio::config 'immich_api_key')
export IMMICH_URL=$(bashio::config 'immich_url')
export ALBUM_NAME=$(bashio::config 'album_name' 'EPF')
export ROTATION_ANGLE=$(bashio::config 'rotation_angle' '0')
export COLOR_ENHANCE=$(bashio::config 'color_enhance' '1.0')
export CONTRAST=$(bashio::config 'contrast' '1.0')
export SLEEP_DURATION=$(bashio::config 'sleep_duration' '3600')
export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export IMAGE_QUALITY=$(bashio::config 'image_quality' '85')

# Set INGRESS_PATH directly (Home Assistant provides this automatically)
# If running in Ingress mode, HA handles the routing without needing the token
export INGRESS_PATH="/api/hassio_ingress"

if [ -z "${IMMICH_API_KEY}" ]; then
    bashio::log.fatal "IMMICH_API_KEY is required!"
    exit 1
fi

if [ -z "${IMMICH_URL}" ]; then
    bashio::log.fatal "IMMICH_URL is required!"
    exit 1
fi

bashio::log.info "Configuration loaded:"
bashio::log.info "  Immich URL: ${IMMICH_URL}"
bashio::log.info "  Album: ${ALBUM_NAME}"
bashio::log.info "  Rotation: ${ROTATION_ANGLE}°"
bashio::log.info "  Color Enhance: ${COLOR_ENHANCE}"
bashio::log.info "  Contrast: ${CONTRAST}"
bashio::log.info "  Sleep Duration: ${SLEEP_DURATION}s"
bashio::log.info "  Log Level: ${LOG_LEVEL}"
bashio::log.info "  Image Quality: ${IMAGE_QUALITY}%"
bashio::log.info "  Ingress Path: ${INGRESS_PATH}"

cd /app || exit 1

exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level ${LOG_LEVEL} \
    app:app