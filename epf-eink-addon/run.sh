#!/usr/bin/with-contenv bashio

bashio::log.info "Starting EPF E-Ink Add-on..."

export IMAGE_SOURCE=$(bashio::config 'image_source' 'immich')
export IMMICH_API_KEY=$(bashio::config 'immich_api_key')
export IMMICH_URL=$(bashio::config 'immich_url')
export ALBUM_NAME=$(bashio::config 'album_name' 'eink')
export HA_API_TOKEN=$(bashio::config 'ha_api_token')
export HA_URL=$(bashio::config 'ha_url')
export COMFYUI_PROMPT=$(bashio::config 'comfyui_prompt')
export COMFYUI_NEGATIVE_PROMPT=$(bashio::config 'comfyui_negative_prompt')
export COMFYUI_WIDTH=$(bashio::config 'comfyui_width' '800')
export COMFYUI_HEIGHT=$(bashio::config 'comfyui_height' '480')
export COMFYUI_SEED=$(bashio::config 'comfyui_seed' '-1')
export COMFYUI_MAX_GENERATIONS=$(bashio::config 'comfyui_max_generations' '50')
export COMFYUI_ENTITY_ID=$(bashio::config 'comfyui_entity_id')
export COMFYUI_DIRECT_URL=$(bashio::config 'comfyui_direct_url')
export COMFYUI_WORKFLOW_JSON=$(bashio::config 'comfyui_workflow_json')
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
bashio::log.info "  Image Source: ${IMAGE_SOURCE}"
bashio::log.info "  Immich URL: ${IMMICH_URL}"
bashio::log.info "  Album: ${ALBUM_NAME}"
bashio::log.info "  HA URL: ${HA_URL}"
bashio::log.info "  ComfyUI Prompt: ${COMFYUI_PROMPT}"
bashio::log.info "  ComfyUI Direct URL: ${COMFYUI_DIRECT_URL}"
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