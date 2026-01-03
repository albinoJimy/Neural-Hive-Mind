# Stage 1 - Builder
FROM neural-hive-mind/python-observability-base:1.0.7 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy local libraries
COPY libraries/neural_hive_integration /tmp/neural_hive_integration

# Copy requirements and install dependencies
COPY services/worker-agents/requirements.txt .
RUN pip install --no-cache-dir --user /tmp/neural_hive_integration && \
    pip install --no-cache-dir --user -r requirements.txt

# Stage 2 - Runtime
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r worker-agent && useradd -r -g worker-agent worker-agent

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /root/.local /home/worker-agent/.local
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy neural_hive_observability library
COPY --chown=worker-agent:worker-agent libraries/python/neural_hive_observability/neural_hive_observability /app/neural_hive_observability

# Copy proto stubs from service-registry (needed by worker-agents client)
COPY --chown=worker-agent:worker-agent services/service-registry/src/proto /app/proto

# Copy source code from host context
COPY services/worker-agents/src/ ./src

# Copy Avro schemas for Kafka serialization
COPY --chown=worker-agent:worker-agent schemas/execution-result/ /app/schemas/execution-result/
COPY --chown=worker-agent:worker-agent schemas/execution-ticket/ /app/schemas/execution-ticket/

# Set PATH and PYTHONPATH to include user binaries and local packages
ENV PATH=/home/worker-agent/.local/bin:$PATH \
    PYTHONPATH=/app:/home/worker-agent/.local/lib/python3.11/site-packages

# Expose ports
EXPOSE 8080 9090

# Security context
USER worker-agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run application
CMD ["python", "-m", "src.main"]
