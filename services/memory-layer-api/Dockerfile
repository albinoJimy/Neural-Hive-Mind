# Multi-stage build for Memory Layer API
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY services/memory-layer-api/requirements.txt .
COPY libraries/python/neural_hive_observability/requirements.txt ./observability_requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt -r observability_requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Fix executable permissions and verify uvicorn installation
RUN find /root/.local/bin -type f -exec chmod +x {} \; && \
    ls -la /root/.local/bin/uvicorn* || echo "WARNING: uvicorn not found in /root/.local/bin"

# Copy shared libraries directly to PYTHONPATH
COPY libraries/python/neural_hive_observability /app/neural_hive_observability

# Copy application code
COPY services/memory-layer-api/src/ ./src/

# Update PATH and PYTHONPATH
# Add user site-packages to PYTHONPATH so python -m works
ENV PYTHONPATH=/app:/root/.local/lib/python3.11/site-packages \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# Expose ports
EXPOSE 8000 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

# Labels
LABEL maintainer="Neural Hive-Mind Team <team@neural-hive-mind.org>" \
      version="1.0.0" \
      description="Memory Layer API - Unified access to multicamadas memory" \
      neural-hive.io/component="memory-layer" \
      neural-hive.io/layer="conhecimento-dados" \
      neural-hive.io/domain="unified-memory"

# Start application with uvicorn (using python -m to avoid PATH issues)
CMD python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
