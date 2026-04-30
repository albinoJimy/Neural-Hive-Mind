# Multi-stage build for Service Registry
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy local libraries
COPY libraries/python/neural_hive_observability /tmp/neural_hive_observability

# Copy requirements and install dependencies
COPY requirements-base.txt ./requirements-base.txt
COPY services/service-registry/requirements.txt ./requirements-service.txt
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir --user /tmp/neural_hive_observability && \
    pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r registry && useradd -r -g registry -u 1000 registry

# Install grpc_health_probe with retry logic
RUN GRPC_HEALTH_PROBE_VERSION=v0.4.19 && \
    curl -fsSL --retry 5 --retry-delay 5 --connect-timeout 30 --max-time 120 \
    https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 \
    -o /usr/local/bin/grpc_health_probe && \
    chmod +x /usr/local/bin/grpc_health_probe

# Create directories and set permissions
RUN mkdir -p /app/logs /app/tmp && chown -R registry:registry /app /usr/local/bin

# Copy Python dependencies from builder
COPY --from=builder --chown=registry:registry /root/.local /home/registry/.local

# Copy source code
COPY --chown=registry:registry services/service-registry/src/ ./src/

# Set Python path
ENV PATH=/home/registry/.local/bin:/usr/local/bin:$PATH
ENV PYTHONPATH=/app

# Switch to non-root user
USER registry

# Expose ports
EXPOSE 50051 9090

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD /usr/local/bin/grpc_health_probe -addr=:50051 || exit 1

# Run the service
CMD ["python", "-m", "src.main"]
