FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/test-generation/requirements.txt ./requirements-service.txt

# Copy local libraries needed by the service
COPY libraries/python/neural_hive_integration /tmp/neural_hive_integration
COPY libraries/python/neural_hive_resilience /tmp/neural_hive_resilience

# Replace relative path and install dependencies including local libraries
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir /tmp/neural_hive_integration && \
    pip install --no-cache-dir /tmp/neural_hive_resilience && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY services/test-generation/src/ ./src/

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expor porta
EXPOSE 8013

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8013/health || exit 1

# Comando de启动
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8013"]
