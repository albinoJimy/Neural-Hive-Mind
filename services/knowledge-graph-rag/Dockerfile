FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Criar diretório temporário com permissões corretas (fix portalocker/qdrant_client)
RUN mkdir -p /tmp && chmod 1777 /tmp

# Copy requirements-base.txt first (required by service requirements)
COPY requirements-base.txt ./requirements-base.txt
COPY services/knowledge-graph-rag/requirements.txt ./requirements-service.txt

# Copy local libraries needed by the service (use /opt/build to avoid /tmp conflicts)
COPY libraries/neural_hive_integration /opt/build/neural_hive_integration
COPY libraries/python/neural_hive_resilience /opt/build/neural_hive_resilience
COPY libraries/python/neural_hive_llm /opt/build/neural_hive_llm

# Replace relative path and install dependencies including local libraries
RUN cat requirements-service.txt | sed 's|-r ../../requirements-base.txt|-r requirements-base.txt|' > requirements.txt && \
    pip install --no-cache-dir /opt/build/neural_hive_integration && \
    pip install --no-cache-dir /opt/build/neural_hive_resilience && \
    pip install --no-cache-dir /opt/build/neural_hive_llm && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY services/knowledge-graph-rag/src/ ./src/

# Copiar arquivos proto compilados do service-registry
COPY services/service-registry/src/proto/ ./src/proto/

# Expor porta
EXPOSE 8016

# Configure PYTHONPATH to find knowledge_graph_rag package
ENV PYTHONPATH="/app/src:$PYTHONPATH"
ENV TMPDIR="/app/tmp"

# Create entrypoint script to ensure /tmp exists at runtime
RUN echo '#!/bin/bash\n\
mkdir -p /tmp /app/tmp\n\
chmod 1777 /tmp /app/tmp\n\
exec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8016"]
