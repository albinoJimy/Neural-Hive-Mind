# Stage 1: Builder
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.3.0 AS builder

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Criar e ativar virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiar bibliotecas locais primeiro
COPY libraries/python/neural_hive_security /tmp/neural_hive_security
COPY libraries/python/neural_hive_resilience /tmp/neural_hive_resilience
COPY libraries/python/neural_hive_domain /tmp/neural_hive_domain
COPY libraries/neural_hive_integration /tmp/neural_hive_integration

# Copiar requirements e instalar dependências
COPY services/queen-agent/requirements.txt /tmp/requirements-service.txt
COPY requirements-base.txt /tmp/requirements-base.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /tmp/neural_hive_security && \
    pip install --no-cache-dir /tmp/neural_hive_resilience && \
    pip install --no-cache-dir /tmp/neural_hive_domain && \
    pip install --no-cache-dir /tmp/neural_hive_integration && \
    cat /tmp/requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r /tmp/requirements-base.txt|' > /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Stage 2: Runtime - usar mesma base image para ter neural_hive_observability
ARG REGISTRY=ghcr.io/albinojimy
FROM ${REGISTRY}/neural-hive-mind/python-observability-base:1.3.0

# Instalar apenas runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar virtualenv do builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Garantir acesso aos site-packages globais e proto stubs
# Include /app/src/proto for proto imports with absolute imports
ENV PYTHONPATH="/app/src/proto:/usr/local/lib/python3.11/site-packages:$PYTHONPATH"

# Criar usuário não-root
RUN useradd -m -u 1000 -s /bin/bash queen-agent

# Criar diretório de trabalho
WORKDIR /app

# Copiar código fonte
COPY --chown=queen-agent:queen-agent services/queen-agent/src/ /app/src/

# Gerar stubs gRPC (deve executar como root antes de mudar para usuário não-root)
RUN python -m grpc_tools.protoc -I./src/proto --python_out=./src/proto --grpc_python_out=./src/proto --pyi_out=./src/proto ./src/proto/queen_agent.proto && \
    sed -i 's/^import queen_agent_pb2/from . import queen_agent_pb2/' ./src/proto/queen_agent_pb2_grpc.py && \
    chown -R queen-agent:queen-agent /app/src/proto/

# Mudar para usuário não-root
USER queen-agent

# Expor portas
EXPOSE 8000 50053 9090

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização
CMD ["python", "-m", "src.main"]
