# Stage 1 - Builder
FROM neural-hive-mind/python-observability-base:1.0.7 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    protobuf-compiler \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY services/self-healing-engine/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --prefix=/opt/venv -r requirements.txt

# Copy source code
COPY services/self-healing-engine/src/ ./src/

# Stage 2 - Runtime
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r healing-engine && useradd -r -u 1001 -g healing-engine healing-engine

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy packages globally from builder
RUN cp -r /opt/venv/lib/python3.11/site-packages/* /usr/local/lib/python3.11/site-packages/ 2>/dev/null || true

# Copy source code and playbooks
COPY --from=builder /app/src ./src
COPY services/self-healing-engine/playbooks/ ./playbooks/

# Set PATH and PYTHONPATH
ENV PATH=/usr/local/bin:$PATH \
    PYTHONPATH=/usr/local/lib/python3.11/site-packages:/app

# Labels for traceability
LABEL neural-hive.io/component="self-healing-engine" \
      neural-hive.io/layer="resilience" \
      maintainer="Neural Hive Team <team@neural-hive.io>"

# Expose ports: HTTP (8080), gRPC (50051), Metrics (9090)
EXPOSE 8080 50051 9090

# Security context
USER healing-engine

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
