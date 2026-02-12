# Single stage build for Memory Layer API using observability base
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.2.7

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies into system Python (alongside neural_hive_observability)
COPY services/memory-layer-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m -u 1000 app

# Copy application code
COPY services/memory-layer-api/src/ ./src/

# Copy Avro schemas
COPY schemas/memory-sync-event/ ./schemas/memory-sync-event/

# Fix ownership and permissions for non-root user
RUN chown -R app:app /app && chmod -R a+r /app

# Update PYTHONPATH
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# Switch to non-root user
USER app

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

# Start application with uvicorn (single worker for local development)
CMD ["sh", "-c", "python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1"]
