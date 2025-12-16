# Stage 1 - Builder
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    protobuf-compiler \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy neural_hive_security library (deve ser copiado no build context)
# Build command: docker build -f services/guard-agents/Dockerfile --build-arg BUILD_CONTEXT=. -t guard-agents .
COPY libraries/security/neural_hive_security /tmp/neural_hive_security

# Copy requirements and install dependencies
COPY services/guard-agents/requirements.txt .
RUN pip install --no-cache-dir --prefix=/opt/venv -r requirements.txt && \
    pip install --no-cache-dir --prefix=/opt/venv -e /tmp/neural_hive_security

# Copy source code
COPY services/guard-agents/src/ ./src/

# Stage 2 - Runtime
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r guard-agent && useradd -r -u 1000 -g guard-agent guard-agent

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /opt/venv /opt/venv

# Copy source code
COPY --from=builder /app/src ./src

# Set PATH to include venv binaries
ENV PATH=/opt/venv/bin:$PATH

# Labels for traceability
LABEL neural-hive.io/component="guard-agents" \
      neural-hive.io/layer="resilience" \
      maintainer="Neural Hive Team <team@neural-hive.io>"

# Expose ports: HTTP (8080), gRPC (50051), Metrics (9090)
EXPOSE 8080 50051 9090

# Security context
USER guard-agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
