# PII Service Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Compilar arquivos protobuf
COPY src/proto/*.proto .
RUN python -m grpc_tools.protoc \
    --proto_path=. \
    --python_out=. \
    --grpc_python_out=. \
    pii.proto

# Mover arquivos gerados para o local correto
RUN mkdir -p src/proto && mv pii*_pb2*.py src/proto/

# Copiar código da aplicação
COPY src/ src/

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
