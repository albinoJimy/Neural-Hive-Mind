# Stage 1: Builder
FROM neural-hive-mind/python-observability-base:1.2.0 AS builder

WORKDIR /app

COPY services/analyst-agents/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt && \
    find /root/.local -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    find /root/.local -type f -name '*.pyc' -delete 2>/dev/null || true

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY services/analyst-agents/src/ ./src/

# Create non-root user
RUN useradd -m -u 1000 analyst && chown -R analyst:analyst /app
USER analyst

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Expose ports
EXPOSE 8000 50051

# Run application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
