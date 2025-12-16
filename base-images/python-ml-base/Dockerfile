# Neural Hive-Mind Python ML Base Image
# Base image with Python 3.11 and ML build dependencies

FROM python:3.11-slim

# Build arguments for versioning
ARG VERSION=1.0.0
ARG BUILD_DATE

# Install essential build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to version 24.0
RUN pip install --no-cache-dir --upgrade pip==24.0

# Set working directory
WORKDIR /app

# OCI metadata labels
LABEL org.opencontainers.image.title="Neural Hive-Mind Python ML Base"
LABEL org.opencontainers.image.description="Base image with Python 3.11 and ML build dependencies"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL neural-hive-mind.org/layer="base"
LABEL neural-hive-mind.org/component="python-ml-base"
