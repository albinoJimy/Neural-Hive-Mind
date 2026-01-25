# Stage 1 - Builder
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.4 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    protobuf-compiler \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create virtualenv with system site-packages to inherit neural_hive_observability
RUN python -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy local libraries
COPY libraries/security /tmp/neural_hive_security
COPY libraries/neural_hive_integration /tmp/neural_hive_integration

# Copy requirements and install dependencies to venv
COPY services/guard-agents/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /tmp/neural_hive_security || true && \
    pip install --no-cache-dir /tmp/neural_hive_integration && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY services/guard-agents/src/ ./src/

# Stage 2 - Runtime
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.4

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r guard-agent && useradd -r -u 1000 -g guard-agent guard-agent

# Set working directory
WORKDIR /app

# Copy virtualenv from builder (inherits system site-packages for neural_hive_observability)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# Copy source code
COPY --from=builder /app/src ./src

# Fix ownership and permissions
RUN chown -R guard-agent:guard-agent /app && chmod -R a+r /app

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
