# Multi-stage build for Scout Agents
FROM neural-hive-mind/python-observability-base:1.0.7 AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies in virtualenv
COPY services/scout-agents/requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/usr/local/lib/python3.11/site-packages:$PYTHONPATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy and install neural_hive_integration library with proto_stubs
COPY libraries/neural_hive_integration/ /tmp/neural_hive_integration/
RUN pip install --no-cache-dir /tmp/neural_hive_integration/ && \
    rm -rf /tmp/neural_hive_integration

# Runtime stage
FROM neural-hive-mind/python-observability-base:1.0.7

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

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/usr/local/lib/python3.11/site-packages:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose ports
EXPOSE 8000 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Run application
CMD ["python", "-m", "src.main"]
