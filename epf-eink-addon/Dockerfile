# ==============================================================================
# Home Assistant Add-on: EPF E-Ink Photo Frame
# Dockerfile for multi-architecture support
# ==============================================================================

ARG BUILD_FROM
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Setup base system
RUN \
    apk add --no-cache \
        python3=~3.12 \
        py3-pip=~23 \
        py3-setuptools=~70 \
        py3-wheel=~0.43 \
    \
    && apk add --no-cache --virtual .build-dependencies \
        gcc=~13 \
        g++=~13 \
        python3-dev=~3.12 \
        musl-dev=~1.2 \
        jpeg-dev=~9 \
        zlib-dev=~1.3 \
        freetype-dev=~2.13 \
        lcms2-dev=~2.16 \
        openjpeg-dev=~2.5 \
        tiff-dev=~4.6 \
        tk-dev=~8.6 \
        tcl-dev=~8.6 \
        libffi-dev=~3.4

# Create app directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt /app/

# Install Python packages
RUN \
    pip3 install --no-cache-dir --upgrade pip==24.3.1 \
    && pip3 install --no-cache-dir -r requirements.txt \
    \
    # Clean up build dependencies
    && apk del --no-network .build-dependencies \
    && rm -rf \
        /tmp/* \
        /var/cache/apk/* \
        /root/.cache

# Copy application files
COPY app.py /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:5000/health || exit 1

# Expose port
EXPOSE 5000

# Labels for Home Assistant
LABEL \
    io.hass.version="VERSION" \
    io.hass.type="addon" \
    io.hass.arch="armhf|armv7|aarch64|amd64|i386"

# Start script
CMD ["/run.sh"]
