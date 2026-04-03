# Analyst MCP Server Dockerfile
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
COPY src/analyst_mcp_server /app/src/analyst_mcp_server

# Set PYTHONPATH
ENV PYTHONPATH=/app/src

# Expor porta (se necessário para health checks)
EXPOSE 8000

# Entry point
CMD ["python", "-m", "analyst_mcp_server"]
