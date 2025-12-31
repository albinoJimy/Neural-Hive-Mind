# Stage 1 - Builder
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.3 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    protobuf-compiler \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create and activate virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy local libraries (entire package with setup.py)
COPY libraries/security /tmp/neural_hive_security

# Copy requirements and install dependencies to venv
COPY services/guard-agents/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /tmp/neural_hive_security || true && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY services/guard-agents/src/ ./src/

# Stage 2 - Runtime
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.3

# Create non-root user
RUN groupadd -r guard-agent && useradd -r -u 1000 -g guard-agent guard-agent

# Set working directory
WORKDIR /app

# Copy virtualenv from builder (does not overwrite base image packages)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Ensure access to global site-packages (where neural_hive_observability is installed)
ENV PYTHONPATH="/usr/local/lib/python3.11/site-packages:$PYTHONPATH"

# Copy source code
COPY --from=builder /app/src ./src

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
