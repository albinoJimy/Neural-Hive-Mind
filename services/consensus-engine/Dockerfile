# Multi-stage Dockerfile for Consensus Engine
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install setuptools first
RUN pip install --no-cache-dir setuptools wheel

# Copy requirements and install Python dependencies
COPY services/consensus-engine/requirements.txt .
COPY libraries/python/neural_hive_specialists/requirements.txt ./specialists-requirements.txt
RUN grep -v "neuralHive" requirements.txt > requirements-build.txt && \
    pip install --no-cache-dir --user -r requirements-build.txt && \
    pip install --no-cache-dir --user -r specialists-requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN useradd -m -u 1000 consensus

# Copy Python dependencies from builder to consensus user home
COPY --from=builder /root/.local /home/consensus/.local

# Copy libraries directly to PYTHONPATH (no installation needed)
COPY libraries/python/neural_hive_observability /app/neural_hive_observability
COPY libraries/python/neural_hive_specialists /app/neural_hive_specialists

# Copy application code
COPY services/consensus-engine/src /app/src

# Fix ownership
RUN chown -R consensus:consensus /app /home/consensus/.local

# Environment variables
ENV PYTHONPATH=/app:/home/consensus/.local/lib/python3.11/site-packages \
    PYTHONUNBUFFERED=1 \
    PATH=/home/consensus/.local/bin:$PATH

USER consensus

# Expose ports
EXPOSE 8000 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Labels
LABEL maintainer="Neural Hive-Mind Team <team@neural-hive-mind.org>" \
      version="1.0.0" \
      component="consensus-aggregator" \
      layer="cognitiva" \
      description="Mecanismo de Consenso Multi-Agente - Neural Hive-Mind"

# Start application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
