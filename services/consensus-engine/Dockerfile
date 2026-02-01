# Stage 1: Builder
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-grpc-base:1.0.7 AS builder

WORKDIR /app

# Copy internal library for installation
COPY libraries/python/neural_hive_domain /tmp/neural_hive_domain

# Instalar dependências e biblioteca interna
COPY services/consensus-engine/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --user /tmp/neural_hive_domain && \
    pip install --no-cache-dir --user -r requirements.txt && \
    python -m uvicorn --version && \
    echo "✓ uvicorn runtime verification passed"

# Stage 2: Runtime
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-grpc-base:1.0.7

WORKDIR /app

# Criar usuário não-root
RUN useradd -m -u 1000 consensus

# Copiar dependências do builder
COPY --from=builder --chown=consensus:consensus /root/.local /home/consensus/.local

# Copiar biblioteca de observabilidade (copiada directamente porque não é instalável via pip)
COPY --chown=consensus:consensus libraries/python/neural_hive_observability/neural_hive_observability /app/neural_hive_observability

# Copiar proto_gen da biblioteca neural_hive_specialists (apenas stubs gRPC necessários)
COPY --chown=consensus:consensus libraries/python/neural_hive_specialists/proto_gen /app/neural_hive_specialists/proto_gen
# Criar __init__.py mínimo para expor apenas proto_gen (evita dependências pesadas)
RUN echo '"""neural_hive_specialists stub for consensus-engine - only proto_gen needed"""' > /app/neural_hive_specialists/__init__.py && \
    chown consensus:consensus /app/neural_hive_specialists/__init__.py

# ARG para invalidar cache (passado pelo CI/CD)
ARG CACHE_BUST=1
# Usar ARG em RUN força invalidação do cache a partir deste ponto
RUN echo "Cache bust: ${CACHE_BUST}"

# Copiar código da aplicação
COPY --chown=consensus:consensus services/consensus-engine/src /app/src

# Garantir diretórios de schemas
RUN mkdir -p /app/schemas/cognitive-plan /app/schemas/consolidated-decision && \
    chown -R consensus:consensus /app/schemas

# Copiar Avro schemas
COPY --chown=consensus:consensus schemas/cognitive-plan/cognitive-plan.avsc /app/schemas/cognitive-plan/cognitive-plan.avsc
COPY --chown=consensus:consensus schemas/consolidated-decision/consolidated-decision.avsc /app/schemas/consolidated-decision/consolidated-decision.avsc

# Environment variables
# Include /app/src/proto for proto imports to work with absolute imports
ENV PYTHONPATH=/app:/app/src/proto:/app/neural_hive_specialists:/home/consensus/.local/lib/python3.11/site-packages \
    PYTHONUNBUFFERED=1 \
    PATH=/home/consensus/.local/bin:$PATH

USER consensus

# Expose ports
EXPOSE 8000 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Labels
LABEL maintainer="Neural Hive-Mind Team <team@neural-hive-mind.org>" \
      version="1.0.11" \
      component="consensus-aggregator" \
      layer="cognitiva" \
      description="Mecanismo de Consenso Multi-Agente - Neural Hive-Mind"

# Start application
# Using 1 worker to avoid race conditions in startup (MongoDB indexes, Kafka consumer group)
# For production with multiple replicas, use 1 worker per pod and scale horizontally
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
# Force rebuild Sun Feb  1 15:44:17 WAT 2026
