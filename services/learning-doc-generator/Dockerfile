# Stage 1: Builder
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-grpc-base:1.0.7 AS builder

WORKDIR /app

# Instalar dependências
COPY services/learning-doc-generator/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --user -r requirements.txt && \
    echo "✓ Dependencies installed"

# Stage 2: Runtime
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-grpc-base:1.0.7

WORKDIR /app

# Criar usuário não-root
RUN useradd -m -u 1000 docgen

# Copiar dependências do builder
COPY --from=builder --chown=docgen:docgen /root/.local /home/docgen/.local

# Copiar biblioteca de observabilidade
COPY --chown=docgen:docgen libraries/python/neural_hive_observability/neural_hive_observability /app/neural_hive_observability

# ARG para invalidar cache
ARG CACHE_BUST=1
RUN echo "Cache bust: ${CACHE_BUST}"

# Copiar código da aplicação
COPY --chown=docgen:docgen services/learning-doc-generator/src /app/src

# Criar diretório para templates e output
RUN mkdir -p /app/templates /app/output && \
    chown -R docgen:docgen /app/templates /app/output

# Environment variables
ENV PYTHONPATH=/app:/home/docgen/.local/lib/python3.11/site-packages \
    PYTHONUNBUFFERED=1 \
    PATH=/home/docgen/.local/bin:$PATH \
    MPLBACKEND=Agg

USER docgen

# Expose ports
EXPOSE 8009 8089

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8009/health || exit 1

# Labels
LABEL maintainer="Neural Hive-Mind Team <team@neural-hive-mind.org>" \
      version="1.0.0" \
      component="learning-doc-generator" \
      layer="observability" \
      description="Learning Documentation Generator - Neural Hive-Mind"

# Start application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8009", "--workers", "1"]
