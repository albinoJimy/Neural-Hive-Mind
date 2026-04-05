# Single stage build usando observability base
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.2.6

WORKDIR /app

# Instalar dependências de build e runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY src/ ./src/

# Criar diretório para modelos ML
RUN mkdir -p /app/ml_models && \
    chmod 755 /app/ml_models

# Criar usuário não-root
RUN useradd -m -u 1000 mlinference && \
    chown -R mlinference:mlinference /app
USER mlinference

# Expor portas
EXPOSE 8010 9091

# Labels
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown
ARG VERSION=1.0.0

LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.authors="Neural Hive-Mind Team" \
      org.opencontainers.image.url="https://github.com/neural-hive-mind/ml-inference-api" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.title="ML Inference API" \
      org.opencontainers.image.description="API de inferência ML para predição de aprovação de planos cognitivos"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8010/health || exit 1

# Comando de inicialização
CMD ["python", "-m", "src.main"]
