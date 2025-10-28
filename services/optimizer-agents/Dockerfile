# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy proto files and compile
COPY src/proto/ ./src/proto/
RUN python -m grpc_tools.protoc \
    -I./src/proto \
    --python_out=./src/proto \
    --grpc_python_out=./src/proto \
    ./src/proto/optimizer_agent.proto

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY src/ ./src/
COPY --from=builder /app/src/proto/*.py ./src/proto/

# Set Python path
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose ports
EXPOSE 50051 8080 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Labels
LABEL maintainer="Neural Hive-Mind Team <team@neuralhivemind.io>"
LABEL description="Optimizer Agents - Continuous Improvement and Policy Recalibration"
LABEL version="1.0.0"
LABEL component="optimizer-agents"
LABEL layer="estrategica"

# Run application
ENTRYPOINT ["python", "-m", "src.main"]
