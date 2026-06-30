FROM python:3.12-slim

WORKDIR /app

# Instalar kubectl (o deploy-service shell-out para kubectl)
RUN apt-get update && apt-get install -y curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/ && \
    rm -rf /var/lib/apt/lists/*

# Biblioteca local neural_hive_observability (não está no PyPI)
COPY libraries/python/neural_hive_observability /tmp/neural_hive_observability

# Dependências (contexto de build = raiz do repo). Remove a linha
# neural-hive-observability (satisfeita pela lib local instalada acima).
COPY services/deploy-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir /tmp/neural_hive_observability && \
    grep -v "neural-hive-observability" requirements.txt > req.txt && \
    pip install --no-cache-dir -r req.txt

# Código da aplicação
COPY services/deploy-service/src /app/src

# Usuário não-root
RUN useradd -m -u 1000 deployer && \
    chown -R deployer:deployer /app
USER deployer

EXPOSE 8010

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8010"]
