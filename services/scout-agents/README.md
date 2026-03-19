# Scout Agents - Neural Hive-Mind

Sistema de exploração e descoberta de código para o Neural Hive-Mind.

## Descrição

O Scout Agents é um serviço especializado em exploração de codebases, detecção de sinais de mudança e identificação de padrões de design. Ele coordena múltiplos "scouts" que trabalham em paralelo para analisar código, descobrir padrões e publicar insights.

## Funcionalidades

- **Detecção de Sinais**: Identifica arquivos criados, modificados ou deletados
- **Scoring de Curiosidade**: Calcula pontuação de interesse para arquivos baseado em:
  - Complexidade ciclomática
  - Densidade de padrões
  - Palavras-chave desconhecidas
  - Razão de comentários
  - Bibliotecas externas
- **Coordenação Multi-Scout**: Gerencia múltiplos scouts com distribuição de tarefas
- **Redis State Store**: Compartilhamento de estado via Redis para evitar trabalho duplicado
- **API REST Endpoints**: Endpoints para gerenciamento de explorações e consulta de métricas

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                         Scout Agents                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │  Curiosity      │  │  Signal          │  │  Scout        │ │
│  │  Calculator     │  │  Detector        │  │  Coordinator  │ │
│  └────────┬────────┘  └────────┬─────────┘  └───────┬───────┘ │
│           │                    │                    │           │
│           └────────────────────┴────────────────────┘           │
│                                │                                │
│  ┌─────────────────────────────▼─────────────────────────────┐ │
│  │                    Exploration Engine                       │ │
│  └─────────────────────────────┬─────────────────────────────┘ │
│                                │                                │
│  ┌─────────────────────────────▼─────────────────────────────┐ │
│  │                    Redis State Store                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Instalação

### Requisitos

- Python 3.12+
- Redis (opcional, para coordenação distribuída)
- Kafka (opcional, para publicação de eventos)

### Dependências

```bash
pip install -r requirements.txt
```

## Execução

### Desenvolvimento

```bash
python -m src.main
```

### Produção

```bash
helm install scout-agents ./helm/scout-agents
```

## API

### Health Checks

- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe
- `GET /metrics` - Métricas Prometheus

### Exploração

- `GET /api/v1/explorations` - Lista explorações
- `POST /api/v1/explorations` - Cria nova exploração
- `DELETE /api/v1/explorations/{id}` - Cancela exploração
- `POST /api/v1/explorations/{id}/scouts` - Adiciona scout

### Detecção

- `POST /api/v1/signal-detect` - Detecta sinais em diretório
- `GET /api/v1/curiosity/{directory}` - Scores de curiosidade
- `GET /api/v1/exploration-summary/{directory}` - Resumo de exploração

### Padrões

- `GET /api/v1/patterns` - Lista padrões detectados

## Testes

```bash
# Rodar todos os testes
pytest

# Rodar com coverage
pytest --cov=src

# Rodar testes específicos
pytest tests/signals/
pytest tests/coordination/
pytest tests/api_extended/
```

### Cobertura de Testes

- **294 testes** no total
- 100% de cobertura nas funcionalidades core

## Configuração

### Variáveis de Ambiente

```bash
# Service
ENVIRONMENT=production
LOG_LEVEL=INFO

# Detection
SCOUT_MAX_SIGNALS_PER_MINUTE=100
SCOUT_CURIOSITY_THRESHOLD=70.0
SCOUT_CONFIDENCE_THRESHOLD=0.6

# Exploration
SCOUT_MAX_CONCURRENT_SCOUTS=10
SCOUT_DEFAULT_TIMEOUT_MINUTES=30
SCOUT_ENABLE_BURST_DETECTION=true

# Redis
REDIS_URL=redis://localhost:6379
REDIS_KEY_PREFIX=scout_agents:
REDIS_TTL=3600

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
SCOUT_SIGNALS_TOPIC=scout.signals
SCOUT_DISCOVERIES_TOPIC=scout.discoveries
```

## Deploy

### Docker

```bash
docker build -t scout-agents:latest .
docker run -p 8000:8000 scout-agents:latest
```

### Kubernetes com Helm

```bash
helm install scout-agents ./helm/scout-agents \
  --set image.tag=v1.0.0 \
  --set config.redis.url=redis://redis:6379
```

## Observabilidade

### Métricas Prometheus

O serviço expõe métricas em `/metrics`:

- `scout_signals_detected_total` - Total de sinais detectados
- `scout_files_scanned_total` - Total de arquivos escaneados
- `scout_patterns_found_total` - Total de padrões encontrados
- `scout_active_explorations` - Explorações ativas
- `scout_scouts_active` - Scouts ativos

### Dashboard Grafana

Importe o dashboard em `monitoring/grafana-dashboard.json`.

## Licença

MIT
