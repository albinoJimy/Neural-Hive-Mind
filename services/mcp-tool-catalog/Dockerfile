# Multi-stage build for MCP Tool Catalog Service
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.4 AS builder

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

# Copy and install neural_hive_integration library with proto_stubs
COPY libraries/neural_hive_integration/ /tmp/neural_hive_integration/
RUN pip install --no-cache-dir /tmp/neural_hive_integration/ && \
    rm -rf /tmp/neural_hive_integration

# Copy and install updated neural_hive_observability library
COPY libraries/python/neural_hive_observability/ /tmp/neural_hive_observability/
RUN pip install --no-cache-dir /tmp/neural_hive_observability/ && \
    rm -rf /tmp/neural_hive_observability

# Runtime stage
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.4

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Venv packages have priority over global site-packages
ENV PYTHONPATH="/opt/venv/lib/python3.11/site-packages:/usr/local/lib/python3.11/site-packages"

# Copy application code
COPY services/mcp-tool-catalog/src/ ./src/
COPY schemas/ ./schemas/

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
