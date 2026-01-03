FROM neural-hive-mind/python-specialist-base:1.0.7

WORKDIR /app

# Criar usuário não-root
RUN groupadd -r -g 1000 specialist && useradd -r -u 1000 -g specialist specialist

# Criar diretórios com permissões corretas
RUN mkdir -p /home/specialist/.cache /home/specialist/.local \
    && chown -R specialist:specialist /home/specialist

# Verificar que modelos da base image estão acessíveis
RUN python -c "import spacy; nlp = spacy.load('pt_core_news_sm'); print('✓ Base models accessible')"

# Copiar código da aplicação
COPY services/specialist-technical/src /app/src

# Ajustar PATH e PYTHONPATH
ENV PATH=/home/specialist/.local/bin:$PATH
ENV PYTHONPATH=/app/src:/app:$PYTHONPATH

# Mudar para usuário não-root
USER specialist

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

# Labels
LABEL maintainer="Neural Hive-Mind Team"
LABEL component="technical-specialist"
LABEL layer="cognitiva"
LABEL version="1.0.11"

# Expor portas
EXPOSE 50051 8000 8080

# Comando de execução
CMD ["python", "src/main.py"]
