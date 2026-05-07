# Unified Gateway Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar bibliotecas locais primeiro (apenas as necessárias)
# neural_hive_security precisa do setup.py no diretório pai
COPY libraries/security /app/libs/security
COPY libraries/python/neural_hive_observability /app/libs/neural_hive_observability
COPY libraries/python/neural_hive_resilience /app/libs/neural_hive_resilience

# Instalar bibliotecas locais
RUN pip install --no-cache-dir \
    /app/libs/security \
    /app/libs/neural_hive_observability \
    /app/libs/neural_hive_resilience

# Copiar e instalar requirements (sem dependências locais)
COPY services/unified-gateway/requirements.txt .
RUN grep -v "^-e" requirements.txt > requirements-docker.txt || cp requirements.txt requirements-docker.txt
RUN pip install --no-cache-dir -r requirements-docker.txt

# Copiar código fonte
COPY services/unified-gateway/src/ ./src/

# Expor porta
EXPOSE 7999

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7999/health || exit 1

# Comando para iniciar o serviço
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "7999"]
