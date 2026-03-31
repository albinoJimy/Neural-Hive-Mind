# =============================================================================
# Neural Hive-Mind Python Base Image (Unificado)
# =============================================================================
# Imagem base unificada para todos os serviços Python da plataforma.
# Consolida: python-nlp-base, python-grpc-base, python-observability-base
#
# Versão: 2.0.0
# Python: 3.12-slim
# =============================================================================

FROM python:3.12-slim

# Build arguments
ARG VERSION=2.0.0
ARG BUILD_DATE
ARG REGISTRY=ghcr.io/albinojimy

# Labels
LABEL org.opencontainers.image.title="Neural Hive-Mind Python Base"
LABEL org.opencontainers.image.description="Unified base image for Neural Hive-Mind Python services"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL neural-hive-mind.org/component="python-base"
LABEL neural-hive-mind.org.python-version="3.12"

# Metadados
LABEL maintainer="Neural Hive-Mind Team"
LABEL org.opencontainers.image.source="https://github.com/albinoJimy/Neural-Hive-Mind"

# Configurações de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Instalar em modo usuário para evitar conflitos
    PIP_USER=1 \
    # Adicionar user bin to PATH
    PATH="${PATH}:/root/.local/bin"

# Workdir
WORKDIR /app

# ============================================================================
# DEPENDÊNCIAS BASE (Consolidadas)
# ============================================================================

# Dependências do sistema para compilação de pacotes Python
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libc-dev \
        libpq-dev \
        libssl-dev \
        libffi-dev \
        curl \
        && rm -rf /var/lib/apt/lists/*

# ============================================================================
# PACOTES PYTHON PRINCIPAIS (Versões Normalizadas)
# ============================================================================

# OpenTelemetry (normalizado v1.29.0)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    opentelemetry-api==1.29.0 \
    opentelemetry-sdk==1.29.0 \
    opentelemetry-exporter-otlp-proto-grpc==1.29.0 \
    opentelemetry-exporter-otlp-proto-common==1.29.0 \
    opentelemetry-proto==1.29.0 \
    opentelemetry-instrumentation==0.50b0 \
    opentelemetry-instrumentation-grpc==0.50b0

# gRPC e Protobuf (normalizado v1.68.1)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    grpcio==1.68.1 \
    grpcio-tools==1.68.1 \
    grpcio-health-checking==1.68.1 \
    protobuf==5.29.2

# FastAPI e dependências web
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn[standard]>=0.32.0 \
    pydantic>=2.10.0 \
    pydantic-settings>=2.6.0

# Structlog para logging estruturado
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    structlog>=24.4.0

# Kafka client
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    aiokafka>=0.12.0

# Prometheus metrics
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    prometheus-client>=0.21.0

# Outras dependências comuns
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    aiohttp>=3.10.0 \
    python-multipart>=0.0.20 \
    requests>=2.32.0

# ============================================================================
# BIBLIOTECAS NEURAL HIVE-MIND (Instaladas em camada separada)
# ============================================================================

# neural_hive_domain (domínio partilhado)
COPY libraries/python/neural_hive_domain /tmp/neural_hive_domain
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/neural_hive_domain && \
    rm -rf /tmp/neural_hive_domain

# neural_hive_exceptions (exceções centralizadas)
COPY libraries/python/neural_hive_exceptions /tmp/neural_hive_exceptions
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/neural_hive_exceptions && \
    rm -rf /tmp/neural_hive_exceptions

# neural_hive_infrastructure (configurações base)
COPY libraries/python/neural_hive_infrastructure /tmp/neural_hive_infrastructure
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/neural_hive_infrastructure && \
    rm -rf /tmp/neural_hive_infrastructure

# neural_hive_observability (logging, metrics, tracing)
COPY libraries/python/neural_hive_observability /tmp/neural_hive_observability
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir /tmp/neural_hive_observability && \
    rm -rf /tmp/neural_hive_observability

# neural_hive_resilience (circuit breakers, retries)
COPY libraries/python/neural_hive_resilience /tmp/neural_hive_resilience
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -f "/tmp/neural_hive_resilience/requirements.txt" ]; then \
        pip install --no-cache-dir -r /tmp/neural_hive_resilience/requirements.txt; \
    fi && \
    pip install --no-cache-dir /tmp/neural_hive_resilience && \
    rm -rf /tmp/neural_hive_resilience

# ============================================================================
# CLEANUP
# ============================================================================

# Limpar cache pip para reduzir tamanho da imagem final
RUN rm -rf /root/.cache/pip /tmp/*

# ============================================================================
# HEALTH CHECK
# =============================================================================

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# ============================================================================
# DEFAULTS
# =============================================================================

# Portas comuns (serviços devem sobrescrever)
EXPOSE 8000 50051 9090

# Comando padrão (serviços devem sobrescrever)
CMD ["python", "-m", "pytest", "--version"]
