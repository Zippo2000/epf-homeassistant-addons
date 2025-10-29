#!/usr/bin/with-contenv bashio
# ==============================================================================
# EPF E-Ink Add-on startup script
# This will be completed in Phase 4
# ==============================================================================

bashio::log.info "Starting EPF E-Ink Add-on..."

# Read configuration
IMMICH_API_KEY=$(bashio::config 'immich_api_key')
IMMICH_URL=$(bashio::config 'immich_url')
ALBUM_NAME=$(bashio::config 'album_name')

bashio::log.info "Immich URL: ${IMMICH_URL}"
bashio::log.info "Album: ${ALBUM_NAME}"

# Placeholder - Flask server will be started in Phase 5
bashio::log.info "EPF server starting (placeholder)..."
sleep infinity
