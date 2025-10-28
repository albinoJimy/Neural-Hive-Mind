# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements da biblioteca neural_hive_specialists
COPY libraries/python/neural_hive_specialists/requirements.txt /tmp/lib-requirements.txt
RUN pip install --no-cache-dir --user -r /tmp/lib-requirements.txt

# Copiar requirements do serviço
COPY services/specialist-behavior/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Criar usuário não-root
RUN groupadd -r -g 1000 specialist && useradd -r -u 1000 -g specialist specialist

# Copiar dependências do builder
COPY --from=builder /root/.local /home/specialist/.local

# Copiar biblioteca neural_hive_specialists
COPY libraries/python/neural_hive_specialists /app/libraries/python/neural_hive_specialists

# Copiar código da aplicação
COPY services/specialist-behavior/src /app/src

# Ajustar PATH
ENV PATH=/home/specialist/.local/bin:$PATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Mudar para usuário não-root
USER specialist

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

# Labels
LABEL maintainer="Neural Hive-Mind Team"
LABEL component="behavior-specialist"
LABEL layer="cognitiva"
LABEL version="1.0.0"

# Expor portas
EXPOSE 50051 8000 8080

# Comando de execução
CMD ["python", "src/main.py"]
