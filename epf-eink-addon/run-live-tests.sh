#!/bin/sh
# =============================================================================
# Run the LIVE integration tests against a real Immich v3 server.
#
# Connection details are read from the local, git-ignored ./.env file:
#     IMMICH_URL      base URL of the Immich server
#     IMMICH_API_KEY  the server's API key (needs the "asset.download" grant)
#     IMMICH_ALBUM    album the tests exercise
# so nothing sensitive is ever a command-line argument. The two non-secret
# values may be overridden for a one-off run:
#
#     sh run-live-tests.sh                       # uses ./.env
#     sh run-live-tests.sh <immich-url> [album]
#
# Unlike the offline suite (Dockerfile.test's default CMD), these tests touch
# the network. They SKIP cleanly (green-or-skipping, never red) when not opted
# in via EPF_LIVE_TESTS=1 or when the connection details are missing — so an
# ordinary offline run is unaffected.
# =============================================================================
set -eu

# Locate this script's directory (the add-on dir) and work from it so the
# Docker build context is a relative `.` (never an mangled absolute path).
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# Import KEY=VALUE pairs from ./.env if present (supplies the vars above).
set -a
[ -f ./.env ] && . ./.env
set +a

# Command-line overrides take precedence over the .env values.
IMMICH_URL="${1:-${IMMICH_URL:-}}"
IMMICH_ALBUM="${2:-${IMMICH_ALBUM:-eink}}"

if [ -z "$IMMICH_URL" ]; then
    echo "Usage: sh run-live-tests.sh [<immich-url> [album]]" >&2
    echo "  (defaults read from ./.env: IMMICH_URL, IMMICH_ALBUM, IMMICH_API_KEY)" >&2
    exit 1
fi
if [ -z "${IMMICH_API_KEY:-}" ]; then
    echo "Error: no IMMICH_API_KEY available (put it in the local ./.env file)." >&2
    exit 1
fi

IMAGE="epf-eink-tests:live"
echo "==> Building test image ${IMAGE} (Dockerfile.test) ..."
docker build -q -f Dockerfile.test -t "$IMAGE" . >/dev/null

echo "==> Running LIVE tests against ${IMMICH_URL} (album: ${IMMICH_ALBUM}) ..."
# `bash -c` (not a shebang on a script file) so the entrypoint is immune to
# any line-ending / missing-interpreter fragility.
docker run --rm \
    -e EPF_LIVE_TESTS=1 \
    -e IMMICH_URL="$IMMICH_URL" \
    -e IMMICH_API_KEY="$IMMICH_API_KEY" \
    -e IMMICH_ALBUM="$IMMICH_ALBUM" \
    -e IMMICH_PHOTO_DEST=/tmp/epf_live_photos \
    "$IMAGE" \
    bash -c 'cd /app && python3 -m pytest -v tests/test_live.py'
