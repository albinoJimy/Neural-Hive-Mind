FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/fluxo-g-dashboard/requirements.txt ./requirements-service.txt

# Replace relative path and install dependencies
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY services/fluxo-g-dashboard/src/ ./src/

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Set PYTHONPATH
ENV PYTHONPATH=/app

USER appuser

# Expor porta
EXPOSE 8021

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8021/health || exit 1

# Comando de启动
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8021"]
