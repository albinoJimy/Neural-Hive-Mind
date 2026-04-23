FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Criar diretório temporário com permissões corretas
RUN mkdir -p /tmp && chmod 1777 /tmp

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/knowledge-graph-rag/requirements.txt ./requirements-service.txt

# Copy local libraries needed by the service
COPY libraries/neural_hive_integration /tmp/neural_hive_integration
COPY libraries/python/neural_hive_resilience /tmp/neural_hive_resilience

# Replace relative path and install dependencies including local libraries
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir /tmp/neural_hive_integration && \
    pip install --no-cache-dir /tmp/neural_hive_resilience && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY services/knowledge-graph-rag/src/ ./src/

# Copiar arquivos proto compilados do service-registry
COPY services/service-registry/src/proto/ ./src/proto/

# Expor porta
EXPOSE 8016

# Configure PYTHONPATH to find knowledge_graph_rag package
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Run application (main.py is in /app/src/)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8016"]
