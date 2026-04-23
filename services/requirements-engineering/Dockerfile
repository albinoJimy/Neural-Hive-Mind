FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/requirements-engineering/requirements.txt ./requirements-service.txt
COPY services/requirements-engineering/requirements-dev.txt ./requirements-dev.txt

# Copy local libraries needed by the service
COPY libraries/neural_hive_integration /tmp/neural_hive_integration
COPY libraries/python/neural_hive_resilience /tmp/neural_hive_resilience

# Replace relative path and install dependencies including local libraries
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir /tmp/neural_hive_integration && \
    pip install --no-cache-dir /tmp/neural_hive_resilience && \
    pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy application
COPY services/requirements-engineering/src ./src

# Expose port
EXPOSE 8010

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8010"]
