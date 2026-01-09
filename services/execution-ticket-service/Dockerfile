# Single stage build using observability base
FROM 37.60.241.150:30500/python-observability-base:1.2.2

WORKDIR /app

# Instalar dependências de build e runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências Python diretamente no sistema
COPY services/execution-ticket-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY services/execution-ticket-service/src/ ./src/

# Copiar modelos compartilhados do orchestrator-dynamic (dependência do models/__init__.py)
RUN mkdir -p /orchestrator-dynamic/src/models
COPY services/orchestrator-dynamic/src/models/execution_ticket.py /orchestrator-dynamic/src/models/

# Criar usuário não-root
RUN useradd -m -u 1000 ticketservice && \
    chown -R ticketservice:ticketservice /app
USER ticketservice

# Expor portas
EXPOSE 8000 50052 9090

# Labels
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown
ARG VERSION=1.0.0

LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.authors="Neural Hive-Mind Team" \
      org.opencontainers.image.url="https://github.com/neural-hive-mind/execution-ticket-service" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.title="Execution Ticket Service" \
      org.opencontainers.image.description="Serviço de gerenciamento de ciclo de vida de tickets de execução"

# Health check (start-period aumentado para permitir retry logic com exponential backoff)
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização
CMD ["python", "-m", "src.main"]
