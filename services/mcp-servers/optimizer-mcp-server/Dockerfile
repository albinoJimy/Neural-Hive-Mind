# Optimizer MCP Server Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY src/ src/

# Expor porta
EXPOSE 3011

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3011/health || exit 1

# Comando de start
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3011"]
