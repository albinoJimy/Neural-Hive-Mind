FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/knowledge-graph-rag/requirements.txt ./requirements-service.txt

# Replace relative path and install dependencies
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY services/knowledge-graph-rag/src/ ./src/

# Copiar arquivos proto compilados do service-registry
COPY --chown=appuser:appuser services/service-registry/src/proto/ ./src/proto/

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Configure PYTHONPATH to allow imports from src/
ENV PYTHONPATH="/app/src:$PYTHONPATH"

USER appuser

# Expor porta
EXPOSE 8016

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8016/health || exit 1

# Comando de启动
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8016"]
