FROM python:3.12-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY src/ /app/src/

# Instalar kubectl
RUN apt-get update && apt-get install -y curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

# Criar usuário não-root
RUN useradd -m -u 1000 deployer && \
    chown -R deployer:deployer /app
USER deployer

EXPOSE 8010

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8010"]
