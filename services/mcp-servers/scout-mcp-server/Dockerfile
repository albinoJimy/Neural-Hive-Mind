# Scout MCP Server Dockerfile
# Multi-stage build para imagem otimizada
#
# Build context: services/mcp-servers/
# Build command: docker build -f scout-mcp-server/Dockerfile .

# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /build

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Criar virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiar e instalar dependências
COPY scout-mcp-server/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime
FROM python:3.12-slim

# Copiar virtualenv do builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Criar usuário não-root
RUN useradd --create-home --shell /bin/bash scout-mcp-user

WORKDIR /app

# Copiar módulo shared (do contexto pai services/mcp-servers/)
COPY --chown=scout-mcp-user:scout-mcp-user shared /app/shared

# Copiar código da aplicação
COPY --chown=scout-mcp-user:scout-mcp-user scout-mcp-server/src /app/src
COPY --chown=scout-mcp-user:scout-mcp-user scout-mcp-server/requirements.txt /app/

# Trocar para usuário não-root
USER scout-mcp-user

# Portas: HTTP (3010)
EXPOSE 3010

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3010/health || exit 1

# Executar servidor
CMD ["python", "-m", "src.main"]
