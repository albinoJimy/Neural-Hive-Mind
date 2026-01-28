# Stage 1: Builder
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-mlops-base:1.0.7 AS builder

WORKDIR /app

# Copiar e instalar bibliotecas internas
COPY libraries/python/neural_hive_ml /tmp/neural_hive_ml
COPY libraries/python/neural_hive_observability /tmp/neural_hive_observability
COPY libraries/python/neural_hive_resilience /tmp/neural_hive_resilience
COPY libraries/neural_hive_integration /tmp/neural_hive_integration

# Instalar dependências específicas do serviço
COPY services/optimizer-agents/requirements-optimizer.txt .
RUN pip config set global.timeout 600 && \
    pip config set global.retries 5 && \
    pip install --no-cache-dir --user /tmp/neural_hive_ml && \
    pip install --no-cache-dir --user /tmp/neural_hive_observability && \
    pip install --no-cache-dir --user /tmp/neural_hive_resilience && \
    pip install --no-cache-dir --user /tmp/neural_hive_integration && \
    pip install --no-cache-dir --user -r requirements-optimizer.txt

# Proto files já compilados no source com imports relativos corretos

# Stage 2: Runtime
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-mlops-base:1.0.7

WORKDIR /app

# Criar usuário não-root
RUN useradd -m -u 1000 optimizer

# Copiar dependências do builder
COPY --from=builder --chown=optimizer:optimizer /root/.local /home/optimizer/.local

# Fix pydantic-settings conflict - remove old versions and install correct ones
RUN rm -rf /home/optimizer/.local/lib/python3.11/site-packages/pydantic* && \
    rm -rf /usr/local/lib/python3.11/site-packages/pydantic* 2>/dev/null || true && \
    pip install --no-cache-dir --target=/home/optimizer/.local/lib/python3.11/site-packages \
        pydantic==2.10.4 pydantic-settings==2.6.1

# Copiar código da aplicação (proto files já têm imports relativos corretos)
COPY --chown=optimizer:optimizer services/optimizer-agents/src/ ./src/

# Ajustar PATH e PYTHONPATH
ENV PATH=/home/optimizer/.local/bin:$PATH
ENV PYTHONPATH=/home/optimizer/.local/lib/python3.11/site-packages:/app

# Mudar para usuário não-root
USER optimizer

# Expose ports
EXPOSE 50051 8080 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Labels
LABEL maintainer="Neural Hive-Mind Team <team@neuralhivemind.io>"
LABEL description="Optimizer Agents - Continuous Improvement and Policy Recalibration"
LABEL version="1.0.14"
LABEL component="optimizer-agents"
LABEL layer="estrategica"

# Run application
ENTRYPOINT ["python", "-m", "src.main"]
