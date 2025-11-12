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
# Baixar Whisper primeiro (vai para /root/.cache/whisper)
RUN python -c "import whisper; whisper.load_model('base')" && \
    python -m pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.8.0/pt_core_news_sm-3.8.0-py3-none-any.whl \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl \
    && python -c "import pt_core_news_sm; import en_core_web_sm; print('✓ Modelos spaCy instalados')"

# Copiar código da aplicação
COPY services/gateway-intencoes/src/ ./src/

# Criar diretórios necessários primeiro (incluindo cache para Whisper e config para NLU)
RUN mkdir -p /app/logs /app/temp /app/models /app/schemas /app/.cache /app/config && \
    cp -r /root/.cache/whisper /app/.cache/ 2>/dev/null || true

# Copiar schema Avro (caminho relativo ao contexto de build)
COPY schemas/intent-envelope/intent-envelope.avsc /app/schemas/intent-envelope.avsc

# Copiar arquivo de regras NLU
COPY services/gateway-intencoes/config/nlu_rules.yaml /app/config/nlu_rules.yaml

# Ajustar permissões
RUN chown -R appuser:appgroup /app

# Configurar permissões de segurança
# Diretórios precisam de 755 (rx), arquivos 644 (r)
# .cache precisa de 775 (rwx) para Whisper criar subdirectórios
RUN find /app -type d -exec chmod 755 {} \; && \
    find /app -type f -exec chmod 644 {} \; && \
    chmod +x /app/src/main.py && \
    chmod 775 /app/.cache

# Configurações de segurança
USER appuser

# Variáveis de ambiente
ENV PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR="/app/temp" \
    HOME="/app" \
    XDG_CACHE_HOME="/app/.cache"

# Definir working directory para /app/src para que uvicorn encontre main.py
WORKDIR /app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expor porta
EXPOSE 8000

# Comando padrão
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]