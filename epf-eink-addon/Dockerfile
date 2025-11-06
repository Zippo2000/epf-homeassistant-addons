ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:bookworm
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Python und Build-Dependencies installieren
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/

# --break-system-packages ist in Containern sicher, da keine System-Python-Apps vorhanden sind
RUN pip3 install --no-cache-dir --break-system-packages --upgrade pip \
    && pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY app.py /app/
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
