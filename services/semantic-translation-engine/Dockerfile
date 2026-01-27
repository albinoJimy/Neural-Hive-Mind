# Multi-stage build for Semantic Translation Engine
# Stage 1: Builder
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.5 AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY services/semantic-translation-engine/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt && \
    python -m uvicorn --version && \
    echo "✓ uvicorn runtime verification passed" && \
    pip install --no-cache-dir --user \
        https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.7.0/pt_core_news_sm-3.7.0.tar.gz \
        https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1.tar.gz && \
    echo "✓ spaCy models downloaded"

# Stage 2: Runtime
FROM python:3.11-slim

# Labels for metadata
LABEL maintainer="Neural Hive-Mind Team <team@neural-hive-mind.org>"
LABEL component="semantic-translation-engine"
LABEL layer="cognitiva"
LABEL version="1.0.0"
LABEL description="Motor de Tradução Semântica - Geração de Planos Cognitivos"

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash app

WORKDIR /app

# Copy Python dependencies from builder - ensure all packages are available
COPY --from=builder /root/.local /home/app/.local
COPY --from=builder /usr/local/lib/python3.11/site-packages /home/app/.local/lib/python3.11/site-packages

# Copy shared libraries
COPY --chown=app:app libraries/python/neural_hive_risk_scoring /app/libraries/neural_hive_risk_scoring
COPY --chown=app:app libraries/python/neural_hive_observability /app/libraries/neural_hive_observability

# Copy application code
COPY --chown=app:app services/semantic-translation-engine/src/ ./src/

# Copy Avro schemas
RUN mkdir -p /app/schemas/intent-envelope /app/schemas/cognitive-plan
COPY --chown=app:app schemas/intent-envelope/intent-envelope.avsc /app/schemas/intent-envelope/intent-envelope.avsc
COPY --chown=app:app schemas/cognitive-plan/cognitive-plan.avsc /app/schemas/cognitive-plan/cognitive-plan.avsc

# Set environment variables
ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONPATH=/app:/app/libraries:/home/app/.local/lib/python3.11/site-packages \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO

# Switch to non-root user
USER app

# Expose ports
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run application
CMD ["sh", "-c", "python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
