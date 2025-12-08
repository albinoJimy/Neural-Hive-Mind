# Stage 1 - Builder
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2 - Runtime
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r worker-agent && useradd -r -g worker-agent worker-agent

# Set working directory
WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /root/.local /home/worker-agent/.local

# Copy source code from host context
COPY src/ ./src

# Set PATH to include user binaries
ENV PATH=/home/worker-agent/.local/bin:$PATH

# Expose ports
EXPOSE 8080 9090

# Security context
USER worker-agent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run application
CMD ["python", "-m", "src.main"]
