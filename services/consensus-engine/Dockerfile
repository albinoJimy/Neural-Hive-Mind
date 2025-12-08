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
    pip install --no-cache-dir --user -r specialists-requirements.txt && \
    python -m uvicorn --version && \
    echo "✓ uvicorn runtime verification passed"

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

# Copy Python dependencies from builder directly with correct ownership
# Using --chown in COPY is much faster than chown -R after the fact
COPY --from=builder --chown=consensus:consensus /root/.local /home/consensus/.local

# Copy libraries directly to PYTHONPATH with correct ownership
COPY --chown=consensus:consensus libraries/python/neural_hive_observability /app/neural_hive_observability
COPY --chown=consensus:consensus libraries/python/neural_hive_specialists /app/neural_hive_specialists

# Copy application code with correct ownership
COPY --chown=consensus:consensus services/consensus-engine/src /app/src

# Ensure schema directories exist
RUN mkdir -p /app/schemas/cognitive-plan /app/schemas/consolidated-decision && \
    chown -R consensus:consensus /app/schemas

# Copy Avro schemas
COPY --chown=consensus:consensus schemas/cognitive-plan/cognitive-plan.avsc /app/schemas/cognitive-plan/cognitive-plan.avsc
COPY --chown=consensus:consensus schemas/consolidated-decision/consolidated-decision.avsc /app/schemas/consolidated-decision/consolidated-decision.avsc

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
# Using 1 worker to avoid race conditions in startup (MongoDB indexes, Kafka consumer group)
# For production with multiple replicas, use 1 worker per pod and scale horizontally
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
