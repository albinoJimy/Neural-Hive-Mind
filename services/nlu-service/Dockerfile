# Dockerfile para NLU Service
FROM python:3.12-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Instalar spaCy models em cache
RUN python -m pip install --no-cache-dir spacy && \
    python -m spacy download pt_core_news_sm && \
    python -m spacy download en_core_web_sm && \
    python -m spacy download es_core_news_sm && \
    mkdir -p /app/models/spacy && \
    cp -r $(python -c "import spacy; import os; print(os.path.dirname(spacy.__file__))")/pt_core_news_sm /app/models/spacy/ && \
    cp -r $(python -c "import spacy; import os; print(os.path.dirname(spacy.__file__))")/en_core_web_sm /app/models/spacy/ && \
    cp -r $(python -c "import spacy; import os; print(os.path.dirname(spacy.__file__))")/es_core_news_sm /app/models/spacy/

# Copiar projeto
COPY services/nlu-service/pyproject.toml ./
COPY services/nlu-service/src/ ./src/

# Instalar dependências Python
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-root

# Expor portas
EXPOSE 8020 8021

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8020/health')" || exit 1

# Executar
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8020"]
