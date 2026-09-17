ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:bookworm
FROM ${BUILD_FROM}

# Optional overrides for the settings-page footer; when unset the values are
# derived in-image (version: config.yaml manifest, timestamp: .build_stamp below).
ARG ADDON_VERSION
ENV ADDON_VERSION=${ADDON_VERSION}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Python and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    python3.11-dev \
    gcc \
    g++ \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff-dev \
    tk-dev \
    tcl-dev \
    libffi-dev \
    libraw-dev \
    wget \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build timestamp (UTC) captured at image-build time; honours SOURCE_DATE_EPOCH
# for reproducible builds (set it to a fixed epoch to freeze the value).
RUN if [ -n "${SOURCE_DATE_EPOCH}" ]; then \
      date -u -d "@${SOURCE_DATE_EPOCH}" '+%Y-%m-%d %H:%M:%S UTC' > .build_stamp; \
    else \
      date -u '+%Y-%m-%d %H:%M:%S UTC' > .build_stamp; \
    fi

COPY requirements.txt /app/

# --break-system-packages is safe inside containers, since no system Python apps are present
RUN pip3 install --no-cache-dir --break-system-packages --upgrade pip \
    && pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy Cython source
COPY cpy.pyx /app/
COPY setup.py /app/

# BUILD CYTHON MODULE during the Docker build!
RUN python3 setup.py build_ext --inplace && \
    ls -la /app/*.so && \
    echo "✅ Cython module compiled successfully"

COPY app.py /app/
COPY providers.py /app/
COPY config.yaml /app/
COPY templates/ /app/templates/

COPY run.sh /
RUN chmod a+x /run.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:5000/health || exit 1

EXPOSE 5000

LABEL \
    io.hass.type="addon" \
    io.hass.arch="amd64" \
    io.hass.version="1.0.0"

CMD ["/run.sh"]
