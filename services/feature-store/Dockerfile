# Multi-stage build for Feature Store Service
# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy local libraries
COPY libraries/python/neural_hive_security /tmp/neural_hive_security

# Copy requirements and install dependencies
COPY services/feature-store/requirements.txt .
RUN pip install --no-cache-dir --user /tmp/neural_hive_security && \
    pip install --no-cache-dir --user -r requirements.txt && \
    python -m uvicorn --version && \
    echo "✓ uvicorn runtime verification passed"

# Stage 2: Runtime
FROM python:3.12-slim

# Labels for metadata
LABEL maintainer="Neural Hive-Mind Team <team@neural-hive-mind.org>"
LABEL component="feature-store"
LABEL layer="ml"
LABEL version="1.0.0"
LABEL description="Serviço de Feature Store para ML"

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash app

WORKDIR /app

# Copy Python dependencies from builder (--chown required for non-root user)
COPY --from=builder --chown=app:app /root/.local /home/app/.local

# Copy application code
COPY --chown=app:app services/feature-store/src/ ./src/

# Set environment variables
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONPATH=/app:/home/app/.local/lib/python3.12/site-packages \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO

# Switch to non-root user
USER app

# Expose ports
EXPOSE 8080 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run application
CMD ["sh", "-c", "python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --workers ${UVICORN_WORKERS:-1}"]
