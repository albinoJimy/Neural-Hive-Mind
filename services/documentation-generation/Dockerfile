FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/documentation-generation/requirements.txt ./requirements-service.txt

# Replace relative path and install dependencies
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY services/documentation-generation/src ./src

# Expose port
EXPOSE 8012

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8012"]
