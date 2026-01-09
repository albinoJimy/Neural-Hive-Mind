# Stage 1: Builder
FROM neural-hive-mind/python-observability-base:1.2.3 AS builder

WORKDIR /build

# Instalar dependências de build
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY services/explainability-api/requirements.txt .

# Instalar dependências Python (filtrando as já presentes na base image)
RUN grep -vE "neural_hive_observability|opentelemetry-|prometheus-client|structlog|pydantic" requirements.txt > requirements-filtered.txt && \
    pip install --no-cache-dir --user -r requirements-filtered.txt

# Stage 2: Runtime (herda da base de observabilidade com todos os pacotes)
FROM neural-hive-mind/python-observability-base:1.2.3

WORKDIR /app

# Criar usuário não-root com UID 1000 (compatível com K8s securityContext)
RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -m appuser

# Copiar dependências do builder (apenas as extras não presentes na base)
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Copiar código da aplicação
COPY --chown=appuser:appuser services/explainability-api/src /app/src

# Configurar PATH e PYTHONPATH para incluir pacotes do usuário
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/home/appuser/.local/lib/python3.11/site-packages:/app

# Expor portas
EXPOSE 8000 8080

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Labels
LABEL maintainer="Neural Hive-Mind Team"
LABEL version="1.0.0"
LABEL description="Explainability API - Neural Hive-Mind"
LABEL component="explainability-api"

# Trocar para usuário não-root
USER appuser

# Comando para iniciar a aplicação (usando python -m para evitar problemas de permissão)
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
