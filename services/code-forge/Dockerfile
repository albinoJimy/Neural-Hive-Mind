# Multi-stage Dockerfile for Code Forge - Neural Code Generation Pipeline
# Stage 1: Builder
FROM neural-hive-mind/python-observability-base:1.2.0 AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy local libraries first
COPY libraries/neural_hive_integration /tmp/neural_hive_integration

# Copy requirements and install dependencies
COPY services/code-forge/requirements.txt .
RUN pip install --no-cache-dir --user /tmp/neural_hive_integration || true && \
    pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (git for template cloning, docker-cli for builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && curl -fsSL https://get.docker.com -o get-docker.sh \
    && sh get-docker.sh \
    && rm get-docker.sh \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
ENV PATH=/root/.local/bin:$PATH

# Copy shared libraries
COPY libraries/python/neural_hive_specialists /app/libraries/neural_hive_specialists

# Copy service code
COPY services/code-forge/src /app/src

# Create non-root user
RUN useradd -m -u 1000 codeforge && \
    chown -R codeforge:codeforge /app

USER codeforge

# Expose ports
EXPOSE 8080 50051 9090

# Labels
LABEL service.name="code-forge" \
      service.version="1.0.0" \
      service.layer="execution" \
      service.component="neural-code-generation"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Entry point
ENTRYPOINT ["python", "-m", "src.main"]
