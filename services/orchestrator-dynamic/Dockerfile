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

# Copiar bibliotecas internas e instalar como editable
# CACHE-BUSTER: 249812b
COPY libraries /libraries
ARG LIBRARY_VERSION=249812b
RUN echo "Library version: ${LIBRARY_VERSION}"
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --user -e /libraries/python/neural_hive_ml && \
    pip install --no-cache-dir --user /libraries/python/neural_hive_security && \
    pip install --no-cache-dir --user /libraries/python/neural_hive_resilience && \
    pip install --no-cache-dir --user /libraries/neural_hive_integration && \
    pip install --no-cache-dir --user --force-reinstall --no-deps /libraries/python/neural_hive_observability

# Copiar requirements (base + service-specific) e resolver path relativo no Docker context
# Padrão consistente com data-migration, code-forge, etc.
COPY requirements-base.txt ./requirements-base.txt
COPY services/orchestrator-dynamic/requirements.txt ./requirements-service.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
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
# libsnappy1v5: necessário para python-snappy descomprimir mensagens Kafka (Ubuntu 24.04)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libsnappy1v5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Criar usuário não-root para segurança
RUN groupadd -r orchestrator && useradd -r -g orchestrator -u 1000 orchestrator

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/tmp && chown -R orchestrator:orchestrator /app

# Copiar dependências instaladas do builder
COPY --from=builder --chown=orchestrator:orchestrator /root/.local /home/orchestrator/.local

# Substituir a versão STALE de neural_hive_observability na base image (/usr/local).
# CRÍTICO: o PYTHONPATH de runtime é definido pelo deployment como
# "/app/libs:/usr/local/lib/python3.11/site-packages" (NÃO inclui ~/.local), por isso a
# app importa o middleware de /usr/local — é AÍ que a correção tem de estar.
# A base python-observability-base:1.2.6 (anterior ao fix 3ebaec41) traz a versão antiga
# do TraceContextMiddleware, que crasha cada request com "'property' object has no
# attribute 'trace_context_extraction_total'". `pip --force-reinstall` é no-op silencioso
# se o dir já existe; é preciso remover a árvore stale antes de reinstalar.
COPY libraries/python/neural_hive_observability /tmp/neural_hive_observability
RUN rm -rf /usr/local/lib/python3.11/site-packages/neural_hive_observability \
           /usr/local/lib/python3.11/site-packages/neural_hive_observability-*.dist-info \
           /usr/local/lib/python3.11/site-packages/neural_hive_observability-*.egg-info && \
    pip install --no-cache-dir --no-deps --target=/usr/local/lib/python3.11/site-packages /tmp/neural_hive_observability && \
    rm -rf /tmp/neural_hive_observability && \
    python -c "import neural_hive_observability.middleware as m; import inspect; assert 'AttributeError' in inspect.getsource(m), 'fix do middleware ausente em /usr/local'; print('Middleware fix verified in', m.__file__)"

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

