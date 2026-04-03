# Guard MCP Server Dockerfile
# Multi-stage build para imagem otimizada
#
# Build context: services/mcp-servers/
# Build command: docker build -f guard-mcp-server/Dockerfile .

# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /build

# Instalar dependências de build e curl para health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Criar virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiar e instalar dependências
COPY guard-mcp-server/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime
FROM python:3.12-slim

# Instalar curl para health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar virtualenv do builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Criar usuário não-root
RUN useradd --create-home --shell /bin/bash guard-mcp-user

WORKDIR /app

# Copiar módulo shared (do contexto pai services/mcp-servers/)
COPY --chown=guard-mcp-user:guard-mcp-user shared /app/shared

# Copiar código da aplicação
COPY --chown=guard-mcp-user:guard-mcp-user guard-mcp-server/src /app/src
COPY --chown=guard-mcp-user:guard-mcp-user guard-mcp-server/requirements.txt /app/

# Trocar para usuário não-root
USER guard-mcp-user

# Portas: HTTP (3014)
EXPOSE 3014

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3014/health || exit 1

# Executar servidor FastAPI
CMD ["uvicorn", "guard_mcp_server.app:app", "--host", "0.0.0.0", "--port", "3014"]
