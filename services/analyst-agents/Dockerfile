# Stage 1: Builder
FROM neural-hive-mind/python-observability-base:1.0.7 AS builder

WORKDIR /app

COPY services/analyst-agents/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt && \
    find /root/.local -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    find /root/.local -type f -name '*.pyc' -delete 2>/dev/null || true

# Stage 2: Runtime - use same base to get neural_hive_observability
FROM neural-hive-mind/python-observability-base:1.0.7

WORKDIR /app

# Create non-root user first
RUN useradd -m -u 1000 analyst

# Copy dependencies from builder to user home
COPY --from=builder --chown=analyst:analyst /root/.local /home/analyst/.local

# Fix pydantic-settings conflict - remove old versions and install correct ones
RUN rm -rf /home/analyst/.local/lib/python3.11/site-packages/pydantic* && \
    rm -rf /usr/local/lib/python3.11/site-packages/pydantic* 2>/dev/null || true && \
    pip install --no-cache-dir --target=/home/analyst/.local/lib/python3.11/site-packages \
        pydantic==2.10.4 pydantic-settings==2.6.1

# Copy application code
COPY --chown=analyst:analyst services/analyst-agents/src/ ./src/

# Set environment
ENV PATH=/home/analyst/.local/bin:$PATH
ENV PYTHONPATH=/home/analyst/.local/lib/python3.11/site-packages:/app

USER analyst

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Expose ports
EXPOSE 8000 50051

# Run application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
