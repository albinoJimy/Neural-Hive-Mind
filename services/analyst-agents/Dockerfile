# Stage 1: Builder
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.5 AS builder

WORKDIR /app

COPY services/analyst-agents/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt && \
    find /root/.local -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    find /root/.local -type f -name '*.pyc' -delete 2>/dev/null || true

# Stage 2: Runtime - use same base to get neural_hive_observability
FROM 37.60.241.150:30500/neural-hive-mind/python-observability-base:1.2.5

WORKDIR /app

# Create non-root user first
RUN useradd -m -u 1000 analyst

# Copy dependencies from builder to user home
COPY --from=builder --chown=analyst:analyst /root/.local /home/analyst/.local

# Copy neural_hive_observability library (latest version with inject_grpc_context)
COPY --chown=analyst:analyst libraries/python/neural_hive_observability/neural_hive_observability /app/neural_hive_observability

# Copy neural_hive_integration library (for ServiceRegistryClient and other integrations)
COPY --chown=analyst:analyst libraries/neural_hive_integration/neural_hive_integration /app/neural_hive_integration

# Copy application code
COPY --chown=analyst:analyst services/analyst-agents/src/ ./src/

# Ensure all files are readable
RUN chmod -R a+r /app

# Set environment - user packages first, then system packages for neural_hive_observability
ENV PATH=/home/analyst/.local/bin:$PATH
ENV PYTHONPATH=/home/analyst/.local/lib/python3.11/site-packages:/usr/local/lib/python3.11/site-packages:/app

USER analyst

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Expose ports
EXPOSE 8000 50051

# Run application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
