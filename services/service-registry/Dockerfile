# Multi-stage build for Service Registry
FROM neural-hive-mind/python-observability-base:1.2.3 AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy local libraries first

# Copy requirements and install dependencies
COPY services/service-registry/requirements.txt .

# Install local library and requirements (excluding neural_hive_observability from pip)
RUN grep -v "neural_hive_observability" requirements.txt > requirements-filtered.txt && \
    pip install --no-cache-dir --user -r requirements-filtered.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install grpc_health_probe
RUN GRPC_HEALTH_PROBE_VERSION=v0.4.19 && \
    curl -L https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 \
    -o /bin/grpc_health_probe && \
    chmod +x /bin/grpc_health_probe

# Copy Python dependencies from builder (user packages + system packages from base)
COPY --from=builder /root/.local /root/.local
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy source code
COPY services/service-registry/src/ ./src/

# Set Python path
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

# Expose ports
EXPOSE 50051 9090

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD grpc_health_probe -addr=:50051 || exit 1

# Run the service
CMD ["python", "-m", "src.main"]
