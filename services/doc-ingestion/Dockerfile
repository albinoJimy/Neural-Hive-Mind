FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for PDF/Word/Visio parsing
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    poppler-utils \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/doc-ingestion/requirements.txt services/doc-ingestion/requirements-dev.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY services/doc-ingestion/src ./src

# Expose port
EXPOSE 8018

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8018"]
