# Single stage build for ML Inference API using observability base
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

# Copy requirements (base + service) and install dependencies into system Python
COPY requirements-base.txt ./requirements-base.txt
COPY services/ml-inference-api/requirements.txt ./requirements-service.txt
RUN sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' requirements-service.txt > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m -u 1000 app

# Copy application code (main.py lives at service root, modules in src/)
COPY services/ml-inference-api/main.py ./main.py
COPY services/ml-inference-api/src/ ./src/

# Fix ownership and permissions for non-root user
RUN chown -R app:app /app && chmod -R a+r /app

# Update PYTHONPATH
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# Switch to non-root user
USER app

# Expose port
EXPOSE 8020

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8020/health').read()"

# Labels
LABEL maintainer="Neural Hive-Mind Team <team@neural-hive-mind.org>" \
      version="0.2.0" \
      description="ML Inference API - Model prediction service with caching and Kafka integration" \
      neural-hive.io/component="ml-inference-api" \
      neural-hive.io/layer="ml-pipeline" \
      neural-hive.io/domain="inference"

# Start application with uvicorn (single worker for local development)
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port 8020 --workers 1"]
