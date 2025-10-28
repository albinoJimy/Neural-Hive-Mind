# Gateway de Intenções - Neural Hive-Mind
FROM python:3.11-slim

# Definir versão e metadados
ARG VERSION=1.0.0
ARG BUILD_DATE
ARG VCS_REF

LABEL org.opencontainers.image.title="Gateway de Intenções - Neural Hive-Mind" \
      org.opencontainers.image.description="Gateway para captura e processamento de intenções" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Neural Hive-Mind" \
      org.opencontainers.image.source="https://github.com/neural-hive-mind/infrastructure" \
      neural-hive-mind.org/component="gateway-intencoes" \
      neural-hive-mind.org/layer="application"

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libasound2-dev \
    portaudio19-dev \
    ffmpeg \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Criar usuário não-root
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1001 appuser

# Definir diretório de trabalho
WORKDIR /app

# Copiar requirements e instalar dependências Python
COPY services/gateway-intencoes/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==24.0 && \
    pip install --no-cache-dir -r requirements.txt

# Download de modelos ML (Whisper e spaCy)
RUN python -c "import whisper; whisper.load_model('base')" && \
    python -c "import spacy; spacy.download('pt_core_news_sm')" && \
    python -c "import spacy; spacy.download('en_core_web_sm')"

# Copiar código da aplicação
COPY services/gateway-intencoes/src/ ./src/

# Criar diretórios necessários primeiro
RUN mkdir -p /app/logs /app/temp /app/models /app/schemas

# Copiar schema Avro (caminho relativo ao contexto de build)
COPY schemas/intent-envelope/intent-envelope.avsc /app/schemas/intent-envelope.avsc

# Ajustar permissões
RUN chown -R appuser:appgroup /app

# Configurar permissões de segurança
RUN chmod -R 755 /app && \
    chmod -R 644 /app/src && \
    chmod +x /app/src/main.py

# Configurações de segurança
USER appuser

# Variáveis de ambiente
ENV PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR="/app/temp"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expor porta
EXPOSE 8000

# Comando padrão
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]