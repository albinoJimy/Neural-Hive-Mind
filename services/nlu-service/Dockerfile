# Dockerfile para NLU Service
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar projeto primeiro (para cache do poetry)
COPY services/nlu-service/pyproject.toml ./
COPY services/nlu-service/src/ ./src/

# Instalar dependências Python
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --without dev --no-root

# Instalar spaCy e baixar modelos após as dependências
# Os modelos podem ser carregados diretamente via spacy.load()
RUN pip install --no-cache-dir spacy && \
    pip install --no-cache-dir https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.8.0/pt_core_news_sm-3.8.0-py3-none-any.whl && \
    python -m spacy download en_core_web_sm && \
    python -m spacy download es_core_news_sm

# Expor portas
EXPOSE 8020 8021

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8020/health')" || exit 1

# Executar
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8020"]
