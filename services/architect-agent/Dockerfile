# Architect Agent Dockerfile
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js and Mermaid CLI
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @mermaid-js/mermaid-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r architect && useradd -r -g architect -u 1000 architect

# Create directories and set permissions
RUN mkdir -p /app/logs /app/tmp && chown -R architect:architect /app

# Copy Python packages from builder
COPY --from=builder --chown=architect:architect /root/.local /home/architect/.local

# Copy Mermaid CLI from builder
COPY --from=builder --chown=architect:architect /usr/local/bin /usr/local/bin

# Copy source code
COPY --chown=architect:architect src/ ./src/

# Set environment
ENV PATH=/home/architect/.local/bin:/usr/local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Switch to non-root user
USER architect

EXPOSE 8008 9098

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8008/health/live || exit 1

CMD ["python", "-m", "src.main"]
