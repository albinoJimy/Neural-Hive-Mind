FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro para cache
COPY requirements-base.txt ./requirements-base.txt
COPY services/approval-gateway/requirements.txt ./requirements-service.txt
# Substituir caminho relativo e instalar
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY services/approval-gateway/src/ ./src/

# Copiar arquivos proto compilados do service-registry para top-level
# Isso permite imports como "from proto import service_registry_pb2"
COPY --chown=appuser:appuser services/service-registry/src/proto/ ./proto/

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Configurar PYTHONPATH para permitir imports de src/ e proto/
ENV PYTHONPATH=/app

USER appuser

# Expor porta
EXPOSE 8017

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8017/health || exit 1

# Comando de启动
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8017"]
