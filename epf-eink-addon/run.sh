#!/usr/bin/with-contenv bashio

bashio::log.info "Starting EPF E-Ink Add-on..."

export IMMICH_API_KEY=$(bashio::config 'immich_api_key')
export IMMICH_URL=$(bashio::config 'immich_url')
export ALBUM_NAME=$(bashio::config 'album_name' 'eink')
export ROTATION_ANGLE=$(bashio::config 'rotation_angle' '270')
export COLOR_ENHANCE=$(bashio::config 'color_enhance' '1.8')
export CONTRAST=$(bashio::config 'contrast' '0.9')
export DITHERING_STRENGTH=$(bashio::config 'dithering_strength' '1.0')
export DISPLAY_MODE=$(bashio::config 'display_mode' 'fill')
export IMAGE_ORDER=$(bashio::config 'image_order' 'random')
export DITHERING_METHOD=$(bashio::config 'dithering_method' 'atkinson')
export WAKEUP_INTERVAL=$(bashio::config 'wakeup_interval' '1440')
export SLEEP_START_HOUR=$(bashio::config 'sleep_start_hour' '23')
export SLEEP_START_MINUTE=$(bashio::config 'sleep_start_minute' '0')
export SLEEP_END_HOUR=$(bashio::config 'sleep_end_hour' '6')
export SLEEP_END_MINUTE=$(bashio::config 'sleep_end_minute' '0')
export LOG_LEVEL=$(bashio::config 'log_level' 'info')

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
bashio::log.info "  Dithering Strength: ${DITHERING_STRENGTH}"
bashio::log.info "  Display Mode: ${DISPLAY_MODE}"
bashio::log.info "  Image Order: ${IMAGE_ORDER}"
bashio::log.info "  Dithering Method: ${DITHERING_METHOD}"
bashio::log.info "  Wake Up Interval: ${WAKEUP_INTERVAL} minutes"
bashio::log.info "  Sleep Time: ${SLEEP_START_HOUR}:${SLEEP_START_MINUTE} - ${SLEEP_END_HOUR}:${SLEEP_END_MINUTE}"
bashio::log.info "  Log Level: ${LOG_LEVEL}"

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