FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for PDF/Word/Visio parsing
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/doc-ingestion/requirements.txt ./requirements-service.txt

# Copy neural_hive_integration library (required for service_registry_client)
COPY libraries/neural_hive_integration /tmp/neural_hive_integration
COPY libraries/python/neural_hive_resilience /tmp/neural_hive_resilience
COPY libraries/python/neural_hive_llm /tmp/neural_hive_llm

# Replace relative path and install dependencies including local libraries
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir /tmp/neural_hive_integration && \
    pip install --no-cache-dir /tmp/neural_hive_llm && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY services/doc-ingestion/src ./src

# Copy proto files from service-registry
COPY services/service-registry/src/proto/ ./src/proto/

# Expose port
EXPOSE 8018

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8018"]
