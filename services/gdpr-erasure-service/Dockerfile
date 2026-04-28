FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar codigo
COPY src/ ./src/

# Criar usuario nao-root
RUN useradd -m -u 1000 nhm && chown -R nhm:nhm /app
USER nhm

# Expor porta
EXPOSE 8010

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8010/api/v1/health')" || exit 1

# Comando
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8010"]
