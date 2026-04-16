# Documentation Generation Service Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar Poetry
RUN pip install poetry

# Copiar ficheiros de dependência
COPY pyproject.toml ./

# Configurar Poetry para não criar ambiente virtual
RUN poetry config virtualenvs.create false

# Instalar dependências
RUN poetry install --no-dev --no-interaction --no-ansi

# Copiar código fonte
COPY src/ ./src/

# Expor porta
EXPOSE 8014

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8014/health || exit 1

# Executar
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8014"]
