FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/requirements-engineering/requirements.txt services/requirements-engineering/requirements-dev.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy application
COPY services/requirements-engineering/src ./src

# Expose port
EXPOSE 8010

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8010"]
