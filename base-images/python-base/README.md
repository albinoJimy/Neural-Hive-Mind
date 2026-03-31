# Neural Hive-Mind Python Base Image

Imagem base Docker unificada para todos os serviços Python da plataforma Neural Hive-Mind.

## Características

- **Python 3.12-slim** - Versão mais recente e otimizada
- **OpenTelemetry 1.29.0** - Tracing e métricas distribuídas
- **gRPC 1.68.1** - Comunicação entre serviços
- **Structlog** - Logging estruturado com correlation IDs
- **FastAPI + Uvicorn** - Framework web
- **Bibliotecas NHM** - Todas as bibliotecas base pré-instaladas

## Bibliotecas NHM Incluídas

- `neural_hive_domain` - Modelos de domínio partilhados
- `neural_hive_exceptions` - Exceções centralizadas
- `neural_hive_infrastructure` - Configurações base
- `neural_hive_observability` - Logging, métricas, tracing
- `neural_hive_resilience` - Circuit breakers, retries

## Uso

### Serviço Básico

```dockerfile
FROM ghcr.io/albinojimy/neural-hive-mind/python-base:2.0.0

# Copiar código do serviço
COPY src/ /app/src/
COPY requirements.txt /app/

# Instalar dependências específicas do serviço
RUN pip install --no-cache-dir -r requirements.txt

# Comando de execução
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Serviço com ML

```dockerfile
FROM ghcr.io/albinojimy/neural-hive-mind/python-base:2.0.0

# Dependências ML adicionais
RUN pip install --no-cache-dir \
    scikit-learn>=1.5.0 \
    pandas>=2.2.0 \
    numpy>=2.0.0

# Resto do serviço...
```

## Build

```bash
# Local
docker build -t nhm-python-base:2.0.0 base-images/python-base/

# Para GHCR
docker build \
  --build-arg REGISTRY=ghcr.io/albinojimy \
  --build-arg VERSION=2.0.0 \
  --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t ghcr.io/albinojimy/neural-hive-mind/python-base:2.0.0 \
  base-images/python-base/
```

## Variáveis de Ambiente

- `PYTHONUNBUFFERED=1` - Output sem buffer
- `PYTHONDONTWRITEBYTECODE=1` - Não criar .pyc
- `PIP_NO_CACHE_DIR=1` - Não cache do pip

## Ports Padrão

- `8000` - HTTP/REST API
- `50051` - gRPC
- `9090` - Prometheus metrics
