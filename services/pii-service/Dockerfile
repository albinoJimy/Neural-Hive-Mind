# PII Service Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar bibliotecas locais primeiro
COPY libraries/security /app/libs/security
COPY libraries/python/neural_hive_observability /app/libs/neural_hive_observability
COPY libraries/python/neural_hive_specialists /app/libs/neural_hive_specialists

# Instalar bibliotecas locais
RUN pip install --no-cache-dir \
    /app/libs/security \
    /app/libs/neural_hive_observability \
    /app/libs/neural_hive_specialists

# Copiar e instalar requirements (sem dependências locais)
COPY services/pii-service/requirements.txt .
RUN grep -v "^-e" requirements.txt > requirements-docker.txt || cp requirements.txt requirements-docker.txt
RUN pip install --no-cache-dir -r requirements-docker.txt

# Compilar arquivos protobuf
COPY services/pii-service/src/proto/*.proto .
RUN python -m grpc_tools.protoc \
    --proto_path=. \
    --python_out=. \
    --grpc_python_out=. \
    pii.proto

# Mover arquivos gerados para o local correto
RUN mkdir -p src/proto && mv pii*_pb2*.py src/proto/

# Copiar código da aplicação
COPY services/pii-service/src/ src/

# Criar usuário não-root
RUN useradd -m -u 1000 piiuser && chown -R piiuser:piiuser /app
USER piiuser

# Expor portas
EXPOSE 8021 9021

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8021/health')"

# Executar aplicação
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8021"]
