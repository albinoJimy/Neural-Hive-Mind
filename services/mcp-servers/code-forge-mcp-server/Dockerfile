# Code Forge MCP Server Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro para cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY src/code_forge_mcp_server /app/src/code_forge_mcp_server

# Set PYTHONPATH
ENV PYTHONPATH=/app/src

# Expor porta
EXPOSE 3018

# Entry point
CMD ["python", "-m", "code_forge_mcp_server"]
