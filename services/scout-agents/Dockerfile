# Multi-stage build for Scout Agents
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.2.6 AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy libraries needed for requirements.txt
COPY libraries /libraries

# Copy requirements and install dependencies in virtualenv with system site-packages
COPY services/scout-agents/requirements.txt .
RUN python -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir /libraries/python/neural_hive_resilience/ && \
    pip install --no-cache-dir /libraries/neural_hive_integration/

# Runtime stage
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.2.6

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder (does not overwrite base image packages)
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY services/scout-agents/src/ ./src/

# Create non-root user
RUN useradd -m -u 1000 scout && chown -R scout:scout /app
USER scout

# Set environment variables - virtualenv inherits system site-packages
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose ports
EXPOSE 8000 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Run application
CMD ["python", "-m", "src.main"]
