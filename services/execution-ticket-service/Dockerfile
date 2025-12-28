# Stage 1: Builder
FROM neural-hive-mind/python-observability-base:1.2.0 AS builder

WORKDIR /build

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências Python
COPY services/execution-ticket-service/requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Instalar apenas dependências de runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar virtualenv do builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
ENV PATH="/opt/venv/bin:$PATH"

# Copiar código fonte
COPY services/execution-ticket-service/src/ ./src/

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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização
CMD ["python", "-m", "src.main"]
