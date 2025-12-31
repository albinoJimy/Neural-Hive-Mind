# Trivy MCP Server Dockerfile
# Multi-stage build para imagem otimizada
#
# Build context: services/mcp-servers/
# Build command: docker build -f trivy-mcp-server/Dockerfile .

# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Criar virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiar e instalar dependências
COPY trivy-mcp-server/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Runtime
FROM python:3.11-slim

# Instalar Trivy CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin v0.48.3 \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copiar virtualenv do builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Criar usuário não-root
RUN useradd --create-home --shell /bin/bash trivy-mcp-user

WORKDIR /app

# Copiar módulo shared (do contexto pai services/mcp-servers/)
COPY --chown=trivy-mcp-user:trivy-mcp-user shared /app/shared

# Copiar código da aplicação
COPY --chown=trivy-mcp-user:trivy-mcp-user trivy-mcp-server/src /app/src
COPY --chown=trivy-mcp-user:trivy-mcp-user trivy-mcp-server/requirements.txt /app/

# Criar diretório de cache do Trivy
RUN mkdir -p /tmp/trivy-cache && chown trivy-mcp-user:trivy-mcp-user /tmp/trivy-cache

# Trocar para usuário não-root
USER trivy-mcp-user

# Portas: HTTP (3000) e Metrics (9091)
EXPOSE 3000 9091

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Executar servidor
CMD ["python", "-m", "src.main"]
