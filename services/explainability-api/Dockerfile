# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Instalar dependências de build
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY services/explainability-api/requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Criar usuário não-root
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copiar dependências do builder
COPY --from=builder /root/.local /home/appuser/.local

# Copiar bibliotecas compartilhadas
COPY --chown=appuser:appuser libraries/python/neural_hive_observability /app/libraries/neural_hive_observability
COPY --chown=appuser:appuser libraries/python/neural_hive_specialists /app/libraries/neural_hive_specialists

# Copiar código da aplicação
COPY --chown=appuser:appuser services/explainability-api/src /app/src

# Configurar PATH para incluir binários do usuário
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app

# Expor portas
EXPOSE 8000 8080

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Labels
LABEL maintainer="Neural Hive-Mind Team"
LABEL version="1.0.0"
LABEL description="Explainability API - Neural Hive-Mind"
LABEL component="explainability-api"

# Trocar para usuário não-root
USER appuser

# Comando para iniciar a aplicação
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
