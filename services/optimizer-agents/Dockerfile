# Stage 1: Builder
FROM neural-hive-mind/python-mlops-base:1.0.0 AS builder

WORKDIR /app

# Instalar dependências específicas do serviço
COPY services/optimizer-agents/requirements-optimizer.txt .
RUN pip install --no-cache-dir --user -r requirements-optimizer.txt

# Copiar proto files e compilar
COPY services/optimizer-agents/src/proto/ ./src/proto/
RUN python -m grpc_tools.protoc \
    -I./src/proto \
    --python_out=./src/proto \
    --grpc_python_out=./src/proto \
    ./src/proto/optimizer_agent.proto

# Stage 2: Runtime
FROM neural-hive-mind/python-mlops-base:1.0.0

WORKDIR /app

# Criar usuário não-root
RUN useradd -m -u 1000 optimizer

# Copiar dependências do builder
COPY --from=builder --chown=optimizer:optimizer /root/.local /home/optimizer/.local

# Copiar código da aplicação
COPY --chown=optimizer:optimizer services/optimizer-agents/src/ ./src/
COPY --from=builder --chown=optimizer:optimizer /app/src/proto/*.py ./src/proto/

# Ajustar PATH e PYTHONPATH
ENV PATH=/home/optimizer/.local/bin:$PATH
ENV PYTHONPATH=/app:$PYTHONPATH

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
LABEL version="1.0.11"
LABEL component="optimizer-agents"
LABEL layer="estrategica"

# Run application
ENTRYPOINT ["python", "-m", "src.main"]
