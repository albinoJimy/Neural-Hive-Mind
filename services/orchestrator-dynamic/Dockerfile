# Stage 1: Builder
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.2.6 AS builder

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Criar diretório de trabalho
WORKDIR /build

# Cache buster para forçar rebuild quando neural_hive_integration mudar
ARG LIBRARY_VERSION=03339c8

# Copiar bibliotecas internas e instalar neural_hive_ml como editable
COPY libraries /libraries
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --user -e /libraries/python/neural_hive_ml

# Copiar requirements e instalar dependências restantes
COPY services/orchestrator-dynamic/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --user -r requirements.txt \
    --default-timeout=900 --retries 3

# Stage 2: Runtime - usar mesma base para manter neural_hive_observability
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.2.6

# Metadados OCI para rastreabilidade
LABEL org.opencontainers.image.title="Orchestrator Dynamic"
LABEL org.opencontainers.image.description="Orquestrador Dinâmico do Neural Hive-Mind usando Temporal"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.vendor="Neural Hive-Mind"
LABEL neural-hive.layer="orchestration"
LABEL neural-hive.component="orchestrator-dynamic"

# Instalar apenas dependências de runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Criar usuário não-root para segurança
RUN groupadd -r orchestrator && useradd -r -g orchestrator -u 1000 orchestrator

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/tmp && chown -R orchestrator:orchestrator /app

# Copiar dependências instaladas do builder
COPY --from=builder --chown=orchestrator:orchestrator /root/.local /home/orchestrator/.local

# Definir PATH e PYTHONPATH para incluir user packages e base image packages
ENV PATH=/home/orchestrator/.local/bin:$PATH
ENV PYTHONPATH=/home/orchestrator/.local/lib/python3.11/site-packages:/usr/local/lib/python3.11/site-packages:/app

# Definir diretório de trabalho
WORKDIR /app

# Copiar código fonte
COPY --chown=orchestrator:orchestrator services/orchestrator-dynamic/src/ ./src/

# Copiar scripts de treinamento ML
COPY --chown=orchestrator:orchestrator services/orchestrator-dynamic/scripts/ ./scripts/

# Proto stubs não precisam mais ser copiados separadamente
# Eles agora estão incluídos no pacote neural_hive_integration.proto_stubs

# Mudar para usuário não-root
USER orchestrator

# Expor portas (HTTP, Prometheus, gRPC)
EXPOSE 8000 9090 50053

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização (FastAPI + Temporal Worker em processos separados)
# Usando uvicorn para FastAPI e worker em background
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]

# CI/CD Cache Buster - 1771283618
# Force rebuild to include logger fixes

