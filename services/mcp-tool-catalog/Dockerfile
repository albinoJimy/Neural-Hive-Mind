# Multi-stage build for MCP Tool Catalog Service
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.3 AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies to venv
COPY services/mcp-tool-catalog/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.3

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder (does not overwrite base image packages)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Ensure access to global site-packages (where neural_hive_observability is installed)
ENV PYTHONPATH="/usr/local/lib/python3.11/site-packages:$PYTHONPATH"

# Copy application code
COPY services/mcp-tool-catalog/src/ ./src/

# Create non-root user
RUN useradd -m -u 1000 mcp-user && chown -R mcp-user:mcp-user /app
USER mcp-user

# Expose ports
EXPOSE 8080 9091

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run application
CMD ["python", "-m", "src.main"]
