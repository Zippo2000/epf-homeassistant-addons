# EPF E-Ink Add-on - Placeholder Dockerfile
# This will be completed in Phase 3

ARG BUILD_FROM
FROM $BUILD_FROM

# Install base dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip

# Set working directory
WORKDIR /app

# Copy startup script
COPY run.sh /
RUN chmod a+x /run.sh

# Placeholder - files will be added in Phase 3
CMD ["/run.sh"]
