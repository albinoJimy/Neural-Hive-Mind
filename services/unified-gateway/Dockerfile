# Unified Gateway Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro para cache do Docker
# Contexto de build é a raiz do repositório (context: .)
COPY services/unified-gateway/requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

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
