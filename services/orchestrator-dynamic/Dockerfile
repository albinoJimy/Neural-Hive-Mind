# Stage 1: Builder
FROM neural-hive-mind/python-observability-base:1.2.2 AS builder

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Criar diretório de trabalho
WORKDIR /build

# Copiar requirements e instalar dependências
COPY services/orchestrator-dynamic/requirements.txt .
# Bibliotecas internas referenciadas via caminhos relativos nos requirements
COPY libraries /libraries
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

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
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Definir PATH para incluir binários do usuário
ENV PATH=/home/orchestrator/.local/bin:$PATH

# Definir diretório de trabalho
WORKDIR /app

# Copiar código fonte
COPY --chown=orchestrator:orchestrator services/orchestrator-dynamic/src/ ./src/

# Proto stubs não precisam mais ser copiados separadamente
# Eles agora estão incluídos no pacote neural_hive_integration.proto_stubs

# Mudar para usuário não-root
USER orchestrator

# Expor portas
EXPOSE 8000 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização (FastAPI + Temporal Worker em processos separados)
# Usando uvicorn para FastAPI e worker em background
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
